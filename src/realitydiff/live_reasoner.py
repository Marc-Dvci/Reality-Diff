from __future__ import annotations

from math import sqrt
from typing import Any
from uuid import uuid4

from .models import AgentStep, Answer, AskRequest, EvidenceRef
from .pipeline import GeminiMediaAnalyzer
from .repository import WorldRepository


class GeminiTemporalReasoner:
    """Ground Gemini answers in uploads retrieved with Gemini Embedding 2."""

    def __init__(self, repository: WorldRepository, analyzer: GeminiMediaAnalyzer) -> None:
        self.repository = repository
        self.analyzer = analyzer

    def answer(self, request: AskRequest) -> Answer | None:
        uploads = self.retrieve_uploads(request.question, request.owner_id, 12)
        if not uploads:
            return None

        observations = [_observation_payload(item) for item in uploads]
        raw = self.analyzer.reason_about_observations(
            request.question,
            observations,
            self.repository.corrections(request.conversation_id, request.owner_id),
        )
        allowed = {str(item["id"]): item for item in uploads}
        evidence = [
            _evidence_ref(allowed[item_id])
            for item_id in dict.fromkeys(raw.get("evidence_ids", []))
            if item_id in allowed
        ]
        status = raw.get("status", "not_found")
        if status == "answered" and not evidence:
            status = "uncertain"
            raw["confidence"] = min(float(raw.get("confidence", 0)), 0.25)
            raw["confidence_label"] = "low"
            raw["coverage_note"] = "Gemini did not return a verifiable source photo."
        return Answer(
            answer_id=f"ans_{uuid4().hex[:10]}",
            status=status,
            title=str(raw.get("title", "I could not verify that"))[:180],
            text=str(raw.get("text", "The indexed photos do not support an answer."))[:1200],
            confidence=float(raw.get("confidence", 0)),
            confidence_label=raw.get("confidence_label", "not_applicable"),
            subject_id=str(raw.get("subject_id") or "")[:100] or None,
            evidence=evidence,
            coverage_note=str(raw.get("coverage_note") or "")[:500] or None,
            follow_up=str(raw.get("follow_up") or "")[:300] or None,
            choices=[str(choice)[:160] for choice in raw.get("choices", [])[:4]],
            steps=[
                AgentStep(
                    name="Retrieve",
                    detail=(
                        f"Gemini Embedding 2 ranked the private observations; "
                        f"the top {len(uploads)} were inspected."
                    ),
                ),
                AgentStep(
                    name="Reason",
                    detail="Gemini 3.7 Flash produced a schema-constrained answer.",
                ),
                AgentStep(
                    name="Ground",
                    detail=f"Validated {len(evidence)} returned evidence id(s) against storage.",
                ),
            ],
        )

    def retrieve_uploads(
        self, question: str, owner_id: str | None = None, limit: int = 12
    ) -> list[dict[str, Any]]:
        uploads = [
            item
            for item in self.repository.uploads_for_reasoning(owner_id)
            if item.get("status") == "analyzed" and item.get("analysis")
        ]
        if not uploads:
            return []

        query_embedding = self.analyzer.embed_text(question)
        return sorted(
            uploads,
            key=lambda item: _cosine(query_embedding, item.get("_embedding", [])),
            reverse=True,
        )[: max(1, min(limit, 12))]


def _observation_payload(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("analysis", {})
    return {
        "id": item.get("id"),
        "captured_at": item.get("captured_at"),
        "capture_time_source": item.get("capture_time_source"),
        "title": item.get("title"),
        "candidate_subject": analysis.get("candidate_subject"),
        "scene_type": analysis.get("scene_type"),
        "description": analysis.get("description"),
        "entities": analysis.get("entities", []),
        "quality": analysis.get("quality", {}),
    }


def _evidence_ref(item: dict[str, Any]) -> EvidenceRef:
    analysis = item.get("analysis", {})
    entity_confidences = [
        float(entity.get("confidence", 0))
        for entity in analysis.get("entities", [])
        if isinstance(entity, dict)
    ]
    return EvidenceRef(
        asset_id=str(item["id"]),
        subject_id=str(analysis.get("candidate_subject") or "imported-photo"),
        image=str(item["image"]),
        captured_at=str(item["captured_at"]),
        label=str(item.get("title") or "Imported photo"),
        observation=str(analysis.get("description") or "No visible-state description."),
        confidence=max(entity_confidences, default=0.65),
    )


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    denominator = sqrt(sum(value * value for value in left)) * sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return -1.0
    return sum(a * b for a, b in zip(left, right)) / denominator
