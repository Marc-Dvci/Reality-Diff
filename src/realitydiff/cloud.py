from __future__ import annotations

import json
from typing import Any

from .config import Settings


class FirestoreStateBackend:
    """Small persistent state adapter for horizontally scaled Cloud Run instances."""

    def __init__(self, project: str) -> None:
        self.project = project
        self._client_instance = None

    def load(self) -> dict[str, list[dict[str, Any]]]:
        client = self._client()
        return {
            "corrections": self._collection(client, "corrections", "created_at", 250),
            "ingestion_runs": self._collection(client, "ingestion_runs", "started_at", 20),
            "uploads": self._collection(client, "uploads", "captured_at", 250),
            "subject_states": self._collection(client, "subject_states", "updated_at", 250),
        }

    def put(self, collection: str, document_id: str, value: dict[str, Any]) -> None:
        self._client().collection(f"realitydiff_{collection}").document(document_id).set(value)

    def delete(self, collection: str, document_id: str) -> None:
        self._client().collection(f"realitydiff_{collection}").document(document_id).delete()

    @staticmethod
    def _collection(client: Any, name: str, order_field: str, limit: int) -> list[dict[str, Any]]:
        query = (
            client.collection(f"realitydiff_{name}")
            .order_by(order_field, direction="DESCENDING")
            .limit(limit)
        )
        return [document.to_dict() for document in query.stream()]

    def _client(self):
        if self._client_instance is None:
            try:
                from google.cloud import firestore
            except ImportError as exc:
                raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc
            self._client_instance = firestore.Client(project=self.project)
        return self._client_instance


class PubSubEventPublisher:
    """Publish non-sensitive pipeline metadata; image bytes stay in Cloud Storage."""

    def __init__(self, project: str, topic: str) -> None:
        self.project = project
        self.topic = topic
        self._client_instance = None

    def publish(self, event: dict[str, Any]) -> str:
        client = self._client()
        topic_path = client.topic_path(self.project, self.topic)
        future = client.publish(
            topic_path,
            json.dumps(event, separators=(",", ":")).encode("utf-8"),
            event_type=str(event.get("event_type", "media.indexed")),
        )
        return str(future.result(timeout=15))

    def _client(self):
        if self._client_instance is None:
            try:
                from google.cloud import pubsub_v1
            except ImportError as exc:
                raise RuntimeError("Install the Google integration: pip install -e '.[google]'") from exc
            self._client_instance = pubsub_v1.PublisherClient()
        return self._client_instance


def build_state_backend(settings: Settings) -> FirestoreStateBackend | None:
    if settings.environment == "production" and settings.google_cloud_project:
        return FirestoreStateBackend(settings.google_cloud_project)
    return None


def build_event_publisher(settings: Settings) -> PubSubEventPublisher | None:
    if settings.environment == "production" and settings.google_cloud_project:
        return PubSubEventPublisher(settings.google_cloud_project, settings.pubsub_topic)
    return None
