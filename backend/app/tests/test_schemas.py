"""Tests for core Pydantic schemas.

Run with: pytest app/tests/test_schemas.py -v
"""

import pytest
from pydantic import ValidationError

from app.schemas.models import (
    Candidate,
    CompetencyAssessment,
    CoverageStatus,
    DisagreementFlag,
    DisagreementSeverity,
    DisagreementType,
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    ProjectCreate,
    RoleRubric,
    SignalType,
    SynthesisReport,
    VerificationResult,
    Competency,
)


# ---------------------------------------------------------------------------
# EvidenceSpan
# ---------------------------------------------------------------------------


class TestEvidenceSpan:
    def test_valid_span(self):
        span = EvidenceSpan(
            source_debrief_id="d1",
            interviewer_name="Alice",
            start_char=0,
            end_char=45,
            quoted_text="Candidate solved the A/B testing question well.",
        )
        assert span.span_id  # auto-generated
        assert span.quoted_text == "Candidate solved the A/B testing question well."

    def test_end_must_be_after_start(self):
        with pytest.raises(ValidationError, match="end_char"):
            EvidenceSpan(
                source_debrief_id="d1",
                interviewer_name="Alice",
                start_char=100,
                end_char=50,  # invalid: before start
                quoted_text="Some text here.",
            )

    def test_span_length_roughly_matches_quoted_text(self):
        with pytest.raises(ValidationError):
            EvidenceSpan(
                source_debrief_id="d1",
                interviewer_name="Alice",
                start_char=0,
                end_char=500,  # way too long for a 5-char string
                quoted_text="Hello",
            )

    def test_quoted_text_min_length(self):
        with pytest.raises(ValidationError, match="min_length"):
            EvidenceSpan(
                source_debrief_id="d1",
                interviewer_name="Alice",
                start_char=0,
                end_char=4,
                quoted_text="Hi",  # too short
            )


# ---------------------------------------------------------------------------
# ExtractedSignal
# ---------------------------------------------------------------------------


def make_span(debrief_id: str = "d1") -> EvidenceSpan:
    return EvidenceSpan(
        source_debrief_id=debrief_id,
        interviewer_name="Alice",
        start_char=0,
        end_char=47,
        quoted_text="Candidate solved the A/B testing question well..",
    )


class TestExtractedSignal:
    def test_valid_signal(self):
        sig = ExtractedSignal(
            debrief_id="d1",
            competency_id="stat_reasoning",
            signal_type=SignalType.POSITIVE,
            claim="Candidate demonstrated strong statistical reasoning.",
            evidence_spans=[make_span()],
            confidence=0.9,
        )
        assert sig.signal_id
        assert sig.signal_type == SignalType.POSITIVE

    def test_requires_at_least_one_evidence_span(self):
        with pytest.raises(ValidationError, match="at least one"):
            ExtractedSignal(
                debrief_id="d1",
                competency_id="stat_reasoning",
                signal_type=SignalType.POSITIVE,
                claim="Candidate did well.",
                evidence_spans=[],  # empty — should fail
                confidence=0.8,
            )

    def test_invalid_signal_type(self):
        with pytest.raises(ValidationError):
            ExtractedSignal(
                debrief_id="d1",
                competency_id="stat_reasoning",
                signal_type="very_positive",  # not a valid enum value
                claim="Candidate did well.",
                evidence_spans=[make_span()],
                confidence=0.8,
            )

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            ExtractedSignal(
                debrief_id="d1",
                competency_id="stat_reasoning",
                signal_type=SignalType.POSITIVE,
                claim="Candidate did well.",
                evidence_spans=[make_span()],
                confidence=1.5,  # > 1.0 — invalid
            )

    def test_claim_min_length(self):
        with pytest.raises(ValidationError, match="min_length"):
            ExtractedSignal(
                debrief_id="d1",
                competency_id="stat_reasoning",
                signal_type=SignalType.POSITIVE,
                claim="ok",  # too short
                evidence_spans=[make_span()],
                confidence=0.8,
            )


# ---------------------------------------------------------------------------
# InterviewDebrief
# ---------------------------------------------------------------------------


class TestInterviewDebrief:
    def test_valid_debrief(self):
        debrief = InterviewDebrief(
            candidate_id="c1",
            interviewer_name="Bob Smith",
            round_name="Technical Interview 1",
            raw_text="The candidate showed strong analytical ability. They correctly identified "
            "the selection bias in the observational study design without prompting.",
        )
        assert debrief.word_count > 0  # auto-computed

    def test_word_count_computed(self):
        debrief = InterviewDebrief(
            candidate_id="c1",
            interviewer_name="Alice",
            raw_text="one two three four five",
        )
        assert debrief.word_count == 5

    def test_raw_text_too_short(self):
        with pytest.raises(ValidationError, match="min_length"):
            InterviewDebrief(
                candidate_id="c1",
                interviewer_name="Alice",
                raw_text="Hi",
            )


# ---------------------------------------------------------------------------
# RoleRubric
# ---------------------------------------------------------------------------


class TestRoleRubric:
    def test_valid_rubric(self):
        rubric = RoleRubric(
            role_title="Data Scientist",
            competencies=[
                Competency(
                    competency_id="stat_reasoning",
                    name="Statistical Reasoning",
                    description="Applies statistical concepts correctly.",
                )
            ],
        )
        assert rubric.rubric_id
        assert len(rubric.competencies) == 1

    def test_empty_competencies_rejected(self):
        with pytest.raises(ValidationError, match="at least one competency"):
            RoleRubric(role_title="Data Scientist", competencies=[])


# ---------------------------------------------------------------------------
# SynthesisReport — confirm no hire/no-hire field
# ---------------------------------------------------------------------------


class TestSynthesisReport:
    def test_no_hire_recommendation_field(self):
        """The SynthesisReport must not have a hire/no-hire recommendation field."""
        field_names = set(SynthesisReport.model_fields.keys())
        forbidden = {"recommendation", "hire_decision", "should_hire", "hire", "no_hire", "score"}
        overlap = field_names & forbidden
        assert not overlap, f"SynthesisReport must not contain these fields: {overlap}"

    def test_valid_report(self):
        report = SynthesisReport(
            candidate_id="c1",
            candidate_name="Jordan Lee",
            role_id="r1",
            role_title="Data Scientist",
            executive_summary="Jordan demonstrated strong statistical reasoning across three interviews. "
            "Communication skills were assessed by one interviewer only (thin coverage). "
            "One disagreement flagged on product judgment — requires discussion.",
            competency_assessments=[],
            disagreement_flags=[],
            coverage_gaps=[],
            total_debriefs=3,
            total_signals_extracted=12,
        )
        assert report.report_id
        assert not report.reviewer_approved


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_valid_result(self):
        result = VerificationResult(
            is_valid=True,
            citation_validity_rate=1.0,
            total_spans_checked=5,
            valid_spans=5,
        )
        assert result.is_valid

    def test_citation_rate_out_of_range(self):
        with pytest.raises(ValidationError):
            VerificationResult(is_valid=False, citation_validity_rate=1.5)
