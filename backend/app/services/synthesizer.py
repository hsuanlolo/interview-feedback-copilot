"""
Synthesis report generator (PROMPT 10).

Orchestrates the full pipeline:
  1. Verify citations (hard gate — blocks if any span is invalid)
  2. Build coverage map
  3. Detect disagreements
  4. Generate executive summary (template-based; LLM version in a future prompt)
  5. Assemble and return SynthesisReport

Non-negotiable rules enforced here:
  - No hire/no-hire recommendation produced or stored.
  - Synthesis blocked if citation_validity_rate < 1.0.
  - Every CompetencyAssessment traces back to ExtractedSignal evidence spans.
"""

from __future__ import annotations

from typing import List

from fastapi import HTTPException

from app.schemas.models import (
    CompetencyAssessment,
    CoverageGap,
    CoverageStatus,
    DisagreementFlag,
    DisagreementSeverity,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SynthesisReport,
    SynthesisRequest,
)
from app.services.coverage_analyzer import analyze_coverage
from app.services.disagreement_detector import detect_disagreements
from app.services.evidence_verifier import verifier


def _generate_executive_summary(
    assessments: List[CompetencyAssessment],
    flags: List[DisagreementFlag],
    gaps: List[CoverageGap],
    n_debriefs: int,
    n_signals: int,
) -> str:
    """
    Template-based executive summary.

    Intentionally factual and neutral: no qualitative language about the candidate.
    It describes what evidence was found, not what it means — that is the human's job.
    """
    strong = [a for a in assessments if a.coverage_status == CoverageStatus.STRONG]
    conflicted = [a for a in assessments if a.coverage_status == CoverageStatus.CONFLICTED]
    not_covered = [g for g in gaps if g.coverage_status == CoverageStatus.NOT_COVERED]
    high_flags = [f for f in flags if f.severity == DisagreementSeverity.HIGH]

    parts: List[str] = [
        f"This synthesis covers {n_debriefs} interview debrief(s) yielding "
        f"{n_signals} extracted signal(s) across {len(assessments)} competency(ies)."
    ]

    if strong:
        names = ", ".join(a.competency_name for a in strong[:3])
        more = f" (and {len(strong) - 3} more)" if len(strong) > 3 else ""
        parts.append(
            f"{len(strong)} competency(ies) have corroborating positive evidence "
            f"from multiple interviewers: {names}{more}."
        )

    if conflicted:
        names = ", ".join(a.competency_name for a in conflicted[:2])
        parts.append(
            f"{len(conflicted)} competency(ies) show interviewer disagreement: {names}."
        )

    if not_covered:
        names = ", ".join(g.competency_name for g in not_covered[:3])
        more = f" (and {len(not_covered) - 3} more)" if len(not_covered) > 3 else ""
        parts.append(
            f"{len(not_covered)} required competency(ies) were not assessed: {names}{more}."
        )

    if high_flags:
        parts.append(
            f"{len(high_flags)} high-severity disagreement(s) require committee discussion "
            "before a decision is made."
        )

    parts.append(
        "This report organises evidence for human review. "
        "No hire/no-hire recommendation is produced."
    )

    return " ".join(parts)


def synthesize(request: SynthesisRequest) -> SynthesisReport:
    """
    Generate a SynthesisReport for one candidate.

    Raises HTTPException(422) if citation verification fails.
    Raises HTTPException(400) if no signals provided.
    """
    if not request.debriefs:
        raise HTTPException(
            status_code=400,
            detail="At least one debrief is required to synthesise a report.",
        )

    # ── 1. Verify citations (hard gate) ──────────────────────────────────────
    verification = verifier.verify(request.signals, request.debriefs)
    if not verification.is_valid:
        n_err = len(verification.errors)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Citation verification failed: {n_err} invalid evidence span(s). "
                "Resolve all citation errors before generating a synthesis report. "
                f"citation_validity_rate={verification.citation_validity_rate:.1%}"
            ),
        )

    # ── 2. Coverage map ───────────────────────────────────────────────────────
    coverage = analyze_coverage(request.signals, request.rubric, request.debriefs)

    # ── 3. Disagreement detection ─────────────────────────────────────────────
    flags = detect_disagreements(request.signals, request.rubric, request.debriefs)

    # ── 4. Executive summary ──────────────────────────────────────────────────
    executive_summary = _generate_executive_summary(
        assessments=coverage.competency_assessments,
        flags=flags,
        gaps=coverage.coverage_gaps,
        n_debriefs=len(request.debriefs),
        n_signals=len(request.signals),
    )

    # ── 5. Quality metrics ────────────────────────────────────────────────────
    unsupported_count = sum(1 for s in request.signals if s.is_unsupported)
    vague_count = sum(1 for s in request.signals if s.is_vague)
    extractor_ver = request.signals[0].extractor_version if request.signals else "none"

    questions = [
        f.resolution_suggestion
        for f in flags
        if f.severity == DisagreementSeverity.HIGH and f.resolution_suggestion
    ]

    return SynthesisReport(
        candidate_id=request.candidate_id,
        candidate_name=request.candidate_name,
        role_id=request.role_id,
        role_title=request.role_title,
        executive_summary=executive_summary,
        competency_assessments=coverage.competency_assessments,
        disagreement_flags=flags,
        coverage_gaps=coverage.coverage_gaps,
        questions_for_committee=questions,
        total_debriefs=len(request.debriefs),
        total_signals_extracted=len(request.signals),
        unsupported_claim_count=unsupported_count,
        vague_claim_count=vague_count,
        citation_validity_rate=verification.citation_validity_rate,
        extractor_version=extractor_ver,
    )
