from copy import deepcopy

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
    repository._state = {"corrections": [], "ingestion_runs": [], "uploads": []}
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
    assert repository.bootstrap()["gallery"][0]["id"] == uploaded["id"]

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
    assert not repository.bootstrap()["gallery"][0].get("imported")


def test_photo_upload_rejects_content_type_spoofing() -> None:
    response = client.post(
        "/api/v1/media/analyze",
        data={"source": "web_upload"},
        files=[("files", ("not-a-photo.jpg", b"not really an image", "image/jpeg"))],
    )
    assert response.status_code == 415
