"""Tests for PROMPT 9: disagreement detector."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.models import (
    Competency,
    DisagreementSeverity,
    DisagreementType,
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)
from app.services.disagreement_detector import detect_disagreements
from app.services.store import store

client = TestClient(app)
SAMPLE_DIR = Path(__file__).parents[3] / "sample_data"


@pytest.fixture(autouse=True)
def reset():
    store.reset()
    yield
    store.reset()


def make_debrief(interviewer: str = "Alice") -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=f"Interview notes from {interviewer} covering multiple technical topics in detail.",
    )


def make_competency(name: str = "Statistical Reasoning", cid: str = "stat") -> Competency:
    return Competency(
        competency_id=cid,
        name=name,
        description=f"Tests {name}.",
        positive_indicators=[],
        negative_indicators=[],
    )


def make_rubric(competencies: List[Competency] | None = None) -> RoleRubric:
    return RoleRubric(
        role_title="Data Scientist",
        competencies=competencies or [make_competency()],
    )


def make_signal(
    debrief: InterviewDebrief,
    competency_id: str = "stat",
    signal_type: SignalType = SignalType.POSITIVE,
    confidence: float = 0.80,
    is_unsupported: bool = False,
) -> ExtractedSignal:
    idx = debrief.raw_text.find("Interview")
    span = EvidenceSpan.model_construct(
        span_id=str(uuid4()),
        source_debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
        start_char=idx,
        end_char=idx + 9,
        quoted_text="Interview",
    )
    return ExtractedSignal.model_construct(
        signal_id=str(uuid4()),
        debrief_id=debrief.debrief_id,
        competency_id=competency_id,
        signal_type=signal_type,
        claim="Candidate demonstrated the competency clearly.",
        evidence_spans=[span],
        confidence=confidence,
        is_vague=False,
        is_unsupported=is_unsupported,
        extractor_version="test-v1",
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestDisagreementDetector:
    def test_no_signals_returns_empty(self):
        flags = detect_disagreements([], make_rubric())
        assert flags == []

    def test_single_debrief_no_conflict(self):
        debrief = make_debrief("Alice")
        rubric = make_rubric()
        flags = detect_disagreements([make_signal(debrief, "stat", SignalType.POSITIVE)], rubric)
        direction_flags = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert direction_flags == []

    def test_direction_conflict_detected(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        # 1 net-positive voter vs 1 net-negative voter → ratio=0.50 ≥ 0.35 → fires
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert len(direction) == 1
        assert direction[0].severity == DisagreementSeverity.HIGH
        assert direction[0].competency_id == "stat"

    def test_direction_conflict_names_both_interviewers(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        flag = flags[0]
        assert "Alice" in flag.interviewer_names
        assert "Bob" in flag.interviewer_names

    def test_same_direction_no_conflict(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [make_signal(d1, "stat", SignalType.POSITIVE), make_signal(d2, "stat", SignalType.POSITIVE)]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert direction == []

    def test_evidence_absent_flagged_for_unsupported_high_confidence(self):
        debrief = make_debrief("Alice")
        rubric = make_rubric()
        signal = make_signal(debrief, "stat", SignalType.POSITIVE, confidence=0.90, is_unsupported=True)
        flags = detect_disagreements([signal], rubric, [debrief])
        absent = [f for f in flags if f.disagreement_type == DisagreementType.EVIDENCE_ABSENT]
        assert len(absent) == 1
        assert absent[0].severity == DisagreementSeverity.HIGH

    def test_evidence_absent_not_flagged_for_low_confidence(self):
        debrief = make_debrief("Alice")
        rubric = make_rubric()
        signal = make_signal(debrief, "stat", SignalType.POSITIVE, confidence=0.40, is_unsupported=True)
        flags = detect_disagreements([signal], rubric, [debrief])
        absent = [f for f in flags if f.disagreement_type == DisagreementType.EVIDENCE_ABSENT]
        assert absent == []

    def test_flags_sorted_high_first(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric([make_competency("Stat", "stat"), make_competency("SQL", "sql")])
        # 1 net-positive voter vs 1 net-negative voter per competency → both HIGH
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
            make_signal(d1, "sql", SignalType.POSITIVE),
            make_signal(d2, "sql", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        assert len(flags) >= 2
        severities = [f.severity for f in flags]
        high_positions = [i for i, s in enumerate(severities) if s == DisagreementSeverity.HIGH]
        low_positions = [i for i, s in enumerate(severities) if s == DisagreementSeverity.LOW]
        if high_positions and low_positions:
            assert max(high_positions) < min(low_positions)

    def test_resolution_suggestion_nonempty(self):
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        assert len(flags) >= 1
        for flag in flags:
            assert flag.resolution_suggestion != ""

    def test_single_minority_voter_not_flagged(self):
        """1 dissenting voter out of 4 clear voters = 25% minority, below the 35% threshold."""
        d1, d2, d3, d4 = (
            make_debrief("Alice"), make_debrief("Bob"),
            make_debrief("Carol"), make_debrief("Dave"),
        )
        rubric = make_rubric()
        # 3 net-positive voters vs 1 net-negative voter → ratio=0.25 < 0.35 → no conflict
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
            make_signal(d3, "stat", SignalType.POSITIVE),
            make_signal(d4, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2, d3, d4])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert direction == []

    def test_mixed_interviewer_excluded_from_conflict(self):
        """A tied interviewer is excluded; remaining 3-vs-1 split (25%) is below the 30% threshold."""
        d1, d2, d3, d4, d5 = (
            make_debrief("Alice"), make_debrief("Bob"),
            make_debrief("Carol"), make_debrief("Dave"), make_debrief("Eve"),
        )
        rubric = make_rubric()
        # Alice: 1 pos + 1 neg → net=tied → excluded
        # Bob, Carol, Eve: net positive (3 pos voters)
        # Dave: net negative (1 neg voter)
        # After exclusion: 3 pos + 1 neg → ratio=0.25 < 0.30 → no conflict
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d1, "stat", SignalType.NEGATIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
            make_signal(d3, "stat", SignalType.POSITIVE),
            make_signal(d4, "stat", SignalType.NEGATIVE),
            make_signal(d5, "stat", SignalType.POSITIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2, d3, d4, d5])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert direction == []

    def test_low_ratio_not_flagged(self):
        """5 positive voters vs 1 negative voter = ratio 17%, clearly below the 30% threshold."""
        d1, d2, d3, d4, d5, d6 = (
            make_debrief("Alice"), make_debrief("Bob"), make_debrief("Carol"),
            make_debrief("Dave"), make_debrief("Eve"), make_debrief("Frank"),
        )
        rubric = make_rubric()
        # 5 net-positive voters vs 1 net-negative voter → ratio=0.17 < 0.30 → no conflict
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
            make_signal(d3, "stat", SignalType.POSITIVE),
            make_signal(d4, "stat", SignalType.POSITIVE),
            make_signal(d5, "stat", SignalType.POSITIVE),
            make_signal(d6, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2, d3, d4, d5, d6])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert direction == []

    def test_medium_severity_for_skewed_split(self):
        """3 positive voters vs 2 negative voters = ratio 40%, between 35% and 45% → MEDIUM."""
        d1, d2, d3, d4, d5 = (
            make_debrief("Alice"), make_debrief("Bob"), make_debrief("Carol"),
            make_debrief("Dave"), make_debrief("Eve"),
        )
        rubric = make_rubric()
        # 3 net-positive vs 2 net-negative → ratio=0.40, fires (≥0.35) but not HIGH (<0.45)
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.POSITIVE),
            make_signal(d3, "stat", SignalType.POSITIVE),
            make_signal(d4, "stat", SignalType.NEGATIVE),
            make_signal(d5, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2, d3, d4, d5])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert len(direction) == 1
        assert direction[0].severity == DisagreementSeverity.MEDIUM

    def test_high_severity_for_even_split(self):
        """1 vs 1 voters → ratio=0.50 ≥ 0.45 → HIGH severity."""
        d1, d2 = make_debrief("Alice"), make_debrief("Bob")
        rubric = make_rubric()
        signals = [
            make_signal(d1, "stat", SignalType.POSITIVE),
            make_signal(d2, "stat", SignalType.NEGATIVE),
        ]
        flags = detect_disagreements(signals, rubric, [d1, d2])
        direction = [f for f in flags if f.disagreement_type == DisagreementType.DIRECTION_CONFLICT]
        assert len(direction) == 1
        assert direction[0].severity == DisagreementSeverity.HIGH

    def test_unknown_competency_id_skipped(self):
        debrief = make_debrief("Alice")
        rubric = make_rubric()
        signal = make_signal(debrief, "unknown_cid", SignalType.POSITIVE)
        flags = detect_disagreements([signal], rubric)
        assert flags == []


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

class TestDisagreementsEndpoint:
    @pytest.fixture
    def sample_rubric(self):
        return json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text())

    def test_returns_200(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        resp = client.post("/analyze/disagreements", json=body)
        assert resp.status_code == 200

    def test_empty_signals_no_flags(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        data = client.post("/analyze/disagreements", json=body).json()
        assert data["flags"] == []
        assert data["total_flags"] == 0
        assert data["high_severity_count"] == 0

    def test_response_has_severity_counts(self, sample_rubric):
        body = {"signals": [], "rubric": sample_rubric}
        data = client.post("/analyze/disagreements", json=body).json()
        assert "total_flags" in data
        assert "high_severity_count" in data
        assert "medium_severity_count" in data
