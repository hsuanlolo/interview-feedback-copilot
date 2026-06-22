"""Tests for PROMPT 8: coverage map analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.models import (
    Competency,
    CoverageStatus,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)
from app.services.coverage_analyzer import analyze_coverage
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


def make_debrief(interviewer: str = "Alice") -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=f"This is a detailed debrief written by {interviewer} covering several competencies in depth.",
    )


def make_competency(name: str = "Statistical Reasoning", cid: str = "stat") -> Competency:
    return Competency(
        competency_id=cid,
        name=name,
        description=f"Tests {name}.",
        positive_indicators=["strong", "clear"],
        negative_indicators=["weak", "poor"],
    )


def make_rubric(competencies: list[Competency] | None = None) -> RoleRubric:
    return RoleRubric(
        role_title="Data Scientist",
        competencies=competencies or [make_competency()],
    )


def make_signal(
    debrief: InterviewDebrief,
    competency_id: str,
    signal_type: SignalType,
    confidence: float = 0.80,
    is_vague: bool = False,
) -> ExtractedSignal:
    idx = debrief.raw_text.find("debrief")
    return ExtractedSignal.model_construct(
        signal_id=str(uuid4()),
        debrief_id=debrief.debrief_id,
        competency_id=competency_id,
        signal_type=signal_type,
        claim="Candidate demonstrated the competency clearly.",
        evidence_spans=[
            __import__("app.schemas.models", fromlist=["EvidenceSpan"]).EvidenceSpan.model_construct(
                span_id=str(uuid4()),
                source_debrief_id=debrief.debrief_id,
                interviewer_name=debrief.interviewer_name,
                start_char=idx,
                end_char=idx + 7,
                quoted_text="debrief",
            )
        ],
        confidence=confidence,
        is_vague=is_vague,
        is_unsupported=False,
        extractor_version="test-v1",
    )


# ---------------------------------------------------------------------------
# Unit tests for analyze_coverage
# ---------------------------------------------------------------------------


class TestCoverageAnalyzer:
    def test_not_covered_when_no_signals(self):
        rubric = make_rubric([make_competency("Stat", "stat")])
        result = analyze_coverage([], rubric)
        assert len(result.competency_assessments) == 1
        assert result.competency_assessments[0].coverage_status == CoverageStatus.NOT_COVERED

    def test_partial_for_single_interviewer(self):
        debrief = make_debrief("Alice")
        rubric = make_rubric()
        signals = [make_signal(debrief, "stat", SignalType.POSITIVE)]
        result = analyze_coverage(signals, rubric, [debrief])
        assert result.competency_assessments[0].coverage_status == CoverageStatus.PARTIAL

    def test_strong_for_two_positive_interviewers(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert result.competency_assessments[0].coverage_status == CoverageStatus.STRONG

    def test_conflicted_for_disagreeing_interviewers(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert result.competency_assessments[0].coverage_status == CoverageStatus.CONFLICTED

    def test_coverage_gap_for_not_covered(self):
        rubric = make_rubric()
        result = analyze_coverage([], rubric)
        assert len(result.coverage_gaps) == 1
        assert result.coverage_gaps[0].coverage_status == CoverageStatus.NOT_COVERED
        assert "no interviewer assessed" in result.coverage_gaps[0].suggested_followup.lower()

    def test_coverage_gap_for_partial(self):
        debrief = make_debrief()
        rubric = make_rubric()
        result = analyze_coverage([make_signal(debrief, "stat", SignalType.POSITIVE)], rubric, [debrief])
        assert len(result.coverage_gaps) == 1
        assert result.coverage_gaps[0].coverage_status == CoverageStatus.PARTIAL

    def test_no_gap_for_strong(self):
        d1, d2 = make_debrief("A"), make_debrief("B")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert result.coverage_gaps == []

    def test_overall_coverage_pct_all_covered(self):
        d1, d2 = make_debrief("A"), make_debrief("B")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert result.overall_coverage_pct == 100.0

    def test_overall_coverage_pct_none_covered(self):
        rubric = make_rubric()
        result = analyze_coverage([], rubric)
        assert result.overall_coverage_pct == 0.0

    def test_multiple_competencies(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric(
            [
                make_competency("Stat", "stat"),
                make_competency("SQL", "sql"),
            ]
        )
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
            # sql not assessed
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert len(result.competency_assessments) == 2
        stat_ca = next(a for a in result.competency_assessments if a.competency_id == "stat")
        sql_ca = next(a for a in result.competency_assessments if a.competency_id == "sql")
        assert stat_ca.coverage_status == CoverageStatus.STRONG
        assert sql_ca.coverage_status == CoverageStatus.NOT_COVERED

    def test_vague_signals_collected(self):
        debrief = make_debrief()
        rubric = make_rubric()
        signals = [make_signal(debrief, "stat", SignalType.POSITIVE, is_vague=True)]
        result = analyze_coverage(signals, rubric, [debrief])
        ca = result.competency_assessments[0]
        assert len(ca.vague_claims) == 1

    def test_positive_and_negative_evidence_collected(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        ca = result.competency_assessments[0]
        assert len(ca.positive_evidence) >= 1
        assert len(ca.negative_evidence) >= 1

    def test_interviewers_list_populated(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
        ]
        result = analyze_coverage(signals, rubric, [d1, d2])
        assert "Alice" in result.interviewers
        assert "Bob" in result.interviewers


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


class TestCoverageEndpoint:
    @pytest.fixture
    def sample_rubric(self):
        return json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text())

    def test_returns_200_empty_signals(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric, "debriefs": []}
        resp = client.post("/analyze/coverage", json=body)
        assert resp.status_code == 200

    def test_all_not_covered_with_no_signals(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        data = client.post("/analyze/coverage", json=body).json()
        for ca in data["competency_assessments"]:
            assert ca["coverage_status"] == "not_covered"

    def test_coverage_gaps_count_matches_not_covered(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        data = client.post("/analyze/coverage", json=body).json()
        not_covered = sum(
            1 for ca in data["competency_assessments"] if ca["coverage_status"] in ("not_covered", "partial")
        )
        assert data["overall_coverage_pct"] == 0.0
        assert len(data["coverage_gaps"]) == not_covered

    def test_overall_coverage_pct_in_response(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        data = client.post("/analyze/coverage", json=body).json()
        assert "overall_coverage_pct" in data
        assert isinstance(data["overall_coverage_pct"], float)
