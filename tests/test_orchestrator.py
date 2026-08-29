"""The web conversation is genuinely driven by the Google ADK agent.

These tests run the real ADK ``Runner`` and agent; only the network model call is
replaced by a scripted fake, so tool selection, evidence grounding, multi-turn session
state, and the fallback contract are all exercised against the actual framework.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("google.adk")

from google.adk.models import BaseLlm, LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

from realitydiff.config import settings  # noqa: E402
from realitydiff.models import AskRequest, ConversationTurn  # noqa: E402
from realitydiff.orchestrator import AdkOrchestrator  # noqa: E402
from realitydiff.repository import WorldRepository  # noqa: E402


FIXTURE = Path(__file__).parents[1] / "web" / "fixtures" / "demo.json"


class ToolThenText(BaseLlm):
    """Call an evidence tool for a fresh question, then speak once it returns."""

    model: str = "fake-tool-then-text"
    tool: str = "search_world"
    question: str = "When did I replace my chair?"

    async def generate_content_async(self, llm_request, stream=False):
        last = llm_request.contents[-1] if llm_request.contents else None
        parts = getattr(last, "parts", None) or []
        got_tool_result = any(getattr(part, "function_response", None) for part in parts)
        if got_tool_result:
            content = types.Content(
                role="model", parts=[types.Part.from_text(text="Here is what your photos show.")]
            )
        else:
            content = types.Content(
                role="model",
                parts=[types.Part.from_function_call(name=self.tool, args={"question": self.question})],
            )
        yield LlmResponse(content=content)


class TextOnly(BaseLlm):
    """Ask a clarifying question without calling any tool."""

    model: str = "fake-text-only"
    reply: str = "Which mark do you mean, the front-left or the rear-right?"

    async def generate_content_async(self, llm_request, stream=False):
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part.from_text(text=self.reply)])
        )


class Boom(BaseLlm):
    model: str = "fake-boom"

    async def generate_content_async(self, llm_request, stream=False):
        raise RuntimeError("model unavailable")
        yield  # pragma: no cover - marks this an async generator


def _orchestrator(model: BaseLlm) -> AdkOrchestrator:
    orchestrator = AdkOrchestrator(WorldRepository(FIXTURE), settings)
    orchestrator._ensure_runner()
    orchestrator._runner.agent.model = model
    return orchestrator


def test_adk_orchestrates_the_turn_and_grounds_the_answer() -> None:
    orchestrator = _orchestrator(ToolThenText())
    answer = asyncio.run(
        orchestrator.answer(
            AskRequest(question="When did I replace my chair?", conversation_id="c1")
        )
    )
    assert answer is not None
    assert answer.status == "answered"
    assert {item.asset_id for item in answer.evidence} == {"office-jun-04", "office-jun-11"}
    # The turn is provably ADK-led, and every rendered evidence id came from the tool.
    assert answer.steps[0].name == "Orchestrate"
    assert "ADK" in answer.steps[0].detail


def test_a_toolless_reply_never_renders_as_a_grounded_fact() -> None:
    orchestrator = _orchestrator(TextOnly())
    answer = asyncio.run(
        orchestrator.answer(
            AskRequest(question="Was this scratch already there?", conversation_id="c2")
        )
    )
    assert answer is not None
    assert answer.status == "clarification_required"
    assert answer.evidence == []
    assert answer.confidence == 0


def test_session_state_is_carried_across_turns() -> None:
    orchestrator = _orchestrator(ToolThenText())

    async def run_two_turns():
        await orchestrator.answer(
            AskRequest(question="When did I replace my chair?", conversation_id="c3")
        )
        await orchestrator.answer(
            AskRequest(question="And the monitor?", conversation_id="c3")
        )
        return await orchestrator._session_service.get_session(
            app_name=orchestrator.app_name, user_id="web", session_id="c3"
        )

    session = asyncio.run(run_two_turns())
    assert session is not None
    # Both user turns and their tool exchanges accumulate in one persistent session.
    assert len(session.events) >= 4


def test_client_history_is_seeded_into_a_fresh_session() -> None:
    # In-memory sessions are per-instance; a fresh instance must reconstruct the
    # conversation from the history the client sends every turn.
    orchestrator = _orchestrator(ToolThenText())

    async def run_with_history():
        await orchestrator.answer(
            AskRequest(
                question="The rear one.",
                conversation_id="c5",
                history=[
                    ConversationTurn(role="user", text="Was this scratch already there?"),
                    ConversationTurn(role="agent", text="Which mark, front-left or rear-right?"),
                ],
            )
        )
        return await orchestrator._session_service.get_session(
            app_name=orchestrator.app_name, user_id="web", session_id="c5"
        )

    session = asyncio.run(run_with_history())
    texts = [
        "".join(part.text or "" for part in (event.content.parts or []))
        for event in session.events
        if event.content
    ]
    assert "Was this scratch already there?" in texts
    assert "Which mark, front-left or rear-right?" in texts


def test_orchestrator_returns_none_so_the_api_can_fall_back() -> None:
    orchestrator = _orchestrator(Boom())
    answer = asyncio.run(
        orchestrator.answer(
            AskRequest(question="When did I replace my chair?", conversation_id="c4")
        )
    )
    assert answer is None
