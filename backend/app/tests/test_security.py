"""Tests for PROMPT 14: privacy and security safeguards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import scrub_pii_for_log, scrub_signal_for_log, validate_debrief_text

client = TestClient(app)


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

class TestPIIScrubbing:
    def test_scrubs_email(self):
        result = scrub_pii_for_log("contact jordan@example.com for details")
        assert "jordan@example.com" not in result
        assert "[EMAIL]" in result

    def test_scrubs_phone_us(self):
        result = scrub_pii_for_log("call me at 555-867-5309")
        assert "555-867-5309" not in result
        assert "[PHONE]" in result

    def test_scrubs_ssn(self):
        result = scrub_pii_for_log("SSN is 123-45-6789")
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_leaves_normal_text_unchanged(self):
        text = "Jordan demonstrated strong statistical reasoning."
        assert scrub_pii_for_log(text) == text

    def test_scrub_signal_dict_scrubs_claim(self):
        sig = {"claim": "Contact jordan@example.com", "evidence_spans": []}
        result = scrub_signal_for_log(sig)
        assert "jordan@example.com" not in result["claim"]

    def test_scrub_signal_dict_scrubs_quoted_text(self):
        sig = {
            "claim": "some claim",
            "evidence_spans": [{"quoted_text": "email is test@corp.io", "span_id": "x"}],
        }
        result = scrub_signal_for_log(sig)
        assert "test@corp.io" not in result["evidence_spans"][0]["quoted_text"]

    def test_original_not_mutated(self):
        sig = {"claim": "reach jordan@example.com", "evidence_spans": []}
        scrub_signal_for_log(sig)
        assert "jordan@example.com" in sig["claim"]


# ---------------------------------------------------------------------------
# Debrief text validation
# ---------------------------------------------------------------------------

class TestDebriefValidation:
    def test_accepts_normal_text(self):
        text = "Jordan showed strong reasoning skills during the interview."
        assert validate_debrief_text(text) == text

    def test_rejects_too_short(self):
        with pytest.raises(Exception) as exc_info:
            validate_debrief_text("Short.")
        assert "too short" in str(exc_info.value).lower() or "422" in str(exc_info.value)

    def test_rejects_too_long(self):
        with pytest.raises(Exception):
            validate_debrief_text("x" * 60_000)


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_health_has_no_store_header(self):
        resp = client.get("/health")
        assert resp.headers.get("cache-control") == "no-store"

    def test_health_has_x_content_type_options(self):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_health_has_x_frame_options(self):
        resp = client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_post_endpoint_has_security_headers(self):
        resp = client.post("/analyze/coverage", json={"signals": [], "rubric": {
            "role_title": "DS", "competencies": [],
            "rubric_id": "r1", "role_level": "IC", "department": "Eng",
        }})
        assert resp.headers.get("x-content-type-options") == "nosniff"
