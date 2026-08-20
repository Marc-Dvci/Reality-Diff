from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings


USEFULNESS_VALUES = [
    "PHYSICAL_STATE_HIGH_VALUE",
    "PHYSICAL_STATE_INCIDENTAL",
    "DOCUMENT",
    "SCREENSHOT",
    "MEME",
    "PORTRAIT",
    "SCENERY",
    "FOOD",
    "UNKNOWN",
]

TRIAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["usefulness", "reason"],
    "properties": {
        "usefulness": {"type": "string", "enum": USEFULNESS_VALUES},
        "reason": {"type": "string"},
    },
}

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "scene_type",
        "candidate_subject",
        "description",
        "entities",
        "quality",
    ],
    "properties": {
        "scene_type": {"type": "string"},
        "candidate_subject": {"type": "string"},
        "description": {"type": "string"},
        "quality": {
            "type": "object",
            "required": ["usable", "coverage_note"],
            "properties": {
                "usable": {"type": "boolean"},
                "coverage_note": {"type": "string"},
            },
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "attributes", "relation", "confidence"],
                "properties": {
                    "name": {"type": "string"},
                    "attributes": {"type": "array", "items": {"type": "string"}},
                    "relation": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
}

WORLD_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "status",
        "title",
        "text",
        "confidence",
        "confidence_label",
        "subject_id",
        "evidence_ids",
        "coverage_note",
        "follow_up",
        "choices",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["answered", "uncertain", "clarification_required", "not_found"],
        },
        "title": {"type": "string"},
        "text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence_label": {
            "type": "string",
            "enum": ["high", "medium", "low", "not_applicable"],
        },
        "subject_id": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "coverage_note": {"type": "string"},
        "follow_up": {"type": "string"},
        "choices": {"type": "array", "items": {"type": "string"}},
    },
}


class GeminiMediaAnalyzer:
    """Cost-aware, multimodel visual indexing pipeline.

    Flash-Lite rejects low-value gallery noise, Gemini 3.7 Flash constructs the
    evidence-safe semantic observation, and Gemini Embedding 2 maps the retained
    image into the same retrieval space as natural-language questions.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client_instance: Any | None = None

    def analyze(self, image_path: Path) -> dict[str, Any]:
        return self.analyze_bytes(image_path.read_bytes(), _mime_type(image_path), image_path.name)

    def analyze_bytes(
        self, image_bytes: bytes, mime_type: str, filename: str = "photo"
    ) -> dict[str, Any]:
        if not self.settings.live_model_enabled:
            return demo_analysis(filename, mime_type, len(image_bytes), self.settings)

        client, types = self._client()
        image = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        triage_response = client.models.generate_content(
            model=self.settings.triage_model,
            contents=[
                image,
                types.Part.from_text(
                    text=(
                        "Classify this personal-gallery image for reconstructing physical state. "
                        "Prefer PHYSICAL_STATE_HIGH_VALUE only when a place, durable object, "
                        "vehicle, plant, kit, or project state is clearly observable. Return only "
                        "the requested JSON. Do not identify people or infer sensitive attributes."
                    )
                ),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=TRIAGE_SCHEMA,
            ),
        )
        triage = _response_json(triage_response)
        usefulness = triage.get("usefulness", "UNKNOWN")

        semantic: dict[str, Any] = {
            "scene_type": usefulness.lower(),
            "candidate_subject": "Unsorted",
            "description": triage.get("reason", "No semantic analysis was required."),
            "entities": [],
            "quality": {"usable": False, "coverage_note": "Filtered during first-pass triage."},
        }
        should_analyze = usefulness in {
            "PHYSICAL_STATE_HIGH_VALUE",
            "PHYSICAL_STATE_INCIDENTAL",
            "DOCUMENT",
        }
        if should_analyze:
            response = client.models.generate_content(
                model=self.settings.gemini_model,
                contents=[
                    image,
                    types.Part.from_text(
                        text=(
                            "Create one evidence-safe observation for a temporal photo-memory "
                            "system. Describe only visible facts. Name a durable candidate subject "
                            "that could recur across photos, list persistent physical entities and "
                            "their visible attributes/relationships, and state any framing or "
                            "coverage limitation. Never identify a person, infer sensitive traits, "
                            "or claim that a change occurred from this single image. Return only "
                            "the requested JSON."
                        )
                    ),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=ANALYSIS_SCHEMA,
                ),
            )
            semantic = _response_json(response)

        embedding = self.embed_bytes(image_bytes, mime_type)
        return {
            "usefulness": usefulness,
            "triage_reason": triage.get("reason", ""),
            **semantic,
            "embedding": embedding,
            "pipeline": {
                "execution": "live",
                "triage_model": self.settings.triage_model,
                "reasoning_model": self.settings.gemini_model if should_analyze else None,
                "embedding_model": self.settings.embedding_model,
            },
        }

    def embed_bytes(self, image_bytes: bytes, mime_type: str) -> list[float]:
        if not self.settings.live_model_enabled:
            return []
        client, types = self._client()
        response = client.models.embed_content(
            model=self.settings.embedding_model,
            contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768,
            ),
        )
        return _embedding_values(response)

    def embed_text(self, text: str) -> list[float]:
        """Embed a question in the same multimodal retrieval space as gallery images."""
        if not self.settings.live_model_enabled:
            return []
        client, types = self._client()
        response = client.models.embed_content(
            model=self.settings.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        return _embedding_values(response)

    def reason_about_observations(
        self, question: str, observations: list[dict[str, Any]], memory: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Use Gemini 3.7 Flash over retrieved, pre-grounded observations."""
        if not self.settings.live_model_enabled:
            raise RuntimeError("Live Gemini reasoning is disabled")
        client, types = self._client()
        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=[
                types.Part.from_text(
                    text=(
                        "You are the evidence-first Reality Diff temporal reasoning agent. "
                        "Answer the user's question using only the supplied observations. Every "
                        "evidence_ids value must exactly match a supplied id. Observation time "
                        "only bounds a change; never invent an exact event time. Absence is useful "
                        "only when the relevant region was visibly covered. If subjects or regions "
                        "are ambiguous, request one focused clarification. If required coverage is "
                        "missing, return uncertain. Never identify people or infer sensitive "
                        "traits. Empty optional text fields must be empty strings.\n\n"
                        f"USER QUESTION:\n{question}\n\n"
                        f"EXPLICIT USER MEMORY:\n{json.dumps(memory, ensure_ascii=False)}\n\n"
                        "RETRIEVED OBSERVATIONS:\n"
                        f"{json.dumps(observations, ensure_ascii=False)}"
                    )
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=WORLD_ANSWER_SCHEMA,
            ),
        )
        return _response_json(response)

    def _client(self) -> tuple[Any, Any]:
        if self._client_instance is not None:
            from google.genai import types

            return self._client_instance, types
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc

        if self.settings.gemini_api_key:
            self._client_instance = genai.Client(api_key=self.settings.gemini_api_key)
        else:
            self._client_instance = genai.Client(
                vertexai=True,
                project=self.settings.google_cloud_project,
                location=self.settings.google_cloud_location,
            )
        return self._client_instance, types


def demo_analysis(
    filename: str, mime_type: str, size: int, settings: Settings
) -> dict[str, Any]:
    """Truthful local result used when credentials are intentionally absent."""
    stem = Path(filename).stem.replace("-", " ").replace("_", " ").strip()
    return {
        "usefulness": "UNKNOWN",
        "triage_reason": "Saved locally; connect Vertex AI to run semantic analysis.",
        "scene_type": "pending_live_analysis",
        "candidate_subject": stem.title() or "Imported photo",
        "description": "This photo is available in the gallery and queued for cloud analysis.",
        "entities": [],
        "quality": {
            "usable": True,
            "coverage_note": "Visual coverage has not been assessed in local demo mode.",
        },
        "embedding": [],
        "pipeline": {
            "execution": "local_pending",
            "triage_model": settings.triage_model,
            "reasoning_model": settings.gemini_model,
            "embedding_model": settings.embedding_model,
            "mime_type": mime_type,
            "bytes": size,
        },
    }


def _response_json(response: Any) -> dict[str, Any]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed
    value = json.loads(getattr(response, "text", None) or "{}")
    if not isinstance(value, dict):
        raise ValueError("Gemini returned a non-object JSON response")
    return value


def _embedding_values(response: Any) -> list[float]:
    embeddings = getattr(response, "embeddings", None) or []
    if not embeddings:
        return []
    values = getattr(embeddings[0], "values", None)
    return [float(value) for value in (values or [])]


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "image/jpeg")
