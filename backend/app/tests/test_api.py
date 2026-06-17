"""
Integration tests for the FastAPI endpoints.

Uses FastAPI's TestClient (backed by httpx) — no real network calls needed.
Each test class resets the in-memory store so tests are independent.

Run with: pytest app/tests/test_api.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.store import store

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before every test."""
    store.reset()
    yield
    store.reset()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_response_shape(self):
        data = client.get("/health").json()
        assert "status" in data
        assert "version" in data
        assert "llm_mode" in data
        assert data["status"] == "ok"

    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "docs" in response.json()


# ---------------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------------


class TestSampleRubric:
    def test_returns_200(self):
        response = client.get("/rubrics/sample")
        assert response.status_code == 200

    def test_has_competencies(self):
        data = client.get("/rubrics/sample").json()
        assert "competencies" in data
        assert len(data["competencies"]) >= 1

    def test_all_competencies_have_required_fields(self):
        data = client.get("/rubrics/sample").json()
        for comp in data["competencies"]:
            assert "competency_id" in comp, f"Missing competency_id: {comp}"
            assert "name" in comp
            assert "description" in comp

    def test_rubric_has_correct_role(self):
        data = client.get("/rubrics/sample").json()
        assert "Data Scientist" in data["role_title"] or "Quant" in data["role_title"]

    def test_sample_rubric_has_stat_reasoning(self):
        data = client.get("/rubrics/sample").json()
        ids = [c["competency_id"] for c in data["competencies"]]
        assert "stat_reasoning" in ids


# ---------------------------------------------------------------------------
# Debriefs
# ---------------------------------------------------------------------------


class TestSampleDebriefs:
    def test_returns_200(self):
        response = client.get("/debriefs/sample")
        assert response.status_code == 200

    def test_returns_five_debriefs(self):
        data = client.get("/debriefs/sample").json()
        assert len(data) == 5

    def test_each_debrief_has_required_fields(self):
        data = client.get("/debriefs/sample").json()
        for debrief in data:
            assert "debrief_id" in debrief
            assert "interviewer_name" in debrief
            assert "raw_text" in debrief
            assert len(debrief["raw_text"]) > 50, "Debrief text seems too short"

    def test_debrief_word_counts_are_positive(self):
        data = client.get("/debriefs/sample").json()
        for debrief in data:
            assert debrief["word_count"] > 0

    def test_debriefs_have_different_interviewers(self):
        data = client.get("/debriefs/sample").json()
        names = [d["interviewer_name"] for d in data]
        assert len(set(names)) == 5, f"Expected 5 unique interviewers, got: {names}"

    def test_debriefs_have_scores(self):
        data = client.get("/debriefs/sample").json()
        # At least some debriefs should have a raw score
        scores = [d["score_raw"] for d in data if d.get("score_raw")]
        assert len(scores) >= 1


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class TestCreateProject:
    def test_returns_201(self):
        response = client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        )
        assert response.status_code == 201

    def test_response_has_project_id(self):
        data = client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        ).json()
        assert "project_id" in data
        assert len(data["project_id"]) > 0

    def test_response_echoes_candidate_name(self):
        data = client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        ).json()
        assert data["candidate_name"] == "Jordan Lee"

    def test_new_project_has_zero_debriefs(self):
        data = client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        ).json()
        assert data["debrief_count"] == 0

    def test_new_project_has_no_synthesis(self):
        data = client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        ).json()
        assert data["has_synthesis"] is False

    def test_missing_candidate_name_returns_422(self):
        response = client.post("/projects", json={"role_title": "Data Scientist"})
        assert response.status_code == 422

    def test_missing_role_title_returns_422(self):
        response = client.post("/projects", json={"candidate_name": "Jordan Lee"})
        assert response.status_code == 422


class TestGetProject:
    def _create(self) -> str:
        return client.post(
            "/projects",
            json={"candidate_name": "Jordan Lee", "role_title": "Data Scientist"},
        ).json()["project_id"]

    def test_returns_200_for_existing(self):
        project_id = self._create()
        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200

    def test_returns_correct_project(self):
        project_id = self._create()
        data = client.get(f"/projects/{project_id}").json()
        assert data["project_id"] == project_id
        assert data["candidate_name"] == "Jordan Lee"

    def test_returns_404_for_nonexistent(self):
        response = client.get("/projects/does-not-exist")
        assert response.status_code == 404

    def test_404_body_has_detail(self):
        response = client.get("/projects/does-not-exist")
        assert "detail" in response.json()

    def test_includes_debriefs_list(self):
        project_id = self._create()
        data = client.get(f"/projects/{project_id}").json()
        assert "debriefs" in data
        assert data["debriefs"] == []  # empty on creation


class TestListProjects:
    def test_empty_list_initially(self):
        data = client.get("/projects").json()
        assert data == []

    def test_reflects_created_projects(self):
        client.post("/projects", json={"candidate_name": "A", "role_title": "DS"})
        client.post("/projects", json={"candidate_name": "B", "role_title": "DS"})
        data = client.get("/projects").json()
        assert len(data) == 2

    def test_most_recent_first(self):
        client.post("/projects", json={"candidate_name": "First", "role_title": "DS"})
        client.post("/projects", json={"candidate_name": "Second", "role_title": "DS"})
        data = client.get("/projects").json()
        # reversed() in the router means most recent is first
        assert data[0]["candidate_name"] == "Second"
