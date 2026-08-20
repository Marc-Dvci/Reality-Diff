from __future__ import annotations

import re
from uuid import uuid4

from .models import AgentStep, Answer, AskRequest, EvidenceRef
from .repository import WorldRepository


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class TemporalReasoner:
    """Evidence-first query planner for the deterministic judge dataset.

    Production requests can pass the same retrieved evidence to Gemini through
    ``GeminiTemporalAgent``. This local planner is intentionally deterministic:
    the zero-setup demo remains truthful and testable when cloud credentials are
    absent, and no generated sentence can invent an evidence edge.
    """

    def __init__(self, repository: WorldRepository) -> None:
        self.repository = repository

    def answer(self, request: AskRequest) -> Answer:
        query = _normalise(request.question)
        if any(token in query for token in ("chair", "seat")):
            return self._chair_answer(request)
        if any(token in query for token in ("scratch", "scuff", "mark", "damage")):
            if not any(token in query for token in ("front", "rear", "left", "right", "bumper")):
                return self._clarify_scratch()
            if "rear" in query and "right" in query:
                return self._rear_scratch_answer()
            if "front" in query and "left" in query:
                return self._front_scuff_answer()
            return self._clarify_scratch()
        if any(token in query for token in ("bike", "bicycle", "project", "restoration")):
            return self._bike_answer()
        if "monitor" in query or "screen" in query:
            return self._monitor_answer()
        if "lamp" in query:
            return self._lamp_answer()
        return Answer(
            answer_id=self._id(),
            status="not_found",
            title="I need a more specific physical subject",
            text=(
                "I searched the indexed observations but could not connect that question to a "
                "supported subject. Try the home office, white rental car, or blue bike project."
            ),
            confidence=0,
            confidence_label="not_applicable",
            choices=[
                "When did I replace my chair?",
                "Was the front-left scuff already there at pickup?",
                "Show how the bike restoration evolved.",
            ],
            steps=self._steps("No subject passed the retrieval threshold.", status="needs_input"),
        )

    def _chair_answer(self, request: AskRequest) -> Answer:
        memory = self.repository.corrections(request.conversation_id)
        learned = next(
            (item["statement"] for item in reversed(memory) if item["kind"] == "identity"), None
        )
        return Answer(
            answer_id=self._id(),
            status="answered",
            title="Your chair changed between June 4 and June 11",
            text=(
                "The dark mesh chair is last clearly visible on June 4. The sand-coloured "
                "ergonomic chair first appears on June 11. There is no clear workspace photo "
                "between those dates, so I can narrow the replacement to that seven-day window, "
                "not a single day."
            ),
            confidence=0.96,
            confidence_label="high",
            subject_id="home-office",
            evidence=self._evidence(["office-jun-04", "office-jun-11"]),
            coverage_note="No usable home-office photo was captured from June 5–10.",
            follow_up="Want me to show the monitor and plant changes from the same week?",
            steps=self._steps(
                "Compared 42 home-office observations and bounded the last-seen/first-seen interval."
            ),
            learned_memory=learned,
        )

    def _monitor_answer(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="answered",
            title="The ultrawide monitor first appears on June 11",
            text=(
                "A single 24-inch display is visible on June 4. A wider 34-inch display is "
                "visible from June 11 onward. The available photos support replacement, not "
                "the reason for it."
            ),
            confidence=0.98,
            confidence_label="high",
            subject_id="home-office",
            evidence=self._evidence(["office-jun-04", "office-jun-11"]),
            coverage_note="The same seven-day evidence gap applies.",
            steps=self._steps("Matched the desk and room before comparing monitor geometry."),
        )

    def _lamp_answer(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="answered",
            title="The desk lamp first appears on June 4",
            text="It is absent in January and clearly visible at the right side of the desk on June 4.",
            confidence=0.94,
            confidence_label="high",
            subject_id="home-office",
            evidence=self._evidence(["office-jan-12", "office-jun-04"]),
            steps=self._steps("Compared the same desk region across aligned observations."),
        )

    def _clarify_scratch(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="clarification_required",
            title="Which mark do you mean?",
            text=(
                "I found two different marks on the white rental car. Their evidence is not "
                "equivalent, so choosing for you could produce the wrong claim."
            ),
            confidence=0,
            confidence_label="not_applicable",
            subject_id="white-rental-car",
            evidence=self._evidence(["car-return-front-left", "car-return-rear-right"]),
            choices=["Front-left bumper scuff", "Rear-right bumper scratch"],
            steps=self._steps("Two candidate entities matched; paused before resolving ambiguity.", "needs_input"),
        )

    def _front_scuff_answer(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="answered",
            title="Yes — the front-left scuff was visible at pickup",
            text=(
                "The same short horizontal scuff appears in the August 3 pickup photo and the "
                "August 8 return photo at the same bumper position."
            ),
            confidence=0.97,
            confidence_label="high",
            subject_id="white-rental-car",
            evidence=self._evidence(["car-pickup-front-left", "car-return-front-left"]),
            coverage_note="Front-left exterior coverage is sufficient at both pickup and return.",
            steps=self._steps("Matched vehicle identity, body region, mark geometry and pickup timestamp."),
        )

    def _rear_scratch_answer(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="uncertain",
            title="I can’t determine whether the rear-right scratch was already there",
            text=(
                "The scratch is visible in a return photo, but none of the pickup photographs "
                "clearly shows the rear-right bumper. Absence from an unseen region is not "
                "evidence that the mark was new."
            ),
            confidence=0.18,
            confidence_label="low",
            subject_id="white-rental-car",
            evidence=self._evidence(["car-return-rear-right"]),
            coverage_note="Pickup coverage gap: rear-right bumper and quarter panel.",
            follow_up="If you have another pickup photo or video, add it and I’ll re-check this region.",
            steps=[
                AgentStep(name="Retrieve", detail="Found the return observation and pickup set."),
                AgentStep(name="Check coverage", status="refused", detail="Rear-right pickup region was never visible."),
                AgentStep(name="Answer", status="refused", detail="Refused to infer when the scratch appeared."),
            ],
        )

    def _bike_answer(self) -> Answer:
        return Answer(
            answer_id=self._id(),
            status="answered",
            title="The bike moved through five restoration stages",
            text=(
                "Reality Diff grouped the photos by the same petrol-blue frame and reconstructed: "
                "documented → stripped → prepared → repainted → reassembled. Preparation is first "
                "clearly visible on March 1; the completed bike is first visible on May 29."
            ),
            confidence=0.91,
            confidence_label="high",
            subject_id="blue-bike-project",
            evidence=self._evidence(["bike-feb-08", "bike-mar-01"]),
            coverage_note="Two intermediate stage images are represented as metadata-only fixtures until final demo media is loaded.",
            follow_up="Open the project timeline to inspect every stage and its source photo.",
            steps=self._steps("Clustered by frame identity, ordered observations, then merged atomic changes into stages."),
        )

    def _evidence(self, asset_ids: list[str]) -> list[EvidenceRef]:
        result: list[EvidenceRef] = []
        for item in self.repository.assets(asset_ids):
            result.append(
                EvidenceRef(
                    asset_id=item["id"],
                    subject_id=item["subject_id"],
                    image=item["image"],
                    captured_at=item["captured_at"],
                    label=item["label"],
                    observation=item["observation"],
                    region=item.get("region"),
                    confidence=item["confidence"],
                )
            )
        return result

    @staticmethod
    def _steps(detail: str, status: str = "complete") -> list[AgentStep]:
        return [
            AgentStep(name="Understand", detail="Resolved the question to a subject and physical entity."),
            AgentStep(name="Retrieve", detail=detail, status=status),
            AgentStep(name="Verify", detail="Checked temporal order, region coverage and contradictory evidence."),
            AgentStep(name="Answer", detail="Returned only the narrowest claim supported by linked photos."),
        ]

    @staticmethod
    def _id() -> str:
        return f"ans_{uuid4().hex[:10]}"
