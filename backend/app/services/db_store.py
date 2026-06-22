"""
Database-backed store implementing the same interface as InMemoryStore.

Uses SQLite via SQLAlchemy 1.4. Swap DATABASE_URL to a Postgres URL for production.
Tests continue to use InMemoryStore via app.dependency_overrides; this store is used
when the server runs normally.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.database import db_session
from app.models.db_models import DebriefRow, ProjectRow, ReportRow
from app.schemas.models import (
    InterviewDebrief,
    ProjectCreate,
    SynthesisReport,
)

# ---------------------------------------------------------------------------
# Helpers — all extraction happens inside the session
# ---------------------------------------------------------------------------


def _row_to_project_dict(row: ProjectRow) -> dict:
    """Build a plain dict from a ProjectRow while still inside a session."""
    return {
        "project_id": row.project_id,
        "candidate_name": row.candidate_name,
        "role_title": row.role_title,
        "rubric_id": row.rubric_id,
        "debrief_count": row.debrief_count,
        "has_synthesis": row.has_synthesis,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "debrief_ids": [],
        "report_id": row.report_id,
    }


def _row_to_debrief(row: DebriefRow) -> InterviewDebrief:
    return InterviewDebrief(
        debrief_id=row.debrief_id,
        candidate_id=row.candidate_id,
        interviewer_name=row.interviewer_name,
        round_name=row.round_name or "",
        interview_date=row.interview_date or "",
        raw_text=row.raw_text,
        score_raw=row.score_raw or "",
        word_count=row.word_count or 0,
    )


# ---------------------------------------------------------------------------
# DatabaseStore
# ---------------------------------------------------------------------------


class DatabaseStore:
    """Persistent store using SQLite. Same interface as InMemoryStore."""

    # ── Projects ────────────────────────────────────────────────────────────

    def create_project(self, data: ProjectCreate) -> dict:
        project_id = str(uuid4())
        with db_session() as db:
            row = ProjectRow(
                project_id=project_id,
                candidate_name=data.candidate_name,
                role_title=data.role_title,
                rubric_id=getattr(data, "rubric_id", None),
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.flush()  # write to DB so we can read it back
            return _row_to_project_dict(row)

    def get_project(self, project_id: str) -> dict | None:
        with db_session() as db:
            row = db.query(ProjectRow).filter_by(project_id=project_id).first()
            return _row_to_project_dict(row) if row else None

    def list_projects(self) -> list[dict]:
        with db_session() as db:
            rows = db.query(ProjectRow).order_by(ProjectRow.created_at).all()
            return [_row_to_project_dict(r) for r in rows]

    def add_debrief_to_project(self, project_id: str, debrief: InterviewDebrief) -> bool:
        with db_session() as db:
            project = db.query(ProjectRow).filter_by(project_id=project_id).first()
            if project is None:
                return False
            row = DebriefRow(
                debrief_id=debrief.debrief_id,
                project_id=project_id,
                candidate_id=debrief.candidate_id,
                interviewer_name=debrief.interviewer_name,
                round_name=debrief.round_name,
                interview_date=debrief.interview_date,
                raw_text=debrief.raw_text,
                score_raw=debrief.score_raw,
                word_count=debrief.word_count,
            )
            db.add(row)
            project.debrief_count = (project.debrief_count or 0) + 1
            return True

    def get_debriefs_for_project(self, project_id: str) -> list[InterviewDebrief]:
        with db_session() as db:
            rows = db.query(DebriefRow).filter_by(project_id=project_id).all()
            return [_row_to_debrief(r) for r in rows]

    # ── Reports ─────────────────────────────────────────────────────────────

    def save_report(self, project_id: str, report: SynthesisReport) -> None:
        with db_session() as db:
            row = ReportRow(
                report_id=report.report_id,
                project_id=project_id,
                candidate_id=report.candidate_id,
                candidate_name=report.candidate_name,
                role_title=report.role_title,
                report_json=report.model_dump_json(),
                reviewer_name=report.reviewer_name,
                reviewer_approved=report.reviewer_approved,
                final_reviewer_notes=report.final_reviewer_notes,
                reviewed_at=report.reviewed_at,
                created_at=datetime.utcnow(),
            )
            db.add(row)
            project = db.query(ProjectRow).filter_by(project_id=project_id).first()
            if project:
                project.report_id = report.report_id
                project.has_synthesis = True

    def get_report(self, report_id: str) -> SynthesisReport | None:
        with db_session() as db:
            row = db.query(ReportRow).filter_by(report_id=report_id).first()
            if row is None:
                return None
            return SynthesisReport.model_validate_json(row.report_json)

    def get_report_for_project(self, project_id: str) -> SynthesisReport | None:
        with db_session() as db:
            project = db.query(ProjectRow).filter_by(project_id=project_id).first()
            if project is None or not project.report_id:
                return None
            report_id = project.report_id
        return self.get_report(report_id)

    def update_report_review(
        self,
        report_id: str,
        reviewer_name: str,
        reviewer_approved: bool,
        final_reviewer_notes: str,
    ) -> SynthesisReport | None:
        with db_session() as db:
            row = db.query(ReportRow).filter_by(report_id=report_id).first()
            if row is None:
                return None
            report = SynthesisReport.model_validate_json(row.report_json)
            report.reviewer_name = reviewer_name
            report.reviewer_approved = reviewer_approved
            report.final_reviewer_notes = final_reviewer_notes
            if reviewer_approved:
                report.reviewed_at = datetime.utcnow()
            row.report_json = report.model_dump_json()
            row.reviewer_name = reviewer_name
            row.reviewer_approved = reviewer_approved
            row.final_reviewer_notes = final_reviewer_notes
            row.reviewed_at = report.reviewed_at
            return report

    # ── Dev helpers ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Delete all rows. For testing only."""
        with db_session() as db:
            db.query(ReportRow).delete()
            db.query(DebriefRow).delete()
            db.query(ProjectRow).delete()

    @property
    def project_count(self) -> int:
        with db_session() as db:
            return db.query(ProjectRow).count()
