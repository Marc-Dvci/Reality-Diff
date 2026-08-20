from __future__ import annotations

import json
from typing import Any

from .config import settings
from .live_reasoner import GeminiTemporalReasoner
from .models import AskRequest, CorrectionRequest
from .pipeline import GeminiMediaAnalyzer
from .repository import WorldRepository
from .temporal import TemporalReasoner


def build_adk_agent(repository: WorldRepository) -> Any:
    """Build the Collaborative Partner with repository-scoped tools."""
    try:
        from google.adk.agents import Agent
        from google.adk.models import Gemini
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc

    reasoner = TemporalReasoner(repository)
    imported_reasoner = GeminiTemporalReasoner(repository, GeminiMediaAnalyzer(settings))

    def search_world(question: str, conversation_id: str = "adk-session") -> str:
        """Search temporal observations and return an evidence-linked answer as JSON."""
        answer = reasoner.answer(AskRequest(question=question, conversation_id=conversation_id))
        return answer.model_dump_json()

    def inspect_subject(subject_id: str) -> str:
        """Return one subject's timeline, changes, coverage, and source asset ids."""
        subject = repository.subject(subject_id)
        return json.dumps(subject or {"error": "subject_not_found"})

    def search_imported_photos(question: str, limit: int = 8) -> str:
        """Retrieve live imported-photo observations related to a natural-language question."""
        safe_limit = max(1, min(limit, 12))
        ranked = imported_reasoner.retrieve_uploads(question, safe_limit)
        observations = []
        for item in ranked:
            analysis = item.get("analysis", {})
            observations.append(
                {
                    "id": item.get("id"),
                    "captured_at": item.get("captured_at"),
                    "capture_time_source": item.get("capture_time_source"),
                    "candidate_subject": analysis.get("candidate_subject"),
                    "description": analysis.get("description"),
                    "entities": analysis.get("entities", []),
                    "quality": analysis.get("quality", {}),
                }
            )
        return json.dumps(observations)

    def remember_correction(kind: str, statement: str, subject_id: str = "") -> str:
        """Persist a user's natural-language correction for later conversations."""
        allowed = {"identity", "alias", "significance", "evidence", "category"}
        if kind not in allowed:
            return json.dumps({"error": "invalid_kind", "allowed": sorted(allowed)})
        correction = repository.remember(
            CorrectionRequest(
                conversation_id="adk-session",
                kind=kind,  # type: ignore[arg-type]
                subject_id=subject_id or None,
                statement=statement,
            )
        )
        return correction.model_dump_json()

    return Agent(
        name="reality_diff_partner",
        model=Gemini(
            model=settings.gemini_model,
            retry_options=types.HttpRetryOptions(attempts=3),
        ),
        description="Evidence-first semantic memory for the physical world.",
        instruction=(
            "Lead the user through questions about how physical subjects changed over time. "
            "Use search_world for the verified sample and search_imported_photos for live "
            "imports before asserting a physical fact. Cite returned evidence, distinguish "
            "last-seen from exact change time, ask one focused clarifying question when entities "
            "are ambiguous, and say that a claim is unverifiable when required photo coverage is "
            "missing. Save corrections only when the user explicitly provides one."
        ),
        tools=[search_world, search_imported_photos, inspect_subject, remember_correction],
    )


def build_adk_app(repository: WorldRepository, root_agent: Any | None = None) -> Any:
    """Return the standard ADK App wrapper used by ADK web/CLI/Cloud Run."""
    try:
        from google.adk.apps import App
    except ImportError as exc:
        raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc
    return App(root_agent=root_agent or build_adk_agent(repository), name="realitydiff")
