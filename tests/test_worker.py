import base64
import json
from pathlib import Path

from realitydiff.repository import WorldRepository
from realitydiff.worker import IngestionConsolidator, decode_pubsub_event


FIXTURE = Path(__file__).parents[1] / "web" / "fixtures" / "demo.json"


def _upload(media_id: str, owner: str, subject: str, captured_at: str) -> dict:
    return {
        "id": media_id,
        "owner_id": owner,
        "status": "analyzed",
        "captured_at": captured_at,
        "image": f"/api/v1/media/{media_id}",
        "analysis": {
            "candidate_subject": subject,
            "description": f"Observation for {subject} at {captured_at}.",
        },
    }


def test_consolidation_builds_ordered_subject_state_scoped_to_owner() -> None:
    repository = WorldRepository(FIXTURE)
    # Two observations of the same subject for owner A, plus a same-subject photo owned by B.
    repository.add_upload(_upload("a2", "owner-a", "Balcony pothos", "2026-06-11T09:00:00Z"))
    repository.add_upload(_upload("a1", "owner-a", "Balcony pothos", "2026-06-04T09:00:00Z"))
    repository.add_upload(_upload("b1", "owner-b", "Balcony pothos", "2026-06-05T09:00:00Z"))

    consolidator = IngestionConsolidator(repository)
    result = consolidator.consolidate("a2", "owner-a")

    assert result["status"] == "consolidated"
    assert result["subject"] == "Balcony pothos"
    # Owner B's photo of the same subject is excluded.
    assert result["observation_count"] == 2
    assert result["events_proposed"] == 1

    state = repository.subject_states("owner-a")[0]
    # Observations are ordered by capture time, so the earlier photo comes first.
    assert [item["media_id"] for item in state["observations"]] == ["a1", "a2"]
    event = state["proposed_events"][0]
    assert event["from_media_id"] == "a1" and event["to_media_id"] == "a2"

    # The consolidation is private to owner A.
    assert repository.subject_states("owner-b") == []


def test_consolidation_skips_media_that_belongs_to_a_different_owner() -> None:
    repository = WorldRepository(FIXTURE)
    repository.add_upload(_upload("a1", "owner-a", "Home office", "2026-06-04T09:00:00Z"))
    consolidator = IngestionConsolidator(repository)

    # The correct owner consolidates; a foreign owner sees nothing to consolidate.
    assert consolidator.consolidate("a1", "owner-a")["status"] == "consolidated"
    assert consolidator.consolidate("a1", "owner-b")["status"] == "skipped"


def test_decode_pubsub_envelope_round_trips_and_rejects_malformed() -> None:
    event = {"event_type": "media.indexed", "media_id": "m1", "owner_id": "owner-a"}
    data = base64.b64encode(json.dumps(event).encode("utf-8")).decode("utf-8")
    envelope = {"message": {"data": data}, "subscription": "reality-diff-ingestion-worker"}
    assert decode_pubsub_event(envelope) == event

    assert decode_pubsub_event({"message": {"data": "!!not-base64!!"}}) is None
    assert decode_pubsub_event({"message": {}}) is None
    assert decode_pubsub_event({}) is None
