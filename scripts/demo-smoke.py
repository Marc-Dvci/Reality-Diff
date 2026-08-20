"""Smoke-test a running Reality Diff judge URL using only Python's standard library."""

from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen


BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8091").rstrip("/")


def request(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    value = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urlopen(value, timeout=5) as response:  # noqa: S310 -- caller chooses the smoke-test URL
        if response.status >= 300:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.load(response)


health = request("/health")
ready = request("/ready")
bootstrap = request("/api/v1/bootstrap")
proof = request("/api/v1/proof")
chair = request(
    "/api/v1/ask",
    {"question": "When did I replace my chair?", "conversation_id": "smoke"},
)
missing_view = request(
    "/api/v1/ask",
    {
        "question": "Was the rear-right scratch already there at pickup?",
        "conversation_id": "smoke",
    },
)

assert health["status"] == "ok"
assert ready["status"] == "ready"
assert len(bootstrap["subjects"]) >= 3
assert proof["fixture"]["synthetic"] is True
assert chair["status"] == "answered" and len(chair["evidence"]) == 2
assert missing_view["status"] == "uncertain" and missing_view["confidence_label"] == "low"

print(
    json.dumps(
        {
            "url": BASE_URL,
            "status": "pass",
            "subjects": len(bootstrap["subjects"]),
            "chair_evidence": len(chair["evidence"]),
            "coverage_refusal": missing_view["coverage_note"],
        },
        indent=2,
    )
)
