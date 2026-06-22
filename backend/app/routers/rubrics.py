"""
Rubric endpoints.

Endpoints:
  GET /rubrics/list           List all built-in rubrics (id + title)
  GET /rubrics/{rubric_id}    Return a specific rubric by id
  GET /rubrics/sample         Return the Data Scientist rubric (kept for compatibility)
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.models import RoleRubric

router = APIRouter(prefix="/rubrics", tags=["rubrics"])

_RUBRICS_DIR = Path(__file__).parents[2] / "sample_data" / "rubrics"


class RubricMeta(BaseModel):
    rubric_id: str
    role_title: str
    role_level: str
    department: str
    filename: str


def _load_rubric_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse rubric {path.name}: {exc}") from exc


@router.get("/list", response_model=list[RubricMeta])
async def list_rubrics() -> list[RubricMeta]:
    """Return metadata for all built-in rubrics."""
    if not _RUBRICS_DIR.exists():
        raise HTTPException(status_code=404, detail="Rubric directory not found.")
    results = []
    for path in sorted(_RUBRICS_DIR.glob("*.json")):
        data = _load_rubric_file(path)
        results.append(
            RubricMeta(
                rubric_id=data.get("rubric_id", path.stem),
                role_title=data.get("role_title", path.stem),
                role_level=data.get("role_level", ""),
                department=data.get("department", ""),
                filename=path.name,
            )
        )
    return results


@router.get("/by-id/{rubric_id}", response_model=RoleRubric)
async def get_rubric_by_id(rubric_id: str) -> RoleRubric:
    """Return a rubric by its rubric_id field."""
    if not _RUBRICS_DIR.exists():
        raise HTTPException(status_code=404, detail="Rubric directory not found.")
    for path in _RUBRICS_DIR.glob("*.json"):
        data = _load_rubric_file(path)
        if data.get("rubric_id") == rubric_id:
            return RoleRubric(**data)
    raise HTTPException(status_code=404, detail=f"Rubric '{rubric_id}' not found.")


@router.get("/sample", response_model=RoleRubric)
async def get_sample_rubric() -> RoleRubric:
    """Return the bundled Data Scientist rubric (kept for backward compatibility)."""
    path = _RUBRICS_DIR / "data_scientist_rubric.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sample rubric file not found.")
    return RoleRubric(**_load_rubric_file(path))
