"""
Synthesis endpoint (PROMPT 10).

POST /synthesize — generate a SynthesisReport from verified signals.

The report is saved to the in-memory store and can be retrieved later
for reviewer edits (PROMPT 12).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.models import SynthesisReport, SynthesisRequest
from app.services.store import store
from app.services.synthesizer import synthesize

router = APIRouter(prefix="/synthesize", tags=["synthesis"])


@router.post("", response_model=SynthesisReport, status_code=201)
async def create_synthesis(request: SynthesisRequest) -> SynthesisReport:
    """
    Generate a human-reviewable SynthesisReport.

    Pipeline:
    1. Verify all evidence spans (blocks with 422 if any span is invalid)
    2. Build the coverage map
    3. Detect interviewer disagreements
    4. Generate a template executive summary
    5. Save the report to the store and return it

    **No hire/no-hire recommendation is produced** — this is a non-negotiable
    design constraint. The report surfaces evidence; the human committee decides.

    Returns 422 if citation_validity_rate < 100% (hard gate from the eval plan).
    Returns 400 if no debriefs are provided.

    The returned `report_id` can be used with `PATCH /review/{report_id}` to
    add reviewer notes and approve the report.
    """
    report = synthesize(request)

    # Save so reviewer can retrieve and edit it
    store.save_report(project_id="", report=report)

    return report
