"""
Analysis endpoints (PROMPT 8 + PROMPT 9).

POST /analyze/coverage      — coverage map across all interviewers × competencies
POST /analyze/disagreements — detected interviewer conflicts
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.models import (
    CoverageMapResponse,
    CoverageRequest,
    DisagreementSeverity,
    DisagreementsRequest,
    DisagreementsResponse,
)
from app.services.coverage_analyzer import analyze_coverage
from app.services.disagreement_detector import detect_disagreements

router = APIRouter(prefix="/analyze", tags=["analysis"])


@router.post("/coverage", response_model=CoverageMapResponse)
async def coverage_map(request: CoverageRequest) -> CoverageMapResponse:
    """
    Build a coverage map across all interviewers for every rubric competency.

    CoverageStatus per competency:
    - **strong**      — ≥2 debriefs assessed it, at least one positive signal
    - **partial**     — only 1 debrief assessed it
    - **not_covered** — no signals for this competency
    - **conflicted**  — ≥2 debriefs assessed it with conflicting directions

    `overall_coverage_pct` = share of *required* competencies with STRONG or CONFLICTED status.
    `coverage_gaps` lists every NOT_COVERED or PARTIAL competency with a suggested follow-up.
    """
    if not request.rubric.competencies:
        raise HTTPException(
            status_code=400,
            detail="Rubric must have at least one competency.",
        )
    return analyze_coverage(request.signals, request.rubric, request.debriefs or None)


@router.post("/disagreements", response_model=DisagreementsResponse)
async def disagreements(request: DisagreementsRequest) -> DisagreementsResponse:
    """
    Detect interviewer disagreements across competencies.

    Returns `DisagreementFlag` objects sorted by severity (HIGH first).

    Detection types implemented:
    - **direction_conflict** — one interviewer positive, another negative on the same competency
    - **evidence_absent**   — confident claim (≥70%) with no verifiable evidence spans

    Each flag carries `resolution_suggestion` — a committee discussion prompt.
    """
    if not request.rubric.competencies:
        raise HTTPException(
            status_code=400,
            detail="Rubric must have at least one competency.",
        )

    flags = detect_disagreements(request.signals, request.rubric, request.debriefs or None)

    return DisagreementsResponse(
        flags=flags,
        total_flags=len(flags),
        high_severity_count=sum(1 for f in flags if f.severity == DisagreementSeverity.HIGH),
        medium_severity_count=sum(1 for f in flags if f.severity == DisagreementSeverity.MEDIUM),
    )
