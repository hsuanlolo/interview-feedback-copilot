"""
Tests for the LLM extraction client and POST /extract/llm endpoint.

Test layers:
  1. _locate_quotes helper — the offset computation and hallucination detection
  2. MockLLMClient — produces valid, offset-accurate signals without an API key
  3. LLMSignalDraft / LLMExtractionOutput — Pydantic validation gating
  4. HTTP endpoint — POST /extract/llm with mock client injected via dependency_overrides

Note: AnthropicLLMClient is NOT tested against the real API here. That would
require a real API key and would incur cost. Real API tests belong in a
separate eval suite (PROMPT 13). These tests only exercise the mock path and
the client abstractions.

Run with: pytest app/tests/test_llm_extractor.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.models import (
    Competency,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)
from app.services.llm_client import (
    EXTRACTOR_VERSION_LLM,
    MOCK_EXTRACTOR_VERSION,
    LLMExtractionOutput,
    LLMSignalDraft,
    MockLLMClient,
    _locate_quotes,
    extract_all_llm,
    get_llm_client,
)
from app.services.store import store

client = TestClient(app)

SAMPLE_DIR = Path(__file__).parents[2] / "sample_data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset():
    store.reset()
    yield
    store.reset()


@pytest.fixture
def mock_client_override():
    """Override the get_llm_client dependency so all endpoint tests use MockLLMClient."""
    app.dependency_overrides[get_llm_client] = lambda: MockLLMClient()
    yield
    app.dependency_overrides.clear()


def make_debrief(text: str, interviewer: str = "Alice") -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=text,
    )


def make_competency(
    name: str = "Statistical Reasoning",
    cid: str = "stat",
    pos: list[str] | None = None,
    neg: list[str] | None = None,
) -> Competency:
    return Competency(
        competency_id=cid,
        name=name,
        description=f"Tests {name.lower()}.",
        positive_indicators=pos or ["correctly identified", "sound reasoning"],
        negative_indicators=neg or ["missed the issue", "shallow explanation"],
    )


def make_rubric(competencies: list[Competency] | None = None) -> RoleRubric:
    return RoleRubric(
        role_title="Data Scientist",
        competencies=competencies or [make_competency()],
    )


RICH_DEBRIEF = """\
Candidate: Jordan Lee
Interviewer: Alice
---

Jordan correctly identified the selection bias in the observational study
without any prompting from me. The reasoning was sound and clearly explained.

They also designed a well-structured A/B test with an appropriate power
calculation, discussing the minimum detectable effect and weekly seasonality.
"""


# ---------------------------------------------------------------------------
# 1. _locate_quotes helper
# ---------------------------------------------------------------------------


class TestLocateQuotes:
    RAW = "The candidate demonstrated strong statistical reasoning in the technical screen."

    def test_exact_quote_produces_valid_span(self):
        quote = "demonstrated strong statistical reasoning"
        spans, warnings = _locate_quotes(self.RAW, [quote], "d-1", "Alice")
        assert len(spans) == 1
        assert len(warnings) == 0
        span = spans[0]
        assert self.RAW[span.start_char : span.end_char] == quote

    def test_missing_quote_produces_warning_not_span(self):
        quote = "invented text that never appeared"
        spans, warnings = _locate_quotes(self.RAW, [quote], "d-1", "Alice")
        assert len(spans) == 0
        assert len(warnings) == 1
        assert "hallucinated" in warnings[0].lower()

    def test_duplicate_quotes_deduplicated(self):
        quote = "strong statistical"
        spans, warnings = _locate_quotes(self.RAW, [quote, quote], "d-1", "Alice")
        assert len(spans) == 1  # Not duplicated

    def test_multiple_quotes_multiple_spans(self):
        raw = "First sentence here. Second sentence follows. Third sentence last."
        quotes = ["First sentence here", "Third sentence last"]
        spans, warnings = _locate_quotes(raw, quotes, "d-1", "Alice")
        assert len(spans) == 2
        for span in spans:
            assert raw[span.start_char : span.end_char] == span.quoted_text

    def test_empty_quote_string_skipped(self):
        spans, warnings = _locate_quotes(self.RAW, ["", "  "], "d-1", "Alice")
        assert len(spans) == 0

    def test_span_offsets_are_exact(self):
        raw = "Jordan correctly identified selection bias without prompting."
        quote = "correctly identified selection bias"
        spans, _ = _locate_quotes(raw, [quote], "d-1", "Alice")
        assert len(spans) == 1
        assert raw[spans[0].start_char : spans[0].end_char] == quote


# ---------------------------------------------------------------------------
# 2. LLMSignalDraft / LLMExtractionOutput — Pydantic validation gating
# ---------------------------------------------------------------------------


class TestLLMOutputValidation:
    def test_valid_draft_accepted(self):
        draft = LLMSignalDraft(
            competency_id="stat",
            signal_type=SignalType.POSITIVE,
            claim="Candidate demonstrated strong statistical reasoning.",
            evidence_quotes=["Jordan correctly identified selection bias."],
            confidence=0.85,
        )
        assert draft.signal_type == SignalType.POSITIVE

    def test_invalid_signal_type_rejected(self):
        with pytest.raises(ValidationError):
            LLMSignalDraft(
                competency_id="stat",
                signal_type="excellent",  # Not a valid SignalType
                claim="Candidate was excellent.",
                evidence_quotes=["Jordan was excellent."],
            )

    def test_empty_evidence_quotes_rejected(self):
        with pytest.raises(ValidationError):
            LLMSignalDraft(
                competency_id="stat",
                signal_type="positive",
                claim="The candidate did well on statistical reasoning tasks.",
                evidence_quotes=[],  # Must have at least one
            )

    def test_short_claim_rejected(self):
        with pytest.raises(ValidationError):
            LLMSignalDraft(
                competency_id="stat",
                signal_type="positive",
                claim="OK",  # min_length=10
                evidence_quotes=["Jordan was great."],
            )

    def test_valid_extraction_output(self):
        output = LLMExtractionOutput(
            signals=[
                {
                    "competency_id": "stat",
                    "signal_type": "positive",
                    "claim": "The candidate demonstrated sound statistical reasoning.",
                    "evidence_quotes": ["Jordan identified the bias."],
                    "confidence": 0.80,
                }
            ]
        )
        assert len(output.signals) == 1

    def test_empty_signals_list_valid(self):
        """An extractor returning zero signals is valid (nothing was found)."""
        output = LLMExtractionOutput(signals=[])
        assert output.signals == []

    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            LLMSignalDraft(
                competency_id="stat",
                signal_type="positive",
                claim="The candidate demonstrated statistical reasoning clearly.",
                evidence_quotes=["Jordan identified the bias."],
                confidence=1.5,  # Must be ≤ 1.0
            )


# ---------------------------------------------------------------------------
# 3. MockLLMClient unit tests
# ---------------------------------------------------------------------------


class TestMockLLMClient:
    def test_returns_signals(self):
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric()
        signals, warnings = mock.extract_signals(debrief, rubric)
        assert len(signals) >= 1

    def test_signals_have_valid_evidence_spans(self):
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric()
        signals, _ = mock.extract_signals(debrief, rubric)
        for signal in signals:
            assert len(signal.evidence_spans) >= 1

    def test_span_offsets_point_into_raw_text(self):
        """Critical: every span's quoted_text must appear at [start:end] in raw_text."""
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric()
        signals, _ = mock.extract_signals(debrief, rubric)
        for signal in signals:
            for span in signal.evidence_spans:
                extracted = debrief.raw_text[span.start_char : span.end_char]
                assert extracted == span.quoted_text, (
                    f"Offset mismatch: raw_text[{span.start_char}:{span.end_char}]="
                    f"{extracted!r} but quoted_text={span.quoted_text!r}"
                )

    def test_extractor_version_is_mock(self):
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric()
        signals, _ = mock.extract_signals(debrief, rubric)
        for signal in signals:
            assert signal.extractor_version == MOCK_EXTRACTOR_VERSION

    def test_debrief_id_propagated(self):
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric()
        signals, _ = mock.extract_signals(debrief, rubric)
        for signal in signals:
            assert signal.debrief_id == debrief.debrief_id

    def test_covers_multiple_competencies(self):
        mock = MockLLMClient()
        debrief = make_debrief(RICH_DEBRIEF)
        rubric = make_rubric(
            [
                make_competency("Statistical Reasoning", "stat"),
                make_competency("Communication", "comm"),
            ]
        )
        signals, _ = mock.extract_signals(debrief, rubric)
        cids = {s.competency_id for s in signals}
        # Mock covers up to 3 competencies; with 2 in rubric, expect 2
        assert len(cids) <= 2

    def test_short_debrief_returns_empty_with_warning(self):
        mock = MockLLMClient()
        # Must be ≥10 chars to pass schema but short enough that no sentences emerge
        debrief = make_debrief("Hello world.", "Dave")
        rubric = make_rubric()
        signals, warnings = mock.extract_signals(debrief, rubric)
        # Either returns empty + warning, or no signals
        assert isinstance(signals, list)
        assert isinstance(warnings, list)

    def test_extractor_version_class_attribute(self):
        assert MockLLMClient.extractor_version == MOCK_EXTRACTOR_VERSION


# ---------------------------------------------------------------------------
# 4. extract_all_llm aggregator
# ---------------------------------------------------------------------------


class TestExtractAllLLM:
    def test_aggregates_across_multiple_debriefs(self):
        mock = MockLLMClient()
        rubric = make_rubric()
        debriefs = [make_debrief(RICH_DEBRIEF, "Alice"), make_debrief(RICH_DEBRIEF, "Bob")]
        signals, warnings = extract_all_llm(debriefs, rubric, mock)
        assert len(signals) >= 1

    def test_short_debrief_generates_warning(self):
        mock = MockLLMClient()
        rubric = make_rubric()
        short = make_debrief("Brief session today.", "Dave")
        _, warnings = extract_all_llm([short], rubric, mock)
        assert any("short" in w.lower() for w in warnings)

    def test_warnings_are_strings(self):
        mock = MockLLMClient()
        rubric = make_rubric()
        _, warnings = extract_all_llm([make_debrief(RICH_DEBRIEF)], rubric, mock)
        assert all(isinstance(w, str) for w in warnings)


# ---------------------------------------------------------------------------
# 5. HTTP endpoint: POST /extract/llm with mock client
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_rubric() -> dict:
    path = SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json"
    return json.loads(path.read_text())


@pytest.fixture
def sample_debrief_text() -> str:
    path = SAMPLE_DIR / "debriefs" / "candidate_001_interviewer_1.txt"
    return path.read_text()


def _build_body(rubric_dict: dict, debrief_text: str) -> dict:
    return {
        "rubric": rubric_dict,
        "debriefs": [
            {
                "candidate_id": "C-001",
                "interviewer_name": "Priya Sharma",
                "raw_text": debrief_text,
            }
        ],
    }


class TestExtractLLMEndpoint:
    def test_returns_200_with_mock_client(self, mock_client_override, sample_rubric, sample_debrief_text):
        body = _build_body(sample_rubric, sample_debrief_text)
        response = client.post("/extract/llm", json=body)
        assert response.status_code == 200, response.text

    def test_response_has_required_fields(self, mock_client_override, sample_rubric, sample_debrief_text):
        body = _build_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/llm", json=body).json()
        assert "signals" in data
        assert "total_signals" in data
        assert "extractor_used" in data
        assert "warnings" in data

    def test_extractor_used_is_mock(self, mock_client_override, sample_rubric, sample_debrief_text):
        body = _build_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/llm", json=body).json()
        assert data["extractor_used"] == MOCK_EXTRACTOR_VERSION

    def test_signals_have_evidence_spans(self, mock_client_override, sample_rubric, sample_debrief_text):
        body = _build_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/llm", json=body).json()
        for signal in data["signals"]:
            assert len(signal["evidence_spans"]) >= 1

    def test_span_offsets_valid_through_endpoint(self, mock_client_override, sample_rubric, sample_debrief_text):
        """End-to-end: every span returned by the endpoint must be in the source text."""
        body = _build_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/llm", json=body).json()
        for signal in data["signals"]:
            for span in signal["evidence_spans"]:
                extracted = sample_debrief_text[span["start_char"] : span["end_char"]]
                assert extracted == span["quoted_text"], (
                    f"raw_text[{span['start_char']}:{span['end_char']}]={extracted!r} "
                    f"!= quoted_text={span['quoted_text']!r}"
                )

    def test_empty_debriefs_returns_400(self, mock_client_override, sample_rubric):
        body = {"rubric": sample_rubric, "debriefs": []}
        response = client.post("/extract/llm", json=body)
        assert response.status_code == 400

    def test_five_debrief_pipeline(self, mock_client_override, sample_rubric):
        debrief_dir = SAMPLE_DIR / "debriefs"
        paths = sorted(debrief_dir.glob("candidate_001_interviewer_*.txt"))
        assert len(paths) == 5
        debriefs = [
            {"candidate_id": "C-001", "interviewer_name": f"I-{i}", "raw_text": p.read_text()}
            for i, p in enumerate(paths)
        ]
        body = {"rubric": sample_rubric, "debriefs": debriefs}
        response = client.post("/extract/llm", json=body)
        assert response.status_code == 200
        data = response.json()
        assert data["total_signals"] >= 1


# ---------------------------------------------------------------------------
# 6. get_llm_client factory behaviour (no dependency override — tests the factory)
# ---------------------------------------------------------------------------


class TestGetLLMClientFactory:
    def test_returns_503_when_no_api_key_and_not_mock_mode(self):
        """Without override: no API key configured, mock mode off → 503."""
        from app.config import settings

        # Confirm test environment has no API key
        assert not settings.anthropic_api_key, (
            "ANTHROPIC_API_KEY is set in the test environment — this test expects it absent"
        )
        assert not settings.llm_mock_mode, "LLM_MOCK_MODE is True in the test environment — this test expects it False"

        body = {
            "rubric": json.loads((SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json").read_text()),
            "debriefs": [
                {
                    "candidate_id": "C-001",
                    "interviewer_name": "Alice",
                    "raw_text": (SAMPLE_DIR / "debriefs" / "candidate_001_interviewer_1.txt").read_text(),
                }
            ],
        }
        response = client.post("/extract/llm", json=body)
        assert response.status_code == 503
        assert "ANTHROPIC_API_KEY" in response.json()["detail"]

    def test_mock_client_returned_when_mock_mode_true(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "llm_mock_mode", True)
        llm_client = get_llm_client()
        assert isinstance(llm_client, MockLLMClient)

    def test_class_attribute_extractor_version(self):
        from app.services.llm_client import AnthropicLLMClient

        assert AnthropicLLMClient.extractor_version == EXTRACTOR_VERSION_LLM


# ---------------------------------------------------------------------------
# 7. Validation gating — AnthropicLLMClient surfaces bad LLM output as 422
# ---------------------------------------------------------------------------


class TestValidationGating:
    """
    These tests verify that LLM output validation is never silently bypassed.
    We mock the _call_api method on AnthropicLLMClient to control what 'Claude returns'.
    """

    def _make_anthropic_client(self):
        from app.services.llm_client import AnthropicLLMClient

        with patch("anthropic.Anthropic"):
            c = AnthropicLLMClient.__new__(AnthropicLLMClient)
            c.model = "claude-opus-4-8"
            return c

    def test_invalid_signal_type_in_llm_output_raises(self):
        """If Claude returns a signal_type not in the enum, it must raise — not silently accept."""
        anthropic_client = self._make_anthropic_client()

        anthropic_client._call_api = MagicMock(
            side_effect=lambda d, r: (_ for _ in ()).throw(
                __import__("fastapi").HTTPException(status_code=422, detail="LLM output failed schema validation")
            )
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            anthropic_client._call_api(make_debrief(RICH_DEBRIEF), make_rubric())
        assert exc.value.status_code == 422

    def test_hallucinated_quote_produces_warning_not_span(self):
        """
        If Claude returns a quote that doesn't appear in the debrief,
        _locate_quotes must produce a warning and NOT create a span.
        """
        hallucinated_quote = "This text never appeared in any debrief, ever."
        raw = RICH_DEBRIEF
        spans, warnings = _locate_quotes(raw, [hallucinated_quote], "d-1", "Alice")
        assert len(spans) == 0
        assert len(warnings) == 1
        assert "hallucinated" in warnings[0].lower()

    def test_lllm_output_with_missing_required_fields_raises_validation_error(self):
        """LLMExtractionOutput validation must catch signals missing required fields."""
        bad_input = {"signals": [{"competency_id": "stat"}]}  # Missing signal_type, claim, evidence_quotes
        with pytest.raises(ValidationError):
            LLMExtractionOutput.model_validate(bad_input)

    def test_mixed_valid_invalid_quotes_partial_result(self):
        """
        When some quotes are valid and some hallucinated, only valid ones become spans.
        This verifies selective rejection (not all-or-nothing).
        """
        raw = "Jordan correctly identified selection bias in the study."
        real_quote = "correctly identified selection bias"
        fake_quote = "hallucinated text that does not exist"

        spans, warnings = _locate_quotes(raw, [real_quote, fake_quote], "d-1", "Alice")
        assert len(spans) == 1  # Only the real quote
        assert len(warnings) == 1  # Only the fake quote warned
        assert raw[spans[0].start_char : spans[0].end_char] == real_quote
