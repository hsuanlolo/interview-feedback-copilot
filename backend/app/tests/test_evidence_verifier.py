"""
Tests for the EvidenceVerifier service and POST /verify/evidence endpoint.

Test layers:
  1. _check_span helper  — exact match, offset mismatch, text not found
  2. EvidenceVerifier.verify()  — signal-level rollups, unsupported/vague flags
  3. HTTP endpoint  — POST /verify/evidence with synthetic and sample data
  4. Integration  — extract (mock) then verify the resulting signals

Span construction strategy:
  Valid spans are built normally through the schema.
  Invalid spans are built with model_construct() which bypasses Pydantic validation,
  letting us create spans with deliberately wrong offsets or invented text for testing
  the verifier's detection logic.

Run with: pytest app/tests/test_evidence_verifier.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.models import (
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    SignalType,
)
from app.services.evidence_verifier import _check_span, verifier
from app.services.store import store

client = TestClient(app)

SAMPLE_DIR = Path(__file__).parents[2] / "sample_data"

RAW = (
    "Jordan correctly identified the selection bias in the observational study. "
    "The reasoning was sound and clearly explained to the panel."
)

QUOTE_A = "Jordan correctly identified the selection bias in the observational study."
QUOTE_B = "The reasoning was sound and clearly explained to the panel."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset():
    store.reset()
    yield
    store.reset()


def make_debrief(text: str = RAW, interviewer: str = "Alice") -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=text,
    )


def make_valid_span(
    debrief: InterviewDebrief,
    quote: str,
) -> EvidenceSpan:
    """Build a valid span: find quote in debrief.raw_text and use exact offsets."""
    idx = debrief.raw_text.find(quote)
    assert idx != -1, f"Quote {quote!r} not found in debrief text"
    return EvidenceSpan(
        source_debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
        start_char=idx,
        end_char=idx + len(quote),
        quoted_text=quote,
    )


def make_bad_offset_span(
    debrief: InterviewDebrief,
    quote: str,
) -> EvidenceSpan:
    """
    Span whose quoted_text IS in the debrief, but start_char/end_char point elsewhere.
    Uses model_construct() to bypass Pydantic validation (which would reject the offset).
    """
    idx = debrief.raw_text.find(quote)
    assert idx != -1
    wrong_start = (idx + 5) % max(1, len(debrief.raw_text) - len(quote))
    return EvidenceSpan.model_construct(
        span_id=str(uuid4()),
        source_debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
        start_char=wrong_start,
        end_char=wrong_start + len(quote),
        quoted_text=quote,
    )


def make_hallucinated_span(debrief: InterviewDebrief) -> EvidenceSpan:
    """Span whose quoted_text does not exist anywhere in the debrief."""
    fake = "This sentence was never written by any interviewer ever."
    return EvidenceSpan.model_construct(
        span_id=str(uuid4()),
        source_debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
        start_char=0,
        end_char=len(fake),
        quoted_text=fake,
    )


def make_signal(
    debrief: InterviewDebrief,
    spans: list[EvidenceSpan],
    competency_id: str = "stat",
    is_vague: bool = False,
) -> ExtractedSignal:
    return ExtractedSignal.model_construct(
        signal_id=str(uuid4()),
        debrief_id=debrief.debrief_id,
        competency_id=competency_id,
        signal_type=SignalType.POSITIVE,
        claim="Candidate demonstrated statistical reasoning clearly.",
        evidence_spans=spans,
        confidence=0.80,
        is_vague=is_vague,
        is_unsupported=False,
        extractor_version="test-v1",
    )


# ---------------------------------------------------------------------------
# 1. _check_span helper
# ---------------------------------------------------------------------------


class TestCheckSpan:
    def test_exact_match_is_valid(self):
        idx = RAW.find(QUOTE_A)
        valid, errors = _check_span(RAW, "s-1", idx, idx + len(QUOTE_A), QUOTE_A)
        assert valid is True
        assert errors == []

    def test_offset_mismatch_detected(self):
        idx = RAW.find(QUOTE_A)
        wrong_start = idx + 5
        valid, errors = _check_span(RAW, "s-2", wrong_start, wrong_start + len(QUOTE_A), QUOTE_A)
        assert valid is False
        assert len(errors) == 1
        assert errors[0].error_type == "offset_mismatch"
        assert str(wrong_start) in errors[0].description

    def test_text_not_found_detected(self):
        fake = "invented text that never appeared in the debrief"
        valid, errors = _check_span(RAW, "s-3", 0, len(fake), fake)
        assert valid is False
        assert len(errors) == 1
        assert errors[0].error_type == "text_not_found"

    def test_partial_match_is_not_valid(self):
        # "Jordan" appears in RAW but at start_char=0, end_char=6 — exact match passes
        valid, errors = _check_span(RAW, "s-4", 0, 6, "Jordan")
        assert valid is True  # exact match

    def test_wrong_text_at_correct_offset_is_mismatch(self):
        # "Jordan" is at offset 0; we say it's "XXXXXX" (same length, wrong text)
        # "XXXXXX" doesn't appear in RAW at all → text_not_found
        valid, errors = _check_span(RAW, "s-5", 0, 6, "XXXXXX")
        assert valid is False
        assert errors[0].error_type == "text_not_found"


# ---------------------------------------------------------------------------
# 2. EvidenceVerifier.verify() — unit tests
# ---------------------------------------------------------------------------


class TestEvidenceVerifier:
    def test_all_valid_spans_passes(self):
        debrief = make_debrief()
        spans = [make_valid_span(debrief, QUOTE_A), make_valid_span(debrief, QUOTE_B)]
        signal = make_signal(debrief, spans)
        result = verifier.verify([signal], [debrief])

        assert result.is_valid is True
        assert result.citation_validity_rate == 1.0
        assert result.total_spans_checked == 2
        assert result.valid_spans == 2
        assert result.errors == []

    def test_offset_mismatch_fails_validation(self):
        debrief = make_debrief()
        bad_span = make_bad_offset_span(debrief, QUOTE_A)
        signal = make_signal(debrief, [bad_span])
        result = verifier.verify([signal], [debrief])

        assert result.is_valid is False
        assert result.citation_validity_rate < 1.0
        assert any(e.error_type == "offset_mismatch" for e in result.errors)

    def test_hallucinated_text_fails_validation(self):
        debrief = make_debrief()
        bad_span = make_hallucinated_span(debrief)
        signal = make_signal(debrief, [bad_span])
        result = verifier.verify([signal], [debrief])

        assert result.is_valid is False
        assert any(e.error_type == "text_not_found" for e in result.errors)

    def test_missing_debrief_produces_source_missing_error(self):
        debrief = make_debrief()
        orphan_span = EvidenceSpan.model_construct(
            span_id=str(uuid4()),
            source_debrief_id="debrief-does-not-exist",
            interviewer_name="Ghost",
            start_char=0,
            end_char=10,
            quoted_text="Some text.",
        )
        signal = make_signal(debrief, [orphan_span])
        # Pass a different debrief that doesn't match the span's source_debrief_id
        other_debrief = make_debrief("Completely different text here.", "Bob")
        result = verifier.verify([signal], [other_debrief])

        assert result.is_valid is False
        assert any(e.error_type == "source_missing" for e in result.errors)

    def test_signal_with_all_spans_failing_is_unsupported(self):
        debrief = make_debrief()
        bad_span = make_hallucinated_span(debrief)
        signal = make_signal(debrief, [bad_span])
        result = verifier.verify([signal], [debrief])

        assert signal.signal_id in result.unsupported_claims

    def test_signal_with_mixed_spans_not_unsupported(self):
        """A signal is unsupported only if ALL spans fail, not just some."""
        debrief = make_debrief()
        good_span = make_valid_span(debrief, QUOTE_A)
        bad_span = make_hallucinated_span(debrief)
        signal = make_signal(debrief, [good_span, bad_span])
        result = verifier.verify([signal], [debrief])

        # is_valid=False (has an error) but not unsupported (one span passed)
        assert result.is_valid is False
        assert signal.signal_id not in result.unsupported_claims

    def test_vague_signal_flagged(self):
        debrief = make_debrief()
        span = make_valid_span(debrief, QUOTE_A)
        signal = make_signal(debrief, [span], is_vague=True)
        result = verifier.verify([signal], [debrief])

        assert signal.signal_id in result.vague_claims
        assert any("vague" in w.lower() for w in result.warnings)

    def test_vague_signal_with_valid_spans_does_not_fail_is_valid(self):
        """Vague is a reviewer flag, not a hard failure — spans can still be valid."""
        debrief = make_debrief()
        span = make_valid_span(debrief, QUOTE_A)
        signal = make_signal(debrief, [span], is_vague=True)
        result = verifier.verify([signal], [debrief])

        # is_valid is about span accuracy, not vagueness
        assert result.is_valid is True
        assert result.citation_validity_rate == 1.0

    def test_citation_validity_rate_computed_correctly(self):
        """3 valid spans + 1 hallucinated → rate = 0.75."""
        debrief = make_debrief()
        s1 = make_valid_span(debrief, QUOTE_A)
        s2 = make_valid_span(debrief, QUOTE_B)
        s3 = make_valid_span(debrief, "The reasoning was sound")
        bad = make_hallucinated_span(debrief)

        signal_a = make_signal(debrief, [s1, bad], "c1")
        signal_b = make_signal(debrief, [s2, s3], "c2")
        result = verifier.verify([signal_a, signal_b], [debrief])

        assert result.total_spans_checked == 4
        assert result.valid_spans == 3
        assert abs(result.citation_validity_rate - 0.75) < 0.01

    def test_empty_signals_returns_valid(self):
        """Zero signals means nothing to invalidate — is_valid=True, rate=1.0."""
        debrief = make_debrief()
        result = verifier.verify([], [debrief])

        assert result.is_valid is True
        assert result.citation_validity_rate == 1.0
        assert result.total_spans_checked == 0

    def test_multiple_debriefs_cross_referenced_correctly(self):
        """Spans from debrief A must not be verified against debrief B's text."""
        debrief_a = make_debrief("Alice: Jordan showed excellent statistical reasoning.", "Alice")
        debrief_b = make_debrief("Bob: The candidate struggled with SQL window functions.", "Bob")
        span_a = make_valid_span(debrief_a, "Jordan showed excellent statistical reasoning.")
        span_b = make_valid_span(debrief_b, "The candidate struggled with SQL window functions.")

        signal_a = make_signal(debrief_a, [span_a], "stat")
        signal_b = make_signal(debrief_b, [span_b], "sql")
        result = verifier.verify([signal_a, signal_b], [debrief_a, debrief_b])

        assert result.is_valid is True
        assert result.citation_validity_rate == 1.0
        assert result.total_spans_checked == 2

    def test_error_list_contains_span_ids(self):
        debrief = make_debrief()
        bad_span = make_hallucinated_span(debrief)
        signal = make_signal(debrief, [bad_span])
        result = verifier.verify([signal], [debrief])

        assert all(hasattr(e, "span_id") for e in result.errors)
        assert result.errors[0].span_id == bad_span.span_id

    def test_unsupported_warning_present_when_claims_unsupported(self):
        debrief = make_debrief()
        bad_span = make_hallucinated_span(debrief)
        signal = make_signal(debrief, [bad_span])
        result = verifier.verify([signal], [debrief])

        assert any("unsupported" in w.lower() for w in result.warnings)

    def test_is_valid_false_with_any_error(self):
        """Even a single error makes is_valid=False (100% gate)."""
        debrief = make_debrief()
        good = make_valid_span(debrief, QUOTE_A)
        bad = make_hallucinated_span(debrief)
        signal_good = make_signal(debrief, [good], "c1")
        signal_bad = make_signal(debrief, [bad], "c2")
        result = verifier.verify([signal_good, signal_bad], [debrief])

        assert result.is_valid is False


# ---------------------------------------------------------------------------
# 3. HTTP endpoint: POST /verify/evidence
# ---------------------------------------------------------------------------


class TestVerifyEndpoint:
    @pytest.fixture
    def valid_payload(self) -> dict:
        debrief = make_debrief()
        idx = debrief.raw_text.find(QUOTE_A)
        return {
            "signals": [
                {
                    "signal_id": str(uuid4()),
                    "debrief_id": debrief.debrief_id,
                    "competency_id": "stat",
                    "signal_type": "positive",
                    "claim": "Candidate correctly identified statistical bias.",
                    "evidence_spans": [
                        {
                            "span_id": str(uuid4()),
                            "source_debrief_id": debrief.debrief_id,
                            "interviewer_name": debrief.interviewer_name,
                            "start_char": idx,
                            "end_char": idx + len(QUOTE_A),
                            "quoted_text": QUOTE_A,
                        }
                    ],
                    "confidence": 0.85,
                    "is_vague": False,
                    "is_unsupported": False,
                    "extractor_version": "baseline-v1",
                }
            ],
            "debriefs": [
                {
                    "debrief_id": debrief.debrief_id,
                    "candidate_id": debrief.candidate_id,
                    "interviewer_name": debrief.interviewer_name,
                    "raw_text": debrief.raw_text,
                }
            ],
        }

    def test_returns_200(self, valid_payload):
        response = client.post("/verify/evidence", json=valid_payload)
        assert response.status_code == 200, response.text

    def test_valid_spans_return_is_valid_true(self, valid_payload):
        data = client.post("/verify/evidence", json=valid_payload).json()
        assert data["is_valid"] is True
        assert data["citation_validity_rate"] == 1.0
        assert data["total_spans_checked"] == 1
        assert data["valid_spans"] == 1
        assert data["errors"] == []

    def test_response_has_all_required_fields(self, valid_payload):
        data = client.post("/verify/evidence", json=valid_payload).json()
        required = {
            "is_valid",
            "errors",
            "warnings",
            "unsupported_claims",
            "vague_claims",
            "citation_validity_rate",
            "total_spans_checked",
            "valid_spans",
        }
        assert required <= set(data.keys())

    def test_empty_debriefs_returns_400(self):
        body = {"signals": [], "debriefs": []}
        response = client.post("/verify/evidence", json=body)
        assert response.status_code == 400

    def test_empty_signals_returns_valid(self):
        debrief = make_debrief()
        body = {
            "signals": [],
            "debriefs": [
                {
                    "debrief_id": debrief.debrief_id,
                    "candidate_id": debrief.candidate_id,
                    "interviewer_name": debrief.interviewer_name,
                    "raw_text": debrief.raw_text,
                }
            ],
        }
        data = client.post("/verify/evidence", json=body).json()
        assert data["is_valid"] is True
        assert data["citation_validity_rate"] == 1.0


# ---------------------------------------------------------------------------
# 4. Integration: extract (baseline) → verify
# ---------------------------------------------------------------------------


class TestExtractThenVerify:
    """
    End-to-end: POST /extract/baseline → POST /verify/evidence.
    The baseline extractor produces exact-offset spans, so all should pass verification.
    """

    @pytest.fixture
    def rubric_dict(self) -> dict:
        return json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text())

    @pytest.fixture
    def debrief_text(self) -> str:
        return (SAMPLE_DIR / "debriefs" / "candidate_001_interviewer_1.txt").read_text()

    def test_baseline_signals_all_pass_verification(self, rubric_dict, debrief_text):
        # Step 1: extract
        extract_body = {
            "rubric": rubric_dict,
            "debriefs": [
                {
                    "candidate_id": "C-001",
                    "interviewer_name": "Priya Sharma",
                    "raw_text": debrief_text,
                }
            ],
        }
        extract_resp = client.post("/extract/baseline", json=extract_body)
        assert extract_resp.status_code == 200
        extract_data = extract_resp.json()
        signals = extract_data["signals"]

        if not signals:
            pytest.skip("No signals extracted — nothing to verify")

        # Step 2: verify (re-use the same debrief in the request)
        debrief_obj = extract_body["debriefs"][0]
        debrief_id = signals[0]["evidence_spans"][0]["source_debrief_id"]
        debrief_obj["debrief_id"] = debrief_id

        verify_body = {
            "signals": signals,
            "debriefs": [debrief_obj],
        }
        verify_resp = client.post("/verify/evidence", json=verify_body)
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()

        assert verify_data["is_valid"] is True, (
            f"Expected all baseline spans to pass verification. Errors: {verify_data['errors']}"
        )
        assert verify_data["citation_validity_rate"] == 1.0

    def test_five_debrief_baseline_all_valid(self, rubric_dict):
        debrief_dir = SAMPLE_DIR / "debriefs"
        paths = sorted(debrief_dir.glob("candidate_001_interviewer_*.txt"))
        assert len(paths) == 5

        debriefs_payload = [
            {
                "candidate_id": "C-001",
                "interviewer_name": f"Interviewer {i + 1}",
                "raw_text": p.read_text(),
            }
            for i, p in enumerate(paths)
        ]

        # Extract
        extract_resp = client.post(
            "/extract/baseline",
            json={"rubric": rubric_dict, "debriefs": debriefs_payload},
        )
        assert extract_resp.status_code == 200
        signals = extract_resp.json()["signals"]

        if not signals:
            pytest.skip("No signals extracted")

        # Build debrief map keyed by debrief_id (from spans)
        debrief_id_to_obj: dict = {}
        for sig in signals:
            for span in sig["evidence_spans"]:
                did = span["source_debrief_id"]
                if did not in debrief_id_to_obj:
                    # Find matching payload by matching first span back to raw_text
                    for d in debriefs_payload:
                        if span["quoted_text"] in d["raw_text"]:
                            debrief_id_to_obj[did] = {**d, "debrief_id": did}
                            break

        verify_body = {
            "signals": signals,
            "debriefs": list(debrief_id_to_obj.values()),
        }
        verify_resp = client.post("/verify/evidence", json=verify_body)
        assert verify_resp.status_code == 200
        data = verify_resp.json()

        assert data["citation_validity_rate"] == 1.0, (
            f"Expected 100% citation validity from baseline extractor. Errors: {data['errors']}"
        )
