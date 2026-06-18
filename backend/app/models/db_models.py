"""
SQLAlchemy ORM models for SQLite persistence.

Schema philosophy:
- Projects, debriefs, and reports are stored as rows.
- Complex nested objects (SynthesisReport, InterviewDebrief.raw_text) are stored
  as JSON TEXT columns. This avoids dozens of tables for a portfolio project and
  keeps the migration path simple. A production version would normalize further.
- SQLAlchemy 1.4 declarative_base style (compatible with the installed version).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ProjectRow(Base):
    __tablename__ = "projects"

    project_id = Column(String(36), primary_key=True)
    candidate_name = Column(String(255), nullable=False)
    role_title = Column(String(255), nullable=False)
    rubric_id = Column(String(36), nullable=True)
    debrief_count = Column(Integer, default=0)
    has_synthesis = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    report_id = Column(String(36), nullable=True)

    debriefs = relationship("DebriefRow", back_populates="project", cascade="all, delete-orphan")


class DebriefRow(Base):
    __tablename__ = "debriefs"

    debrief_id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.project_id"), nullable=False)
    candidate_id = Column(String(36), nullable=False)
    interviewer_name = Column(String(255), nullable=False)
    round_name = Column(String(255), nullable=True)
    interview_date = Column(String(50), nullable=True)
    raw_text = Column(Text, nullable=False)
    score_raw = Column(String(50), nullable=True)
    word_count = Column(Integer, default=0)

    project = relationship("ProjectRow", back_populates="debriefs")


class ReportRow(Base):
    __tablename__ = "reports"

    report_id = Column(String(36), primary_key=True)
    project_id = Column(String(36), nullable=True)
    candidate_id = Column(String(36), nullable=False)
    candidate_name = Column(String(255), nullable=False)
    role_title = Column(String(255), nullable=False)
    # Full report JSON — includes all nested Pydantic-serialized fields
    report_json = Column(Text, nullable=False)
    reviewer_name = Column(String(255), default="")
    reviewer_approved = Column(Boolean, default=False)
    final_reviewer_notes = Column(Text, default="")
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
