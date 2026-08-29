from pathlib import Path

from realitydiff.models import AskRequest, ConversationTurn, CorrectionRequest
from realitydiff.repository import WorldRepository
from realitydiff.temporal import TemporalReasoner


FIXTURE = Path(__file__).parents[1] / "web" / "fixtures" / "demo.json"


def reasoner() -> TemporalReasoner:
    return TemporalReasoner(WorldRepository(FIXTURE))


def test_chair_answer_bounds_time_instead_of_inventing_a_day() -> None:
    answer = reasoner().answer(AskRequest(question="When did I replace my chair?"))
    assert answer.status == "answered"
    assert "June 4" in answer.text
    assert "June 11" in answer.text
    assert "not a single day" in answer.text
    assert len(answer.evidence) == 2


def test_ambiguous_scratch_question_requires_clarification() -> None:
    answer = reasoner().answer(AskRequest(question="Was this scratch already there?"))
    assert answer.status == "clarification_required"
    assert len(answer.choices) == 2
    assert answer.confidence == 0


def test_missing_pickup_view_returns_uncertainty() -> None:
    answer = reasoner().answer(
        AskRequest(question="Was the rear-right bumper scratch already there at pickup?")
    )
    assert answer.status == "uncertain"
    assert answer.confidence_label == "low"
    assert "coverage gap" in (answer.coverage_note or "").lower()
    assert len(answer.evidence) == 1


def test_partial_region_does_not_guess_a_different_car_corner() -> None:
    answer = reasoner().answer(AskRequest(question="Was the right-side scratch already there?"))
    assert answer.status == "clarification_required"
    assert answer.confidence == 0


def test_visible_pickup_scuff_is_supported_by_both_periods() -> None:
    answer = reasoner().answer(
        AskRequest(question="Was the front-left scuff already there at pickup?")
    )
    assert answer.status == "answered"
    assert answer.confidence >= 0.95
    assert {item.asset_id for item in answer.evidence} == {
        "car-pickup-front-left",
        "car-return-front-left",
    }


def test_identity_correction_recomputes_the_chair_answer(tmp_path: Path) -> None:
    repository = WorldRepository(FIXTURE, tmp_path / "state.json")
    statement = "The two black chairs are the same chair under different light."
    repository.remember(
        CorrectionRequest(
            conversation_id="test",
            kind="identity",
            subject_id="home-office",
            statement=statement,
        )
    )
    reasoner_with_memory = TemporalReasoner(repository)

    before = reasoner().answer(AskRequest(question="When did I replace my chair?"))
    after = reasoner_with_memory.answer(
        AskRequest(question="When did I replace my chair?", conversation_id="test")
    )

    # Without the correction the default answer reads the change as a replacement; the
    # correction must change the answer itself, not merely be recalled beside it.
    assert "replace" in before.text.lower() or "not a single day" in before.text
    assert after.learned_memory == statement
    assert after.title != before.title
    assert "replacement" in after.text.lower()
    assert "same chair" in after.text.lower()


def test_follow_up_resolves_a_region_from_conversation_context() -> None:
    history = [
        ConversationTurn(role="user", text="Was this scratch already there?"),
        ConversationTurn(
            role="agent",
            text="Which mark do you mean?",
            subject_id="white-rental-car",
            status="clarification_required",
        ),
    ]
    answer = reasoner().answer(
        AskRequest(
            question="the rear one",
            context_subject_id="white-rental-car",
            history=history,
        )
    )
    assert answer.status == "uncertain"
    assert answer.subject_id == "white-rental-car"
    assert {item.asset_id for item in answer.evidence} == {"car-return-rear-right"}


def test_the_other_one_flips_to_the_opposite_corner() -> None:
    history = [
        ConversationTurn(role="user", text="Was the front-left scuff already there?"),
        ConversationTurn(
            role="agent",
            text="Yes — the front-left scuff was visible at pickup",
            subject_id="white-rental-car",
            status="answered",
        ),
    ]
    answer = reasoner().answer(
        AskRequest(
            question="what about the other one?",
            context_subject_id="white-rental-car",
            history=history,
        )
    )
    assert answer.status == "uncertain"
    assert {item.asset_id for item in answer.evidence} == {"car-return-rear-right"}


def test_bare_follow_up_without_context_stays_ambiguous() -> None:
    answer = reasoner().answer(AskRequest(question="the other one"))
    assert answer.status != "uncertain"
