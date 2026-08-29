from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from .models import Correction, CorrectionRequest


class WorldRepository:
    """Thread-safe demo repository with an explicit persistence seam.

    The hosted sample surface reads an immutable synthetic fixture. Imports,
    corrections, and ingestion runs are written atomically to local JSON or
    persisted through the Firestore state backend without changing clients.
    """

    def __init__(
        self,
        fixture_path: Path,
        state_path: Path | None = None,
        cloud_state: Any | None = None,
    ) -> None:
        self._fixture_path = fixture_path
        self._state_path = state_path
        self._cloud_state = cloud_state
        self._lock = RLock()
        self._world = json.loads(fixture_path.read_text(encoding="utf-8"))
        self._state: dict[str, Any] = {
            "corrections": [],
            "ingestion_runs": [],
            "uploads": [],
            "subject_states": [],
        }
        if cloud_state is not None:
            self._state.update(cloud_state.load())
        elif state_path and state_path.is_file():
            try:
                loaded = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._state.update(loaded)
            except (OSError, json.JSONDecodeError):
                # A damaged demo-state file must not hide the immutable fixture.
                # It is ignored and replaced on the next valid mutation.
                pass
        for key in ("corrections", "ingestion_runs", "uploads", "subject_states"):
            if not isinstance(self._state.get(key), list):
                self._state[key] = []

    def refresh(self) -> None:
        """Re-read cloud state so a worker sees writes made by other Cloud Run instances.

        Each instance keeps an in-process cache primed at startup; the asynchronous
        consolidation stage may run on a different instance than the upload, so it reloads
        the authoritative Firestore state before it reads. A no-op in local mode.
        """
        if self._cloud_state is None:
            return
        with self._lock:
            self._state.update(self._cloud_state.load())

    def bootstrap(self, owner_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            payload = deepcopy(self._world)
            payload["memory"]["corrections"] = [
                _public_correction(item)
                for item in self._state["corrections"]
                if item.get("owner_id") == owner_id
            ]
            payload["ingestion_runs"] = deepcopy(self._state["ingestion_runs"])
            uploads = [
                _public_upload(item)
                for item in self._state.get("uploads", [])
                if item.get("owner_id") == owner_id
            ]
            payload.setdefault("gallery", [])
            payload["gallery"] = uploads + payload["gallery"]
            payload["summary"]["photos_indexed"] += len(uploads)
            payload["summary"]["photos_seen"] += len(uploads)
            return payload

    def subjects(self) -> list[dict[str, Any]]:
        return deepcopy(self._world["subjects"])

    def subject(self, subject_id: str) -> dict[str, Any] | None:
        return next(
            (deepcopy(item) for item in self._world["subjects"] if item["id"] == subject_id),
            None,
        )

    def asset(self, asset_id: str) -> dict[str, Any] | None:
        return next(
            (deepcopy(item) for item in self._world["assets"] if item["id"] == asset_id),
            None,
        )

    def assets(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        wanted = set(asset_ids)
        return [deepcopy(item) for item in self._world["assets"] if item["id"] in wanted]

    def remember(self, request: CorrectionRequest) -> Correction:
        correction = Correction(
            correction_id=f"mem_{uuid4().hex[:10]}",
            conversation_id=request.conversation_id,
            kind=request.kind,
            subject_id=request.subject_id,
            statement=request.statement.strip(),
            owner_id=request.owner_id,
        )
        with self._lock:
            self._state["corrections"].append(correction.model_dump())
            self._persist_item("corrections", correction.correction_id, correction.model_dump())
        return correction

    def corrections(
        self, conversation_id: str | None = None, owner_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            values = deepcopy(self._state["corrections"])

        def keep(item: dict[str, Any]) -> bool:
            if conversation_id is not None and item["conversation_id"] != conversation_id:
                return False
            if owner_id is not None and item.get("owner_id") != owner_id:
                return False
            return True

        return [_public_correction(item) for item in values if keep(item)]

    def add_ingestion_run(self, run: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._state["ingestion_runs"].insert(0, deepcopy(run))
            self._state["ingestion_runs"] = self._state["ingestion_runs"][:20]
            self._persist_item("ingestion_runs", str(run["id"]), run)
        return deepcopy(run)

    def add_upload(self, upload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._state.setdefault("uploads", [])
            self._state["uploads"].insert(0, deepcopy(upload))
            self._state["uploads"] = self._state["uploads"][:250]
            self._persist_item("uploads", str(upload["id"]), upload)
        return _public_upload(upload)

    def upload_by_hash(self, digest: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            return next(
                (
                    _public_upload(item)
                    for item in self._state.get("uploads", [])
                    if item.get("sha256") == digest and item.get("owner_id") == owner_id
                ),
                None,
            )

    def uploads_for_reasoning(
        self, owner_id: str | None = None, limit: int = 250
    ) -> list[dict[str, Any]]:
        with self._lock:
            owned = [
                item
                for item in self._state.get("uploads", [])
                if item.get("owner_id") == owner_id
            ]
            return deepcopy(owned[:limit])

    def upload(self, upload_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            return next(
                (
                    deepcopy(item)
                    for item in self._state.get("uploads", [])
                    if item.get("id") == upload_id and item.get("owner_id") == owner_id
                ),
                None,
            )

    def delete_upload(self, upload_id: str, owner_id: str | None = None) -> bool:
        with self._lock:
            uploads = self._state.get("uploads", [])
            retained = [
                item
                for item in uploads
                if not (item.get("id") == upload_id and item.get("owner_id") == owner_id)
            ]
            if len(retained) == len(uploads):
                return False
            self._state["uploads"] = retained
            if self._cloud_state is not None:
                self._cloud_state.delete("uploads", upload_id)
            else:
                self._persist()
            return True

    def record_subject_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Upsert one owner+subject consolidation produced by the async stage."""
        state_id = str(state["state_id"])
        with self._lock:
            self._state.setdefault("subject_states", [])
            retained = [
                item for item in self._state["subject_states"] if item.get("state_id") != state_id
            ]
            retained.insert(0, deepcopy(state))
            self._state["subject_states"] = retained[:250]
            self._persist_item("subject_states", state_id, state)
        return deepcopy(state)

    def subject_states(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                deepcopy(item)
                for item in self._state.get("subject_states", [])
                if owner_id is None or item.get("owner_id") == owner_id
            ]

    def _persist(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        temporary.replace(self._state_path)

    def _persist_item(self, collection: str, document_id: str, value: dict[str, Any]) -> None:
        if self._cloud_state is not None:
            self._cloud_state.put(collection, document_id, deepcopy(value))
        else:
            self._persist()


def _public_upload(upload: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(upload)
    for private_field in ("_embedding", "sha256", "storage_key", "owner_id"):
        value.pop(private_field, None)
    return value


def _public_correction(correction: dict[str, Any]) -> dict[str, Any]:
    value = deepcopy(correction)
    value.pop("owner_id", None)
    return value
