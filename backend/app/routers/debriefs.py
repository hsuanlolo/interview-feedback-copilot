"""
Debrief endpoints.

Endpoints:
  GET  /debriefs/sample               Return the 5 bundled fictional debriefs
  POST /debriefs/upload/{project_id}  (stub — implemented in PROMPT 5)
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.schemas.models import InterviewDebrief

router = APIRouter(prefix="/debriefs", tags=["debriefs"])

_DEBRIEF_DIR = Path(__file__).parents[2] / "sample_data" / "debriefs"


def _parse_debrief_file(text: str, filename: str) -> InterviewDebrief:
    """Extract header fields from a structured debrief text file.

    Expected format (first N lines):
        Candidate: Jordan Lee
        Candidate ID: C-001
        Interviewer: Priya Sharma
        Interviewer ID: I-01
        Round: Technical Screen (45 min)
        Date: 2024-05-08
        Score: 4/5
        Score Scale: 1 (Does Not Meet Bar) – 5 (Exceptional)
        ---
        [body text]
    """
    fields: dict = {}
    body_lines: list[str] = []
    in_body = False

    for line in text.splitlines():
        stripped = line.strip()

        # The separator line (---) marks the start of the body
        if stripped == "---":
            in_body = True
            continue

        if in_body:
            body_lines.append(line)
            continue

        # Parse header key: value pairs
        if ":" in stripped and not in_body:
            key, _, val = stripped.partition(":")
            fields[key.strip().lower()] = val.strip()

    body = "\n".join(body_lines).strip()
    # If no separator found, treat the whole text as body
    if not body:
        body = text

    return InterviewDebrief(
        debrief_id=str(uuid4()),
        candidate_id=fields.get("candidate id", "C-001"),
        interviewer_name=fields.get("interviewer", filename),
        interviewer_id=fields.get("interviewer id", ""),
        round_name=fields.get("round", ""),
        interview_date=fields.get("date", ""),
        raw_text=text,
        score_raw=fields.get("score", ""),
        scale_description=fields.get("score scale", ""),
    )


@router.get("/sample", response_model=list[InterviewDebrief])
async def get_sample_debriefs() -> list[InterviewDebrief]:
    """Return the 5 bundled fictional debriefs for candidate Jordan Lee.

    These are used to demonstrate the full pipeline without any file upload.
    """
    if not _DEBRIEF_DIR.exists():
        raise HTTPException(
            status_code=404,
            detail="Sample debrief directory not found. Check that sample_data/ exists.",
        )

    paths = sorted(_DEBRIEF_DIR.glob("candidate_001_interviewer_*.txt"))
    if not paths:
        raise HTTPException(status_code=404, detail="No sample debrief files found.")

    result: list[InterviewDebrief] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            debrief = _parse_debrief_file(text, path.stem)
            result.append(debrief)
        except Exception as exc:
            # Log and skip a bad file rather than failing the whole response
            import logging

            logging.getLogger(__name__).warning("Skipping %s: %s", path.name, exc)

    if not result:
        raise HTTPException(status_code=500, detail="Failed to parse any sample debrief files.")

    return result
