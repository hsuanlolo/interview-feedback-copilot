"""
Core Pydantic data models for the Interview Feedback Copilot.

These schemas are the source of truth for data shape throughout the system.
All API endpoints, LLM prompts, and database models derive from these definitions.

Design rules:
- Every model-generated claim must carry at least one EvidenceSpan.
- EvidenceSpans must quote verbatim text from the source debrief.
- No hire/no-hire recommendation fields exist anywhere in this file (deliberate).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SignalType(str, Enum):
    """Direction of an extracted competency signal."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class DisagreementSeverity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DisagreementType(str, Enum):
    DIRECTION_CONFLICT = "direction_conflict"  # one positive, one negative
    SCORE_GAP = "score_gap"  # numeric scores differ significantly
    EVIDENCE_ABSENT = "evidence_absent"  # strong claim with no supporting evidence
    SCALE_MISMATCH = "score_text_mismatch"  # high score paired with negative narrative


class CoverageStatus(str, Enum):
    STRONG = "strong"  # assessed by ≥2 interviewers, at least one positive
    PARTIAL = "partial"  # assessed by 1 interviewer
    NOT_COVERED = "not_covered"  # no interviewer assessed this competency
    CONFLICTED = "conflicted"  # assessed, but signals conflict


# ---------------------------------------------------------------------------
# Rubric models
# ---------------------------------------------------------------------------


class Competency(BaseModel):
    """A single evaluatable competency within a role rubric."""

    competency_id: str = Field(..., description="Unique identifier, e.g. 'stat_reasoning'")
    name: str = Field(..., description="Human-readable name, e.g. 'Statistical Reasoning'")
    description: str = Field(..., description="What strong performance looks like")
    required: bool = Field(True, description="Whether this is a required competency for the role")
    weight: float = Field(1.0, ge=0.0, le=5.0, description="Relative importance (1.0 = baseline)")
    positive_indicators: list[str] = Field(
        default_factory=list,
        description="Phrases or behaviors that signal strength in this competency",
    )
    negative_indicators: list[str] = Field(
        default_factory=list,
        description="Phrases or behaviors that signal weakness in this competency",
    )


class RoleRubric(BaseModel):
    """A complete competency rubric for a specific role."""

    rubric_id: str = Field(default_factory=lambda: str(uuid4()))
    role_title: str
    role_level: str = Field("", description="e.g. 'Senior', 'Lead', 'IC3'")
    department: str = ""
    competencies: list[Competency]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("competencies")
    @classmethod
    def at_least_one_competency(cls, v: list[Competency]) -> list[Competency]:
        if not v:
            raise ValueError("A rubric must define at least one competency")
        return v


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    role_applied: str
    interview_loop_stage: str = Field("", description="e.g. 'Technical Interview Round 2'")


# ---------------------------------------------------------------------------
# Interview Debrief (raw input)
# ---------------------------------------------------------------------------


class InterviewDebrief(BaseModel):
    """Raw interviewer debrief as uploaded by the recruiter."""

    debrief_id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_id: str
    interviewer_name: str
    interviewer_id: str = ""
    round_name: str = Field("", description="e.g. 'Technical Interview 1'")
    interview_date: str = Field("", description="ISO date string or freeform")
    raw_text: str = Field(..., min_length=10, description="Full debrief text as submitted")
    score_raw: str = Field("", description="Raw score as the interviewer stated it, e.g. '4/5' or 'Strong'")
    scale_description: str = Field("", description="e.g. '1 (Weak) – 5 (Exceptional)'")
    word_count: int = Field(0, description="Computed on ingest")

    @model_validator(mode="after")
    def compute_word_count(self) -> "InterviewDebrief":
        self.word_count = len(self.raw_text.split())
        return self


# ---------------------------------------------------------------------------
# Evidence Span (the traceability unit)
# ---------------------------------------------------------------------------


class EvidenceSpan(BaseModel):
    """
    A verbatim excerpt from a debrief that supports a claim.

    The quoted_text MUST appear verbatim in the source debrief.
    The EvidenceVerifier confirms this before synthesis is generated.
    """

    span_id: str = Field(default_factory=lambda: str(uuid4()))
    source_debrief_id: str
    interviewer_name: str
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., ge=0)
    quoted_text: str = Field(..., min_length=5, description="Verbatim text from the debrief")

    @model_validator(mode="after")
    def end_after_start(self) -> "EvidenceSpan":
        if self.end_char <= self.start_char:
            raise ValueError(f"end_char ({self.end_char}) must be > start_char ({self.start_char})")
        return self

    @model_validator(mode="after")
    def span_matches_quoted_text(self) -> "EvidenceSpan":
        expected_len = self.end_char - self.start_char
        if abs(expected_len - len(self.quoted_text)) > 5:
            # Allow small tolerance for whitespace normalization
            raise ValueError(
                f"quoted_text length ({len(self.quoted_text)}) does not match "
                f"span length ({expected_len})"
            )
        return self


# ---------------------------------------------------------------------------
# Extracted Signal (output of the extraction layer)
# ---------------------------------------------------------------------------


class ExtractedSignal(BaseModel):
    """
    A single competency assessment extracted from a debrief.

    One debrief can produce multiple ExtractedSignals (one per competency mentioned).
    Every claim must have at least one evidence span.
    """

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    debrief_id: str
    competency_id: str
    signal_type: SignalType
    claim: str = Field(..., min_length=5, description="The substantive takeaway in one sentence")
    evidence_spans: list[EvidenceSpan] = Field(
        ..., min_length=1, description="Must have at least one supporting span"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extractor confidence in this signal")
    is_vague: bool = Field(False, description="True if the claim lacks specificity")
    is_unsupported: bool = Field(False, description="True if claim could not be grounded in span")
    extractor_version: str = Field("baseline", description="Which extractor produced this signal")

    @field_validator("evidence_spans")
    @classmethod
    def must_have_evidence(cls, v: list[EvidenceSpan]) -> list[EvidenceSpan]:
        if not v:
            raise ValueError("ExtractedSignal must have at least one EvidenceSpan")
        return v


# ---------------------------------------------------------------------------
# Competency Assessment (rolled up per competency across all interviewers)
# ---------------------------------------------------------------------------


class InterviewerAssessment(BaseModel):
    """One interviewer's assessment of one competency."""

    interviewer_name: str
    signal_type: SignalType
    signals: list[ExtractedSignal]
    summary: str = Field("", description="One-sentence summary of this interviewer's view")


class CompetencyAssessment(BaseModel):
    """Rolled-up assessment of one competency across all interviewers."""

    competency_id: str
    competency_name: str
    coverage_status: CoverageStatus
    assessments_by_interviewer: list[InterviewerAssessment]
    positive_evidence: list[ExtractedSignal] = Field(default_factory=list)
    negative_evidence: list[ExtractedSignal] = Field(default_factory=list)
    vague_claims: list[ExtractedSignal] = Field(default_factory=list)
    synthesis_summary: str = Field("", description="Human-reviewable summary — editable by reviewer")


# ---------------------------------------------------------------------------
# Disagreement Flag
# ---------------------------------------------------------------------------


class DisagreementFlag(BaseModel):
    """A detected conflict between interviewers on a competency."""

    flag_id: str = Field(default_factory=lambda: str(uuid4()))
    competency_id: str
    competency_name: str
    disagreement_type: DisagreementType
    severity: DisagreementSeverity
    description: str = Field(..., description="Plain-English description of the conflict")
    interviewer_names: list[str]
    supporting_evidence_spans: list[EvidenceSpan]
    resolution_suggestion: str = Field(
        "", description="Suggested follow-up question or area to probe"
    )


# ---------------------------------------------------------------------------
# Coverage Gap
# ---------------------------------------------------------------------------


class CoverageGap(BaseModel):
    """A required competency that was not assessed, or assessed by only one interviewer."""

    competency_id: str
    competency_name: str
    coverage_status: CoverageStatus
    interviewers_who_assessed: list[str] = Field(default_factory=list)
    suggested_followup: str = Field("", description="Suggested question or probe for a follow-up interview")


# ---------------------------------------------------------------------------
# Synthesis Report (the final output — human-reviewable, no hire/no-hire)
# ---------------------------------------------------------------------------


class SynthesisReport(BaseModel):
    """
    The human-reviewable synthesis of all debrief evidence.

    Deliberately omits:
    - Hire/no-hire recommendation
    - Aggregate candidate score
    - Cross-candidate ranking

    Every substantive claim must cite evidence spans.
    """

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    candidate_id: str
    candidate_name: str
    role_id: str
    role_title: str

    # Content
    executive_summary: str = Field(
        ..., description="3–5 sentence overview of evidence quality and key themes"
    )
    competency_assessments: list[CompetencyAssessment]
    disagreement_flags: list[DisagreementFlag]
    coverage_gaps: list[CoverageGap]
    questions_for_committee: list[str] = Field(
        default_factory=list,
        description="Unresolved questions the hiring committee should discuss",
    )

    # Quality metadata
    total_debriefs: int
    total_signals_extracted: int
    unsupported_claim_count: int = 0
    vague_claim_count: int = 0
    citation_validity_rate: float = Field(
        1.0, ge=0.0, le=1.0, description="Share of evidence spans verified as valid"
    )

    # Human review fields
    final_reviewer_notes: str = Field(
        "", description="Reviewer's additions, corrections, and conclusions"
    )
    reviewer_approved: bool = False
    reviewer_name: str = ""
    reviewed_at: Optional[datetime] = None

    # Provenance
    created_at: datetime = Field(default_factory=datetime.utcnow)
    extractor_version: str = "baseline"

    # No hire/no-hire recommendation field exists. This is deliberate.
    # If a field named recommendation, score, or hire_decision appears here,
    # that is a bug and should be removed.


# ---------------------------------------------------------------------------
# Evidence Verification Result
# ---------------------------------------------------------------------------


class VerificationError(BaseModel):
    span_id: str
    error_type: str  # "text_not_found", "offset_mismatch", "claim_not_supported"
    description: str


class VerificationResult(BaseModel):
    """Output of the EvidenceVerifier service."""

    is_valid: bool
    errors: list[VerificationError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    vague_claims: list[str] = Field(default_factory=list)
    citation_validity_rate: float = Field(1.0, ge=0.0, le=1.0)
    total_spans_checked: int = 0
    valid_spans: int = 0


# ---------------------------------------------------------------------------
# API Request / Response wrappers
# ---------------------------------------------------------------------------


class ExtractionRequest(BaseModel):
    debriefs: list[InterviewDebrief]
    rubric: RoleRubric


class ExtractionResponse(BaseModel):
    signals: list[ExtractedSignal]
    total_signals: int
    extractor_used: str
    warnings: list[str] = Field(default_factory=list)


class CoverageMapResponse(BaseModel):
    competency_assessments: list[CompetencyAssessment]
    coverage_gaps: list[CoverageGap]
    overall_coverage_pct: float = Field(..., ge=0.0, le=100.0)
    interviewers: list[str]


class ProjectCreate(BaseModel):
    candidate_name: str
    role_title: str
    rubric_id: str = ""


class ProjectSummary(BaseModel):
    project_id: str
    candidate_name: str
    role_title: str
    debrief_count: int
    has_synthesis: bool
    created_at: datetime
