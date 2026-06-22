"""Tests for PROMPT 10 (synthesis) and PROMPT 12 (review workflow)."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.models import (
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    SignalType,
)
from app.services.store import store

client = TestClient(app)
SAMPLE_DIR = Path(__file__).parents[2] / "sample_data"


@pytest.fixture(autouse=True)
def reset():
    store.reset()
    yield
    store.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_debrief(
    text: str = "Jordan showed strong statistical reasoning without any prompting.",
    interviewer: str = "Alice",
) -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=text,
    )


def make_valid_signal(debrief: InterviewDebrief, cid: str = "stat") -> ExtractedSignal:
    quote = "strong statistical reasoning"
    idx = debrief.raw_text.find(quote)
    assert idx != -1, "Quote must exist in debrief text"
    span = EvidenceSpan(
        source_debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
        start_char=idx,
        end_char=idx + len(quote),
        quoted_text=quote,
    )
    return ExtractedSignal.model_construct(
        signal_id=str(uuid4()),
        debrief_id=debrief.debrief_id,
        competency_id=cid,
        signal_type=SignalType.POSITIVE,
        claim="Candidate demonstrated strong statistical reasoning.",
        evidence_spans=[span],
        confidence=0.85,
        is_vague=False,
        is_unsupported=False,
        extractor_version="baseline-v1",
    )


def make_synthesis_body(signals, debriefs, rubric_dict: dict) -> dict:
    return {
        "candidate_name": "Jordan Lee",
        "candidate_id": "C-001",
        "role_title": "Data Scientist",
        "role_id": "R-001",
        "signals": signals,
        "rubric": rubric_dict,
        "debriefs": debriefs,
    }


# ---------------------------------------------------------------------------
# PROMPT 10: Synthesis endpoint
# ---------------------------------------------------------------------------


class TestSynthesisEndpoint:
    @pytest.fixture
    def rubric_dict(self):
        return json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text())

    @pytest.fixture
    def valid_payload(self, rubric_dict):
        debrief = make_debrief()
        signal = make_valid_signal(debrief, "stat_reasoning")
        return make_synthesis_body(
            signals=[json.loads(signal.model_dump_json())],
            debriefs=[
                {
                    "debrief_id": debrief.debrief_id,
                    "candidate_id": debrief.candidate_id,
                    "interviewer_name": debrief.interviewer_name,
                    "raw_text": debrief.raw_text,
                }
            ],
            rubric_dict=rubric_dict,
        )

    def test_returns_201(self, valid_payload):
        resp = client.post("/synthesize", json=valid_payload)
        assert resp.status_code == 201, resp.text

    def test_response_has_report_id(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        assert "report_id" in data
        assert len(data["report_id"]) > 0

    def test_no_hire_recommendation_field(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        forbidden = {"recommendation", "hire_decision", "hire", "no_hire", "should_hire"}
        assert forbidden.isdisjoint(set(data.keys()))

    def test_executive_summary_present(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        assert len(data["executive_summary"]) > 20

    def test_executive_summary_has_no_hire_recommendation(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        summary = data["executive_summary"].lower()
        # Must not contain affirmative recommendation language
        forbidden = [
            "recommend hiring",
            "recommend this candidate",
            "strong hire",
            "should be hired",
        ]
        assert not any(phrase in summary for phrase in forbidden)

    def test_competency_assessments_present(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        assert isinstance(data["competency_assessments"], list)
        assert len(data["competency_assessments"]) > 0

    def test_citation_validity_rate_is_1(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        assert data["citation_validity_rate"] == 1.0

    def test_empty_debriefs_returns_400(self, rubric_dict):
        body = {
            "candidate_name": "Jordan",
            "role_title": "DS",
            "signals": [],
            "rubric": rubric_dict,
            "debriefs": [],
        }
        resp = client.post("/synthesize", json=body)
        assert resp.status_code == 400

    def test_invalid_span_blocks_synthesis(self, rubric_dict):
        """Synthesis must return 422 if any evidence span fails verification."""
        debrief = make_debrief()
        # Create a signal with an invented (hallucinated) quote
        bad_span = EvidenceSpan.model_construct(
            span_id=str(uuid4()),
            source_debrief_id=debrief.debrief_id,
            interviewer_name=debrief.interviewer_name,
            start_char=0,
            end_char=30,
            quoted_text="This text does not appear anywhere.",
        )
        bad_signal = ExtractedSignal.model_construct(
            signal_id=str(uuid4()),
            debrief_id=debrief.debrief_id,
            competency_id="stat_reasoning",
            signal_type=SignalType.POSITIVE,
            claim="Candidate had strong reasoning ability overall.",
            evidence_spans=[bad_span],
            confidence=0.80,
            is_vague=False,
            is_unsupported=True,
            extractor_version="test-v1",
        )
        body = make_synthesis_body(
            signals=[json.loads(bad_signal.model_dump_json())],
            debriefs=[
                {
                    "debrief_id": debrief.debrief_id,
                    "candidate_id": debrief.candidate_id,
                    "interviewer_name": debrief.interviewer_name,
                    "raw_text": debrief.raw_text,
                }
            ],
            rubric_dict=rubric_dict,
        )
        resp = client.post("/synthesize", json=body)
        assert resp.status_code == 422

    def test_report_saved_to_store(self, valid_payload):
        data = client.post("/synthesize", json=valid_payload).json()
        report_id = data["report_id"]
        stored = store.get_report(report_id)
        assert stored is not None
        assert stored.report_id == report_id


# ---------------------------------------------------------------------------
# PROMPT 12: Review workflow
# ---------------------------------------------------------------------------


class TestReviewWorkflow:
    @pytest.fixture
    def rubric_dict(self):
        return json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text())

    @pytest.fixture
    def report_id(self, rubric_dict):
        debrief = make_debrief()
        signal = make_valid_signal(debrief, "stat_reasoning")
        payload = make_synthesis_body(
            signals=[json.loads(signal.model_dump_json())],
            debriefs=[
                {
                    "debrief_id": debrief.debrief_id,
                    "candidate_id": debrief.candidate_id,
                    "interviewer_name": debrief.interviewer_name,
                    "raw_text": debrief.raw_text,
                }
            ],
            rubric_dict=rubric_dict,
        )
        data = client.post("/synthesize", json=payload).json()
        return data["report_id"]

    def test_get_report_returns_200(self, report_id):
        resp = client.get(f"/review/{report_id}")
        assert resp.status_code == 200

    def test_get_nonexistent_report_returns_404(self):
        resp = client.get("/review/does-not-exist")
        assert resp.status_code == 404

    def test_patch_reviewer_notes(self, report_id):
        patch = {
            "final_reviewer_notes": "Strong candidate for data work.",
            "reviewer_name": "Sarah",
        }
        resp = client.patch(f"/review/{report_id}", json=patch)
        assert resp.status_code == 200
        data = resp.json()
        assert data["final_reviewer_notes"] == "Strong candidate for data work."
        assert data["reviewer_name"] == "Sarah"

    def test_patch_approval_sets_reviewed_at(self, report_id):
        patch = {"reviewer_approved": True, "reviewer_name": "Sarah"}
        resp = client.patch(f"/review/{report_id}", json=patch)
        assert resp.status_code == 200
        data = resp.json()
        assert data["reviewer_approved"] is True
        assert data["reviewed_at"] is not None

    def test_patch_nonexistent_report_returns_404(self):
        resp = client.patch("/review/does-not-exist", json={"reviewer_approved": True})
        assert resp.status_code == 404

    def test_report_not_approved_by_default(self, report_id):
        data = client.get(f"/review/{report_id}").json()
        assert data["reviewer_approved"] is False

    def test_reviewer_notes_empty_by_default(self, report_id):
        data = client.get(f"/review/{report_id}").json()
        assert data["final_reviewer_notes"] == ""

    def test_patch_is_idempotent(self, report_id):
        patch = {
            "reviewer_name": "Sarah",
            "reviewer_approved": True,
            "final_reviewer_notes": "Looks good.",
        }
        client.patch(f"/review/{report_id}", json=patch)
        resp = client.patch(f"/review/{report_id}", json=patch)
        assert resp.status_code == 200

    def test_report_no_hire_fields_after_patch(self, report_id):
        client.patch(f"/review/{report_id}", json={"reviewer_approved": True, "reviewer_name": "Sarah"})
        data = client.get(f"/review/{report_id}").json()
        forbidden = {"recommendation", "hire_decision", "hire", "no_hire"}
        assert forbidden.isdisjoint(set(data.keys()))
