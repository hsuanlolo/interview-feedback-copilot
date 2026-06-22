"""
Rubric endpoints.

For now: serve the sample rubric from disk.
Future: CRUD for user-uploaded rubrics stored in the database.

Endpoints:
  GET /rubrics/sample   Return the bundled Data Scientist rubric
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.schemas.models import RoleRubric

router = APIRouter(prefix="/rubrics", tags=["rubrics"])

# Resolve sample_data relative to this file's location.
# __file__ is backend/app/routers/rubrics.py
# parents[2] is the project root (interview-feedback-copilot/)
_SAMPLE_RUBRIC_PATH = (
    Path(__file__).parents[2] / "sample_data" / "rubrics" / "data_scientist_rubric.json"
)


@router.get("/sample", response_model=RoleRubric)
async def get_sample_rubric() -> RoleRubric:
    """Return the bundled Data Scientist / Quant Researcher rubric.

    Used to pre-populate the UI so users can see the full workflow
    without uploading their own rubric.
    """
    if not _SAMPLE_RUBRIC_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Sample rubric file not found. Check that sample_data/ exists.",
        )
    try:
        data = json.loads(_SAMPLE_RUBRIC_PATH.read_text(encoding="utf-8"))
        return RoleRubric(**data)
    except (json.JSONDecodeError, Exception) as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse sample rubric: {exc}"
        ) from exc
