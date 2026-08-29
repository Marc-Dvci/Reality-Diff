from __future__ import annotations

import json
from typing import Any

from .config import settings
from .live_reasoner import GeminiTemporalReasoner
from .models import Answer, AskRequest, CorrectionRequest
from .pipeline import GeminiMediaAnalyzer
from .repository import WorldRepository
from .temporal import TemporalReasoner

try:  # ToolContext must be a module global so ADK can resolve the tool signatures.
    from google.adk.tools import ToolContext
except ImportError:  # The Google integration is an optional dependency.
    ToolContext = Any  # type: ignore[assignment, misc]


AGENT_INSTRUCTION = (
    "You are Reality Diff, an evidence-first collaborative partner for questions about how "
    "physical subjects changed over time. Lead the conversation. Before asserting any physical "
    "fact, call search_world for the verified sample world and search_imported_photos for the "
    "user's live imports. Both tools return a grounded, evidence-linked answer as JSON: relay "
    "that answer and its evidence, never invent a photo, a date, or a region. Observation time "
    "only bounds when a change happened; do not claim an exact day the photos cannot show. When "
    "the subject or region is ambiguous, ask one focused clarifying question and stop. When the "
    "conversation continues, resolve short follow-ups like 'the other one' from the earlier "
    "turns before searching again. When required photo coverage is missing, say the claim is "
    "unverifiable and name the one photo that would close the gap. Call remember_correction only "
    "when the user explicitly gives a correction."
)


def _conversation_id(tool_context: Any) -> str:
    session = getattr(tool_context, "session", None)
    session_id = getattr(session, "id", None)
    return str(session_id) if session_id else "adk-session"


def _owner_id(tool_context: Any) -> str | None:
    """The anonymous owner token the orchestrator stored in the ADK session state.

    Every evidence tool passes this into its reasoner so a turn can only ever read the
    uploads and corrections that belong to the visitor who started the session.
    """
    state = getattr(tool_context, "state", None)
    if state is None:
        return None
    try:
        return state.get("owner_id")
    except (AttributeError, TypeError):
        return None


def build_adk_agent(repository: WorldRepository) -> Any:
    """Build the Collaborative Partner with repository-scoped, evidence-linked tools."""
    try:
        from google.adk.agents import Agent
        from google.adk.models import Gemini
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc

    reasoner = TemporalReasoner(repository)
    imported_reasoner = GeminiTemporalReasoner(repository, GeminiMediaAnalyzer(settings))

    # Point the agent's model at the same backend as the rest of the pipeline, so the live
    # deployment orchestrates on Vertex AI instead of falling back to a default client.
    if settings.gemini_api_key:
        client_kwargs: dict[str, Any] = {"api_key": settings.gemini_api_key}
    else:
        client_kwargs = {
            "vertexai": True,
            "project": settings.google_cloud_project,
            "location": settings.google_cloud_location,
        }

    def search_world(question: str, tool_context: ToolContext) -> str:
        """Answer a question from the verified sample world as evidence-linked JSON.

        Use this for the user's recurring realities (home office, rental car, bike project).
        The returned JSON is already grounded; relay its answer, evidence, and any coverage
        gap or clarification verbatim.
        """
        answer = reasoner.answer(
            AskRequest(
                question=question,
                conversation_id=_conversation_id(tool_context),
                owner_id=_owner_id(tool_context),
            )
        )
        return answer.model_dump_json()

    def search_imported_photos(question: str, tool_context: ToolContext) -> str:
        """Answer a question from the user's own imported photos as evidence-linked JSON.

        Gemini Embedding 2 retrieves the relevant private observations and Gemini reasons over
        them. Returns a grounded answer, or a not_found answer when nothing matches.
        """
        conversation_id = _conversation_id(tool_context)
        try:
            answer = imported_reasoner.answer(
                AskRequest(
                    question=question,
                    conversation_id=conversation_id,
                    owner_id=_owner_id(tool_context),
                )
            )
        except Exception:
            answer = None
        if answer is None:
            answer = Answer(
                answer_id="ans_no_import",
                status="not_found",
                title="No imported photo answers that yet",
                text=(
                    "None of your imported photos matched that question closely enough to "
                    "support an answer. Add a photo of the subject and ask again."
                ),
                confidence=0,
                confidence_label="not_applicable",
            )
        return answer.model_dump_json()

    def inspect_subject(subject_id: str) -> str:
        """Return one subject's timeline, changes, coverage, and source asset ids."""
        subject = repository.subject(subject_id)
        return json.dumps(subject or {"error": "subject_not_found"})

    def remember_correction(
        kind: str, statement: str, tool_context: ToolContext, subject_id: str = ""
    ) -> str:
        """Persist a user's explicit natural-language correction for later conversations."""
        allowed = {"identity", "alias", "significance", "evidence", "category"}
        if kind not in allowed:
            return json.dumps({"error": "invalid_kind", "allowed": sorted(allowed)})
        correction = repository.remember(
            CorrectionRequest(
                conversation_id=_conversation_id(tool_context),
                kind=kind,  # type: ignore[arg-type]
                subject_id=subject_id or None,
                statement=statement,
                owner_id=_owner_id(tool_context),
            )
        )
        stored = correction.model_dump()
        stored.pop("owner_id", None)
        return json.dumps(stored)

    return Agent(
        name="reality_diff_partner",
        model=Gemini(
            model=settings.gemini_model,
            client_kwargs=client_kwargs,
            retry_options=types.HttpRetryOptions(attempts=3),
        ),
        description="Evidence-first semantic memory for the physical world.",
        instruction=AGENT_INSTRUCTION,
        tools=[search_world, search_imported_photos, inspect_subject, remember_correction],
    )


def build_adk_app(repository: WorldRepository, root_agent: Any | None = None) -> Any:
    """Return the standard ADK App wrapper used by ADK web/CLI/Cloud Run."""
    try:
        from google.adk.apps import App
    except ImportError as exc:
        raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc
    return App(root_agent=root_agent or build_adk_agent(repository), name="realitydiff")
