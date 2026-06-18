"""
In-memory project store.

Intentionally simple: a plain dict, no persistence, no thread safety.
This is replaced with a real database in PROMPT 15.
The value of keeping it simple now: the API and business logic are tested
independently of any ORM or migration concerns.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from app.schemas.models import (
    InterviewDebrief,
    ProjectCreate,
    ProjectSummary,
    SynthesisReport,
)


class InMemoryStore:
    """Stores projects, debriefs, and reports in memory.

    Data is lost when the server restarts. That is expected and acceptable for
    local development and demos.
    """

    def __init__(self) -> None:
        # project_id → project dict
        self._projects: Dict[str, dict] = OrderedDict()
        # debrief_id → InterviewDebrief
        self._debriefs: Dict[str, InterviewDebrief] = {}
        # report_id → SynthesisReport
        self._reports: Dict[str, SynthesisReport] = {}

    # ── Projects ────────────────────────────────────────────────────────────

    def create_project(self, data: ProjectCreate) -> dict:
        project_id = str(uuid4())
        project = {
            "project_id": project_id,
            "candidate_name": data.candidate_name,
            "role_title": data.role_title,
            "rubric_id": data.rubric_id,
            "debrief_count": 0,
            "has_synthesis": False,
            "created_at": datetime.utcnow().isoformat(),
            "debrief_ids": [],
            "report_id": None,
        }
        self._projects[project_id] = project
        return project

    def get_project(self, project_id: str) -> Optional[dict]:
        return self._projects.get(project_id)

    def list_projects(self) -> List[dict]:
        return list(self._projects.values())

    def add_debrief_to_project(self, project_id: str, debrief: InterviewDebrief) -> bool:
        project = self._projects.get(project_id)
        if project is None:
            return False
        self._debriefs[debrief.debrief_id] = debrief
        project["debrief_ids"].append(debrief.debrief_id)
        project["debrief_count"] = len(project["debrief_ids"])
        return True

    def get_debriefs_for_project(self, project_id: str) -> List[InterviewDebrief]:
        project = self._projects.get(project_id)
        if project is None:
            return []
        return [self._debriefs[did] for did in project["debrief_ids"] if did in self._debriefs]

    # ── Reports ─────────────────────────────────────────────────────────────

    def save_report(self, project_id: str, report: SynthesisReport) -> None:
        self._reports[report.report_id] = report
        if project_id in self._projects:
            self._projects[project_id]["report_id"] = report.report_id
            self._projects[project_id]["has_synthesis"] = True

    def get_report(self, report_id: str) -> Optional[SynthesisReport]:
        return self._reports.get(report_id)

    def get_report_for_project(self, project_id: str) -> Optional[SynthesisReport]:
        project = self._projects.get(project_id)
        if project is None or project.get("report_id") is None:
            return None
        return self._reports.get(project["report_id"])

    def update_report_review(
        self,
        report_id: str,
        reviewer_name: str,
        reviewer_approved: bool,
        final_reviewer_notes: str,
    ) -> Optional[SynthesisReport]:
        """Apply reviewer edits to a stored report. Returns None if not found."""
        from datetime import datetime as _dt

        report = self._reports.get(report_id)
        if report is None:
            return None
        report.reviewer_name = reviewer_name
        report.reviewer_approved = reviewer_approved
        report.final_reviewer_notes = final_reviewer_notes
        if reviewer_approved:
            report.reviewed_at = _dt.utcnow()
        return report

    # ── Dev helpers ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all data. Used in tests to isolate state between test cases."""
        self._projects.clear()
        self._debriefs.clear()
        self._reports.clear()

    @property
    def project_count(self) -> int:
        return len(self._projects)


# Module-level singleton.
# FastAPI routers import this directly.
# Tests call store.reset() in a fixture to start clean.
store = InMemoryStore()
