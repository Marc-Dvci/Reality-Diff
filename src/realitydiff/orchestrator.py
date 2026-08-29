from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from .adk_agent import build_adk_agent
from .config import Settings
from .models import AgentStep, Answer, AskRequest, ConversationTurn
from .repository import WorldRepository


_ANSWER_KEYS = {"status", "title", "text"}


class AdkOrchestrator:
    """Run the web conversation through the Google ADK Collaborative Partner.

    The ADK agent owns the dialogue: it chooses which evidence tool to call, asks its own
    clarifying questions, and carries multi-turn state through the ADK session service keyed
    by ``conversation_id``. The evidence itself still comes from the deterministic and Gemini
    reasoners the tools wrap, so every rendered claim resolves to a validated source photo.

    ``answer`` returns ``None`` on any failure so the API can fall back to the direct pipeline;
    the demo can never regress below the deterministic path.
    """

    def __init__(self, repository: WorldRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.app_name = "realitydiff"
        self._runner: Any | None = None
        self._session_service: Any | None = None

    def _ensure_runner(self) -> Any:
        if self._runner is None:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            self._session_service = InMemorySessionService()
            self._runner = Runner(
                app_name=self.app_name,
                agent=build_adk_agent(self.repository),
                session_service=self._session_service,
                auto_create_session=True,
            )
        return self._runner

    async def answer(self, request: AskRequest) -> Answer | None:
        try:
            from google.genai import types

            # ADK isolates state by (app, user_id, session_id). Keying the user on the
            # anonymous owner token means one visitor's session, history, and tool results
            # can never be reached from another visitor's turn, even if two browsers ever
            # generated the same conversation_id.
            owner = request.owner_id or "web"
            runner = self._ensure_runner()
            await self._ensure_session(owner, request.conversation_id, request.history)
            message = types.Content(
                role="user", parts=[types.Part.from_text(text=request.question)]
            )
            grounded: Answer | None = None
            final_text = ""
            tool_calls: list[str] = []
            async for event in runner.run_async(
                user_id=owner,
                session_id=request.conversation_id,
                new_message=message,
            ):
                for call in event.get_function_calls():
                    tool_calls.append(call.name)
                for response in event.get_function_responses():
                    candidate = _as_answer(response.response)
                    if candidate is not None:
                        grounded = candidate
                if event.is_final_response() and event.content:
                    final_text = _content_text(event.content) or final_text
            return _finalize(grounded, final_text, tool_calls)
        except Exception:
            return None

    async def _ensure_session(
        self, owner: str, conversation_id: str, history: list[ConversationTurn] | None = None
    ) -> None:
        service = self._session_service
        if service is None:
            return
        existing = await service.get_session(
            app_name=self.app_name, user_id=owner, session_id=conversation_id
        )
        if existing is not None:
            return
        # The owner is carried in session state so the evidence tools scope every
        # retrieval to this visitor's own uploads and corrections.
        session = await service.create_session(
            app_name=self.app_name,
            user_id=owner,
            session_id=conversation_id,
            state={"owner_id": owner},
        )
        # In-memory sessions are per-instance, so a recycled or fresh Cloud Run instance
        # starts empty. Reconstruct the turn history the client already carries, so a
        # multi-turn follow-up still resolves against earlier turns wherever it lands.
        await self._seed_history(service, session, history)

    async def _seed_history(
        self, service: Any, session: Any, history: list[ConversationTurn] | None
    ) -> None:
        if not history:
            return
        from google.adk.events import Event
        from google.genai import types

        author = getattr(getattr(self._runner, "agent", None), "name", None) or self.app_name
        for turn in history:
            text = (getattr(turn, "text", "") or "").strip()
            if not text:
                continue
            if getattr(turn, "role", "") == "user":
                content = types.Content(role="user", parts=[types.Part.from_text(text=text)])
                event = Event(author="user", content=content)
            else:
                content = types.Content(role="model", parts=[types.Part.from_text(text=text)])
                event = Event(author=author, content=content)
            try:
                await service.append_event(session, event)
            except Exception:
                # Seeding is best effort: a single unusable turn must not drop the turn.
                continue


def _as_answer(payload: Any) -> Answer | None:
    data = payload
    if isinstance(data, dict) and _ANSWER_KEYS - set(data.keys()) and "result" in data:
        data = data["result"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return None
    if not isinstance(data, dict) or not _ANSWER_KEYS.issubset(data.keys()):
        return None
    try:
        return Answer.model_validate(data)
    except Exception:
        return None


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    texts = [getattr(part, "text", None) for part in parts]
    return " ".join(text.strip() for text in texts if text).strip()


def _finalize(grounded: Answer | None, final_text: str, tool_calls: list[str]) -> Answer | None:
    marker = AgentStep(
        name="Orchestrate",
        detail=(
            "Google ADK led the turn and called "
            f"{', '.join(dict.fromkeys(tool_calls)) or 'no'} evidence tool(s)."
        ),
    )
    if grounded is not None:
        grounded.steps = [marker, *grounded.steps]
        return grounded
    if final_text:
        # The partner spoke without grounding a claim: a clarifying question, never an
        # asserted fact. Render it as such so nothing appears with unlinked evidence.
        is_question = final_text.rstrip().endswith("?")
        return Answer(
            answer_id=f"ans_{uuid4().hex[:10]}",
            status="clarification_required" if is_question else "uncertain",
            title="A quick check before I answer" if is_question else "I can't confirm that yet",
            text=final_text,
            confidence=0.0,
            confidence_label="not_applicable" if is_question else "low",
            coverage_note=None if is_question else "No source photo was linked to this reply.",
            steps=[marker],
        )
    return None
