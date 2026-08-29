from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    subject_id: str
    image: str
    captured_at: str
    label: str
    observation: str
    region: str | None = None
    confidence: float = Field(ge=0, le=1)


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["user", "agent"]
    text: str = Field(default="", max_length=1200)
    subject_id: str | None = None
    status: str | None = None


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=500)
    conversation_id: str = Field(default="judge-demo", min_length=1, max_length=100)
    context_subject_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=40)


class AgentStep(BaseModel):
    name: str
    status: Literal["complete", "needs_input", "refused"] = "complete"
    detail: str


class Answer(BaseModel):
    answer_id: str
    status: Literal["answered", "uncertain", "clarification_required", "not_found"]
    title: str
    text: str
    confidence: float = Field(ge=0, le=1)
    confidence_label: Literal["high", "medium", "low", "not_applicable"]
    subject_id: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    coverage_note: str | None = None
    follow_up: str | None = None
    choices: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    learned_memory: str | None = None


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(default="judge-demo", min_length=1, max_length=100)
    kind: Literal["identity", "alias", "significance", "evidence", "category"]
    subject_id: str | None = None
    statement: str = Field(min_length=3, max_length=500)


class Correction(BaseModel):
    correction_id: str
    conversation_id: str
    kind: str
    subject_id: str | None
    statement: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


class IngestionRequest(BaseModel):
    source: Literal["android_mediastore", "android_picker", "web_folder", "web_upload"]
    discovered: int = Field(default=18, ge=0, le=10_000)
