"""
Extraction endpoints.

PROMPT 5: POST /extract/baseline  (deterministic, no API key)
PROMPT 6: POST /extract/llm       (LLM-powered via Claude, Pydantic-gated output)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.models import ExtractionRequest, ExtractionResponse
from app.services.baseline_extractor import extract_all_baseline
from app.services.llm_client import LLMClientBase, extract_all_llm, get_llm_client

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("/baseline", response_model=ExtractionResponse)
async def extract_baseline(request: ExtractionRequest) -> ExtractionResponse:
    """
    Run the deterministic baseline extractor on the submitted debriefs.

    No API key required. Uses keyword matching against the rubric competencies.
    Intentionally imperfect — exists to establish a lower bound for evaluation.

    Use POST /extract/llm for LLM-powered extraction.

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
async def extract_llm(
    request: ExtractionRequest,
    client: LLMClientBase = Depends(get_llm_client),
) -> ExtractionResponse:
    """
    LLM-powered extraction using Claude claude-opus-4-8.

    Requires ANTHROPIC_API_KEY in environment, or LLM_MOCK_MODE=true for testing.

    Every signal returned has been validated through Pydantic schemas. Evidence
    spans carry verbatim quoted text and exact character offsets into the source
    debrief — the EvidenceVerifier (PROMPT 7) will re-confirm these.

    Returns 503 if no API key is configured and mock mode is off.
    Returns 502 if the Anthropic API is unreachable.
    Returns 422 if Claude's output fails Pydantic schema validation (not silently accepted).
    """
    if not request.debriefs:
        raise HTTPException(status_code=400, detail="At least one debrief is required.")
    if not request.rubric.competencies:
        raise HTTPException(status_code=400, detail="Rubric must have at least one competency.")

    signals, warnings = extract_all_llm(request.debriefs, request.rubric, client)

    return ExtractionResponse(
        signals=signals,
        total_signals=len(signals),
        extractor_used=client.extractor_version,
        warnings=warnings,
    )
