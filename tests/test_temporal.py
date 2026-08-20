from pathlib import Path

from realitydiff.models import AskRequest, CorrectionRequest
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


def test_explicit_correction_persists_and_is_recalled(tmp_path: Path) -> None:
    repository = WorldRepository(FIXTURE, tmp_path / "state.json")
    repository.remember(
        CorrectionRequest(
            conversation_id="test",
            kind="identity",
            subject_id="home-office",
            statement="The two black chairs are the same chair under different light.",
        )
    )
    answer = TemporalReasoner(repository).answer(
        AskRequest(question="When did I replace my chair?", conversation_id="test")
    )
    assert answer.learned_memory == "The two black chairs are the same chair under different light."
