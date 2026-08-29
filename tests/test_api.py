import base64
from copy import deepcopy
from dataclasses import replace
import json

from fastapi.testclient import TestClient
import pytest

from realitydiff.api import app, repository
from realitydiff import api
from realitydiff.storage import LocalMediaStore


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_mutable_demo_state(tmp_path):
    """API mutations in one test must never leak into the judge fixture or another test."""
    original_path = repository._state_path
    original_state = deepcopy(repository._state)
    repository._state_path = tmp_path / "state.json"
    repository._state = {
        "corrections": [],
        "ingestion_runs": [],
        "uploads": [],
        "subject_states": [],
    }
    try:
        yield
    finally:
        repository._state_path = original_path
        repository._state = original_state


def test_health_and_ready() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "reality-diff-api"
    assert client.get("/ready").status_code == 200


def test_bootstrap_is_complete() -> None:
    response = client.get("/api/v1/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["subjects"]) >= 3
    assert len(payload["use_cases"]) == 9


def test_unknown_subject_is_404() -> None:
    response = client.get("/api/v1/subjects/not-real")
    assert response.status_code == 404


def test_web_shell_and_client_asset_are_served() -> None:
    assert "Reality Diff" in client.get("/").text
    javascript = client.get("/app.js")
    assert javascript.status_code == 200
    assert "Evidence-first temporal" in javascript.text


def test_proof_declares_the_recorded_fixture_boundary() -> None:
    response = client.get("/api/v1/proof")
    assert response.status_code == 200
    payload = response.json()
    assert payload["fixture"]["synthetic"] is True
    assert payload["requirements"]["agent_framework"] == "Google ADK"


def test_correction_round_trip_is_conversation_scoped() -> None:
    response = client.post(
        "/api/v1/corrections",
        json={
            "conversation_id": "round-trip",
            "kind": "alias",
            "subject_id": "home-office",
            "statement": "The study means my home office.",
        },
    )
    assert response.status_code == 201
    assert len(client.get("/api/v1/corrections?conversation_id=round-trip").json()) == 1
    assert client.get("/api/v1/corrections?conversation_id=someone-else").json() == []


def test_corrections_persist_across_conversations_for_the_same_owner() -> None:
    # A correction saved in one session (conversation ABC)...
    created = client.post(
        "/api/v1/corrections",
        json={
            "conversation_id": "session-abc",
            "kind": "identity",
            "subject_id": "home-office",
            "statement": "The mesh and ergonomic chairs are the same chair.",
        },
    )
    assert created.status_code == 201
    # ...still shapes the answer after a refresh mints a fresh conversation id, because
    # recall is scoped to the persistent owner, not the conversation.
    answer = client.post(
        "/api/v1/ask",
        json={"question": "When did I replace my chair?", "conversation_id": "session-xyz"},
    ).json()
    assert answer["status"] == "answered"
    assert "same chair" in answer["title"].lower()
    assert answer["learned_memory"]


def test_ingestion_run_reports_recorded_demo_transport() -> None:
    response = client.post(
        "/api/v1/ingestion-runs",
        json={"source": "web_folder", "discovered": 18},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["indexed"] <= payload["discovered"]
    assert payload["transport"] == "recorded_demo"


def test_photo_upload_is_validated_saved_analyzed_and_added_to_gallery(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(api, "media_store", LocalMediaStore(tmp_path / "uploads"))
    image = (api.settings.web_root / "assets" / "gallery" / "living-room.jpg").read_bytes()
    response = client.post(
        "/api/v1/media/analyze",
        data={"source": "web_upload"},
        files=[("files", ("my-living-room.jpg", image, "image/jpeg"))],
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["indexed"] == 1
    assert payload["run"]["transport"] == "local_pending"
    uploaded = payload["items"][0]
    assert "_embedding" not in uploaded
    assert "sha256" not in uploaded
    assert "storage_key" not in uploaded
    assert uploaded["status"] == "queued"
    assert uploaded["analysis"]["pipeline"]["reasoning_model"] == "gemini-3.7-flash"
    assert client.get(f"/api/v1/media/{uploaded['id']}").content == image
    # The owner cookie set on upload flows back on bootstrap, so the gallery is this
    # visitor's own view of their imports.
    assert client.get("/api/v1/bootstrap").json()["gallery"][0]["id"] == uploaded["id"]

    duplicate = client.post(
        "/api/v1/media/analyze",
        data={"source": "web_upload"},
        files=[("files", ("same-bytes-again.jpg", image, "image/jpeg"))],
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["items"] == []
    assert duplicate.json()["run"]["deduplicated"] == 1
    assert duplicate.json()["duplicates"][0]["existing_media_id"] == uploaded["id"]

    deleted = client.delete(f"/api/v1/media/{uploaded['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/media/{uploaded['id']}").status_code == 404
    assert not client.get("/api/v1/bootstrap").json()["gallery"][0].get("imported")


def test_uploads_are_isolated_between_anonymous_visitors(monkeypatch, tmp_path) -> None:
    """The reviewer's two-profile test: visitor B must never reach visitor A's photo.

    Each TestClient keeps its own cookie jar, so the two clients receive two distinct
    anonymous owner tokens exactly as two clean browser profiles would.
    """
    monkeypatch.setattr(api, "media_store", LocalMediaStore(tmp_path / "uploads"))
    image = (api.settings.web_root / "assets" / "gallery" / "living-room.jpg").read_bytes()

    visitor_a = TestClient(app)
    visitor_b = TestClient(app)

    uploaded = visitor_a.post(
        "/api/v1/media/analyze",
        data={"source": "web_upload"},
        files=[("files", ("secret.jpg", image, "image/jpeg"))],
    ).json()["items"][0]
    media_id = uploaded["id"]

    # A sees and can read its own upload.
    assert visitor_a.get(f"/api/v1/media/{media_id}").status_code == 200
    assert any(item["id"] == media_id for item in visitor_a.get("/api/v1/bootstrap").json()["gallery"])

    # B cannot discover it in the gallery, cannot fetch the bytes, cannot delete it.
    assert all(
        item.get("id") != media_id for item in visitor_b.get("/api/v1/bootstrap").json()["gallery"]
    )
    assert visitor_b.get(f"/api/v1/media/{media_id}").status_code == 404
    assert visitor_b.delete(f"/api/v1/media/{media_id}").status_code == 404

    # A's photo survived B's probing untouched.
    assert visitor_a.get(f"/api/v1/media/{media_id}").status_code == 200


def test_corrections_are_isolated_between_anonymous_visitors() -> None:
    visitor_a = TestClient(app)
    visitor_b = TestClient(app)
    visitor_a.post(
        "/api/v1/corrections",
        json={"conversation_id": "judge-demo", "kind": "alias", "statement": "The study is my office."},
    )
    assert len(visitor_a.get("/api/v1/corrections?conversation_id=judge-demo").json()) == 1
    # B shares the default conversation_id but must not see A's correction.
    assert visitor_b.get("/api/v1/corrections?conversation_id=judge-demo").json() == []


def test_photo_upload_rejects_content_type_spoofing() -> None:
    response = client.post(
        "/api/v1/media/analyze",
        data={"source": "web_upload"},
        files=[("files", ("not-a-photo.jpg", b"not really an image", "image/jpeg"))],
    )
    assert response.status_code == 415


def _pubsub_envelope(media_id: str, owner_id: str) -> dict:
    event = {"event_type": "media.indexed", "media_id": media_id, "owner_id": owner_id}
    data = base64.b64encode(json.dumps(event).encode("utf-8")).decode("utf-8")
    return {"message": {"data": data}, "subscription": "reality-diff-ingestion-worker"}


def test_pipeline_push_endpoint_is_disabled_until_configured() -> None:
    # No pipeline token in the demo settings: the async stage is closed, not open.
    response = client.post("/api/v1/pipeline/media-indexed", json=_pubsub_envelope("m1", "o1"))
    assert response.status_code == 503


def test_pipeline_push_endpoint_requires_the_shared_token(monkeypatch) -> None:
    monkeypatch.setattr(api, "settings", replace(api.settings, pipeline_token="pipe-secret"))
    repository.add_upload(
        {
            "id": "m1",
            "owner_id": "owner-a",
            "status": "analyzed",
            "captured_at": "2026-06-04T09:00:00Z",
            "image": "/api/v1/media/m1",
            "analysis": {"candidate_subject": "Home office", "description": "Desk with a lamp."},
        }
    )
    envelope = _pubsub_envelope("m1", "owner-a")

    # A push without the token is rejected even though the service allows public invoke.
    assert client.post("/api/v1/pipeline/media-indexed", json=envelope).status_code == 403

    # With the token, the async state-construction stage runs and commits subject state.
    response = client.post("/api/v1/pipeline/media-indexed?token=pipe-secret", json=envelope)
    assert response.status_code == 200
    assert response.json()["status"] == "consolidated"
    assert repository.subject_states("owner-a")[0]["subject"] == "Home office"


def test_pipeline_push_endpoint_acknowledges_malformed_messages(monkeypatch) -> None:
    monkeypatch.setattr(api, "settings", replace(api.settings, pipeline_token="pipe-secret"))
    response = client.post(
        "/api/v1/pipeline/media-indexed?token=pipe-secret",
        json={"message": {"data": "!!not-base64!!"}},
    )
    # Acknowledged (2xx) so a permanently broken message cannot loop to the dead-letter topic.
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_ask_prefers_the_adk_orchestrator_when_it_is_active(monkeypatch) -> None:
    from realitydiff.models import AgentStep, Answer

    class StubOrchestrator:
        async def answer(self, _request):
            return Answer(
                answer_id="ans_adk",
                status="answered",
                title="From the ADK partner",
                text="Routed through the collaborative partner.",
                confidence=0.9,
                confidence_label="high",
                steps=[AgentStep(name="Orchestrate", detail="Google ADK led the turn.")],
            )

    monkeypatch.setattr(api, "orchestrator", StubOrchestrator())
    payload = client.post("/api/v1/ask", json={"question": "When did I replace my chair?"}).json()
    assert payload["title"] == "From the ADK partner"
    assert payload["steps"][0]["name"] == "Orchestrate"


def test_ask_falls_back_to_the_grounded_pipeline_when_orchestrator_defers(monkeypatch) -> None:
    class DeferringOrchestrator:
        async def answer(self, _request):
            return None

    monkeypatch.setattr(api, "orchestrator", DeferringOrchestrator())
    payload = client.post("/api/v1/ask", json={"question": "When did I replace my chair?"}).json()
    # The deterministic evidence planner still answers, so the demo never regresses.
    assert payload["status"] == "answered"
    assert len(payload["evidence"]) == 2
