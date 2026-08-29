from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

from .repository import WorldRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class IngestionConsolidator:
    """The asynchronous state-construction stage of the ingestion pipeline.

    The upload request path stops as soon as a single photo is indexed: it stores the
    original, runs triage and the visible-facts observation, embeds it, and publishes a
    ``media.indexed`` event. Turning many indexed observations into subject-level *state* is
    deliberately deferred to this stage, which a Pub/Sub push subscription drives out of
    band. It groups a subject's observations, orders them by capture time, and proposes the
    candidate transitions between consecutive observations, then commits that consolidation
    to Firestore. This is the "Commit / build a semantic world" box in the architecture
    diagram, and it lets the request stay fast while the heavier cross-photo work scales on
    its own retry- and dead-letter-backed subscription.

    ``consolidate`` is pure with respect to transport: the Pub/Sub envelope is decoded by
    :func:`decode_pubsub_event`, so the same logic is exercised by unit tests and by the
    live push endpoint.
    """

    def __init__(self, repository: WorldRepository) -> None:
        self.repository = repository

    def consolidate(self, media_id: str, owner_id: str | None) -> dict[str, Any]:
        # A different Cloud Run instance may hold the upload; reload the authoritative
        # state before reading so the just-indexed photo and its siblings are visible.
        self.repository.refresh()
        record = self.repository.upload(media_id, owner_id)
        if record is None:
            return {"status": "skipped", "reason": "media_not_found", "media_id": media_id}

        analysis = record.get("analysis") or {}
        subject = str(analysis.get("candidate_subject") or "Unsorted")
        if record.get("status") != "analyzed" or subject == "Unsorted":
            return {
                "status": "deferred",
                "reason": "not_yet_analyzed",
                "media_id": media_id,
                "subject": subject,
            }

        observations = self._subject_observations(owner_id, subject)
        events = _propose_events(observations)
        state = {
            "state_id": _state_id(owner_id, subject),
            "owner_id": owner_id,
            "subject": subject,
            "observation_count": len(observations),
            "observations": [_observation_summary(item) for item in observations],
            "proposed_events": events,
            "trigger_media_id": media_id,
            "updated_at": _now(),
        }
        self.repository.record_subject_state(state)
        return {
            "status": "consolidated",
            "subject": subject,
            "observation_count": len(observations),
            "events_proposed": len(events),
        }

    def _subject_observations(self, owner_id: str | None, subject: str) -> list[dict[str, Any]]:
        owned = self.repository.uploads_for_reasoning(owner_id)
        matching = [
            item
            for item in owned
            if item.get("status") == "analyzed"
            and str((item.get("analysis") or {}).get("candidate_subject") or "") == subject
        ]
        return sorted(matching, key=lambda item: str(item.get("captured_at") or ""))


def _observation_summary(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("analysis") or {}
    return {
        "media_id": item.get("id"),
        "captured_at": item.get("captured_at"),
        "description": analysis.get("description"),
    }


def _propose_events(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One candidate transition per pair of consecutive observations at distinct times."""
    events: list[dict[str, Any]] = []
    for earlier, later in zip(observations, observations[1:]):
        if str(earlier.get("captured_at")) == str(later.get("captured_at")):
            continue
        events.append(
            {
                "kind": "state_change_candidate",
                "from_media_id": earlier.get("id"),
                "to_media_id": later.get("id"),
                "from_captured_at": earlier.get("captured_at"),
                "to_captured_at": later.get("captured_at"),
            }
        )
    return events


def _state_id(owner_id: str | None, subject: str) -> str:
    return f"{owner_id or 'anonymous'}::{subject}"


def decode_pubsub_event(envelope: Any) -> dict[str, Any] | None:
    """Decode a Pub/Sub push envelope into the original event dict, or ``None`` if malformed.

    A push delivery is ``{"message": {"data": base64(json), ...}, "subscription": ...}``.
    Attributes are merged in so ``owner_id`` survives whether it was sent in the payload or
    as a message attribute.
    """
    if not isinstance(envelope, dict):
        return None
    message = envelope.get("message")
    if not isinstance(message, dict):
        return None
    data = message.get("data")
    event: dict[str, Any] = {}
    if isinstance(data, str) and data:
        try:
            event = json.loads(base64.b64decode(data).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
    if not isinstance(event, dict):
        return None
    attributes = message.get("attributes")
    if isinstance(attributes, dict):
        for key, value in attributes.items():
            event.setdefault(key, value)
    if not event.get("media_id"):
        return None
    return event


def build_consolidator(repository: WorldRepository) -> IngestionConsolidator:
    return IngestionConsolidator(repository)
