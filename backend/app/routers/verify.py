"""
Evidence verification endpoint.

PROMPT 7: POST /verify/evidence
  Accepts extracted signals + source debriefs.
  Returns a VerificationResult with citation_validity_rate and a full error list.
  is_valid=False means synthesis must not proceed.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.models import VerificationRequest, VerificationResult
from app.services.evidence_verifier import verifier

router = APIRouter(prefix="/verify", tags=["verification"])


@router.post("/evidence", response_model=VerificationResult)
async def verify_evidence(request: VerificationRequest) -> VerificationResult:
    """
    Validate that every EvidenceSpan in the submitted signals is grounded in
    verbatim text from the source debrief at the stated character offsets.

    **Non-negotiable rule**: `is_valid=False` means the system must not
    generate a synthesis report until the errors are resolved.

    Error types returned per span:
    - `text_not_found`    — quoted_text does not appear anywhere in the debrief (hallucination)
    - `offset_mismatch`   — text exists, but not at [start_char:end_char] (extractor bug)
    - `source_missing`    — span references a debrief_id not in the provided debriefs list

    Signal-level outcomes:
    - `unsupported_claims` — signal IDs where ALL spans failed (no grounded evidence)
    - `vague_claims`       — signal IDs where `is_vague=True`

    Returns `citation_validity_rate = valid_spans / total_spans_checked`.
    100% is required before synthesis (eval plan hard gate).
    """
    if not request.debriefs:
        raise HTTPException(
            status_code=400,
            detail="At least one debrief is required for verification.",
        )

    return verifier.verify(request.signals, request.debriefs)
