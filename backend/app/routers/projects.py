"""
Project management endpoints.

A "project" is one candidate slate: one candidate, one rubric,
and however many debriefs the loop produced.

Endpoints:
  POST   /projects              Create a new project
  GET    /projects              List all projects
  GET    /projects/{id}         Get one project with its debriefs
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException

from app.schemas.models import ProjectCreate
from app.services.store import store

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", status_code=201)
async def create_project(data: ProjectCreate) -> dict:
    """Create a new interview project for one candidate."""
    return store.create_project(data)


@router.get("")
async def list_projects() -> List[dict]:
    """List all projects (newest first)."""
    return list(reversed(store.list_projects()))


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict:
    """Get a project including its attached debriefs."""
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_id}' not found.",
        )
    # Attach debrief summaries (not full text — keeps response size reasonable)
    debriefs = store.get_debriefs_for_project(project_id)
    return {
        **project,
        "debriefs": [
            {
                "debrief_id": d.debrief_id,
                "interviewer_name": d.interviewer_name,
                "round_name": d.round_name,
                "word_count": d.word_count,
                "score_raw": d.score_raw,
            }
            for d in debriefs
        ],
    }
