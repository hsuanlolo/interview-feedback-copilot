"""
Reviewer edit/approval endpoint (PROMPT 12).

PATCH /review/{report_id} — apply reviewer notes and approval status.
GET   /review/{report_id} — retrieve a report for review.

Human review is a required step, not optional (non-negotiable design rule).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.models import ReviewUpdate, SynthesisReport
from app.services.store import store

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/{report_id}", response_model=SynthesisReport)
async def get_report(report_id: str) -> SynthesisReport:
    """
    Retrieve a previously synthesised report for human review.

    Use `PATCH /review/{report_id}` to add notes and approve.
    """
    report = store.get_report(report_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report '{report_id}' not found.",
        )
    return report


@router.patch("/{report_id}", response_model=SynthesisReport)
async def update_review(report_id: str, update: ReviewUpdate) -> SynthesisReport:
    """
    Apply reviewer edits to a synthesis report.

    Fields the reviewer can update:
    - `final_reviewer_notes` — free-text additions, corrections, context
    - `reviewer_approved`    — set True when the reviewer is satisfied
    - `reviewer_name`        — the reviewer's name for audit trail

    Setting `reviewer_approved=True` records the current timestamp as `reviewed_at`.

    The report is NOT locked after approval — reviewers can iterate. The
    `reviewer_approved` flag signals that the report is ready for the committee,
    not that it is immutable.
    """
    report = store.update_report_review(
        report_id=report_id,
        reviewer_name=update.reviewer_name,
        reviewer_approved=update.reviewer_approved,
        final_reviewer_notes=update.final_reviewer_notes,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report '{report_id}' not found.",
        )
    return report
