"""Tests for PROMPT 15: DatabaseStore (SQLite persistence)."""

from __future__ import annotations

import pytest

from app.schemas.models import InterviewDebrief, ProjectCreate, SynthesisReport


@pytest.fixture
def db_store(tmp_path):
    """Provide a DatabaseStore backed by a fresh temp SQLite database."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    # Patch the engine in database.py to use the temp DB
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.database as database_module
    from app.models.db_models import Base

    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    original_engine = database_module.engine
    original_session = database_module.SessionLocal
    database_module.engine = test_engine
    database_module.SessionLocal = TestSession

    from app.services.db_store import DatabaseStore

    store = DatabaseStore()
    yield store

    database_module.engine = original_engine
    database_module.SessionLocal = original_session


@pytest.fixture
def sample_debrief():
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name="Alice",
        raw_text="Jordan showed strong statistical reasoning and clear communication throughout.",
    )


class TestDatabaseStoreProjects:
    def test_create_project(self, db_store):
        p = db_store.create_project(ProjectCreate(candidate_name="Jordan", role_title="DS"))
        assert p["project_id"]
        assert p["candidate_name"] == "Jordan"

    def test_get_project_returns_none_for_missing(self, db_store):
        assert db_store.get_project("nonexistent") is None

    def test_list_projects_empty_initially(self, db_store):
        assert db_store.list_projects() == []

    def test_list_projects_after_create(self, db_store):
        db_store.create_project(ProjectCreate(candidate_name="A", role_title="DS"))
        db_store.create_project(ProjectCreate(candidate_name="B", role_title="SWE"))
        assert len(db_store.list_projects()) == 2

    def test_add_debrief_to_project(self, db_store, sample_debrief):
        p = db_store.create_project(ProjectCreate(candidate_name="Jordan", role_title="DS"))
        result = db_store.add_debrief_to_project(p["project_id"], sample_debrief)
        assert result is True
        debriefs = db_store.get_debriefs_for_project(p["project_id"])
        assert len(debriefs) == 1
        assert debriefs[0].interviewer_name == "Alice"

    def test_add_debrief_to_missing_project_returns_false(self, db_store, sample_debrief):
        assert db_store.add_debrief_to_project("bad-id", sample_debrief) is False

    def test_project_count(self, db_store):
        assert db_store.project_count == 0
        db_store.create_project(ProjectCreate(candidate_name="X", role_title="Y"))
        assert db_store.project_count == 1

    def test_reset_clears_data(self, db_store):
        db_store.create_project(ProjectCreate(candidate_name="Jordan", role_title="DS"))
        db_store.reset()
        assert db_store.list_projects() == []


class TestDatabaseStoreReports:
    @pytest.fixture
    def minimal_report(self):
        return SynthesisReport(
            candidate_id="C-001",
            candidate_name="Jordan Lee",
            role_id="R-001",
            role_title="Data Scientist",
            executive_summary="Jordan demonstrated strong technical skills across multiple interviews.",
            competency_assessments=[],
            disagreement_flags=[],
            coverage_gaps=[],
            questions_for_committee=["Does Jordan connect analysis to business decisions?"],
            total_debriefs=2,
            total_signals_extracted=5,
            unsupported_claim_count=0,
            vague_claim_count=1,
            citation_validity_rate=1.0,
            extractor_version="baseline-v1",
        )

    def test_save_and_get_report(self, db_store, minimal_report):
        db_store.save_report("proj-1", minimal_report)
        fetched = db_store.get_report(minimal_report.report_id)
        assert fetched is not None
        assert fetched.candidate_name == "Jordan Lee"

    def test_get_report_returns_none_for_missing(self, db_store):
        assert db_store.get_report("no-such-id") is None

    def test_update_review_notes(self, db_store, minimal_report):
        p = db_store.create_project(ProjectCreate(candidate_name="Jordan", role_title="DS"))
        db_store.save_report(p["project_id"], minimal_report)
        updated = db_store.update_report_review(
            minimal_report.report_id,
            reviewer_name="Sarah",
            reviewer_approved=False,
            final_reviewer_notes="Needs follow-up on product judgment.",
        )
        assert updated is not None
        assert updated.final_reviewer_notes == "Needs follow-up on product judgment."

    def test_update_review_approval_sets_reviewed_at(self, db_store, minimal_report):
        db_store.save_report("proj-1", minimal_report)
        updated = db_store.update_report_review(
            minimal_report.report_id,
            reviewer_name="Sarah",
            reviewer_approved=True,
            final_reviewer_notes="",
        )
        assert updated.reviewer_approved is True
        assert updated.reviewed_at is not None

    def test_update_nonexistent_report_returns_none(self, db_store):
        result = db_store.update_report_review("bad-id", "Sarah", True, "notes")
        assert result is None

    def test_no_hire_fields_in_report(self, db_store, minimal_report):
        db_store.save_report("proj-1", minimal_report)
        fetched = db_store.get_report(minimal_report.report_id)
        assert not hasattr(fetched, "recommendation")
        assert not hasattr(fetched, "hire_decision")
