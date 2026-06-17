"""
Extraction endpoints.

PROMPT 5: POST /extract/baseline  (deterministic, no API key)
PROMPT 6: POST /extract/llm       (LLM-powered, requires API key) — stub only here
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.models import ExtractionRequest, ExtractionResponse
from app.services.baseline_extractor import extract_all_baseline

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("/baseline", response_model=ExtractionResponse)
async def extract_baseline(request: ExtractionRequest) -> ExtractionResponse:
    """
    Run the deterministic baseline extractor on the submitted debriefs.

    No API key required. Uses keyword matching against the rubric competencies.
    Intentionally imperfect — exists to establish a lower bound for evaluation.

    Use POST /extract/llm (PROMPT 6) for LLM-powered extraction.

    Input:
      - rubric: the role's RoleRubric (load from GET /rubrics/sample or upload your own)
      - debriefs: list of InterviewDebrief objects (load from GET /debriefs/sample or upload)

    Output:
      - signals: list of ExtractedSignal, one per (debrief × competency) pair matched
      - warnings: quality warnings (short debriefs, zero matches, etc.)
    """
    if not request.debriefs:
        raise HTTPException(status_code=400, detail="At least one debrief is required.")
    if not request.rubric.competencies:
        raise HTTPException(status_code=400, detail="Rubric must have at least one competency.")

    signals, warnings = extract_all_baseline(request.debriefs, request.rubric)

    return ExtractionResponse(
        signals=signals,
        total_signals=len(signals),
        extractor_used="baseline-v1",
        warnings=warnings,
    )


@router.post("/llm", response_model=ExtractionResponse)
async def extract_llm(request: ExtractionRequest) -> ExtractionResponse:
    """
    LLM-powered extraction endpoint — stub for PROMPT 6.

    Will use Claude structured-JSON extraction with Pydantic validation gating.
    Returns 501 until PROMPT 6 is implemented.
    """
    raise HTTPException(
        status_code=501,
        detail="LLM extraction not yet implemented. Use POST /extract/baseline for now.",
    )
