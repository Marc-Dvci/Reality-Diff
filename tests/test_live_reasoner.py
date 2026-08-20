from pathlib import Path

from realitydiff.live_reasoner import GeminiTemporalReasoner
from realitydiff.models import AskRequest
from realitydiff.repository import WorldRepository


FIXTURE = Path(__file__).parents[1] / "web" / "fixtures" / "demo.json"


class FakeAnalyzer:
    def embed_text(self, _text: str) -> list[float]:
        return [1.0, 0.0]

    def reason_about_observations(self, _question, observations, _memory):
        return {
            "status": "answered",
            "title": "The plant gained a new leaf",
            "text": "The two dated observations show one additional visible leaf.",
            "confidence": 0.86,
            "confidence_label": "high",
            "subject_id": "Window plant",
            "evidence_ids": [observations[0]["id"], "invented-id"],
            "coverage_note": "The pot and upper foliage are visible in both photos.",
            "follow_up": "Show the two sources?",
            "choices": [],
        }


def test_live_reasoner_retrieves_and_rejects_invented_evidence_ids() -> None:
    repository = WorldRepository(FIXTURE)
    repository.add_upload(
        {
            "id": "upload_real",
            "image": "/api/v1/media/upload_real",
            "captured_at": "2026-08-01T10:00:00+02:00",
            "capture_time_source": "exif",
            "title": "Window plant",
            "status": "analyzed",
            "_embedding": [1.0, 0.0],
            "analysis": {
                "candidate_subject": "Window plant",
                "scene_type": "plant",
                "description": "A potted plant has seven visible leaves.",
                "entities": [{"name": "plant", "confidence": 0.9}],
                "quality": {"usable": True, "coverage_note": "Pot and foliage visible."},
            },
        }
    )

    answer = GeminiTemporalReasoner(repository, FakeAnalyzer()).answer(  # type: ignore[arg-type]
        AskRequest(question="How did my window plant change?")
    )

    assert answer is not None
    assert answer.status == "answered"
    assert [item.asset_id for item in answer.evidence] == ["upload_real"]
    assert len(answer.steps) == 3
