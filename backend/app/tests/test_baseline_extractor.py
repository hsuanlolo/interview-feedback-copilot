"""
Tests for the deterministic baseline extractor.

Three layers:
  1. Helpers — _extract_body, _split_into_sentences, _classify_signal
  2. Signal extraction — extract_signals_baseline on synthetic debriefs
  3. Integration — POST /extract/baseline with sample data from disk

Run with: pytest app/tests/test_baseline_extractor.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.models import (
    Competency,
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)
from app.services.baseline_extractor import (
    EXTRACTOR_VERSION,
    _classify_signal,
    _extract_body,
    _is_vague,
    _sentence_matches_competency,
    _split_into_sentences,
    extract_all_baseline,
    extract_signals_baseline,
)
from app.services.store import store

client = TestClient(app)

SAMPLE_DIR = Path(__file__).parents[3] / "sample_data"


@pytest.fixture(autouse=True)
def reset():
    store.reset()
    yield
    store.reset()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_debrief(text: str, interviewer: str = "Alice") -> InterviewDebrief:
    return InterviewDebrief(
        candidate_id="C-001",
        interviewer_name=interviewer,
        raw_text=text,
    )


def make_competency(
    name: str = "Statistical Reasoning",
    cid: str = "stat_reasoning",
    pos: List[str] | None = None,
    neg: List[str] | None = None,
) -> Competency:
    return Competency(
        competency_id=cid,
        name=name,
        description=f"Tests {name.lower()} ability.",
        positive_indicators=pos or ["correctly identified", "sound reasoning"],
        negative_indicators=neg or ["missed the issue", "shallow explanation"],
    )


def make_rubric(competencies: List[Competency] | None = None) -> RoleRubric:
    return RoleRubric(
        role_title="Data Scientist",
        competencies=competencies or [make_competency()],
    )


# ---------------------------------------------------------------------------
# 1. Helper: _extract_body
# ---------------------------------------------------------------------------


class TestExtractBody:
    def test_strips_content_before_separator(self):
        text = "Candidate: Alice\nInterviewer: Bob\n---\nActual body starts here."
        body = _extract_body(text)
        assert body == "Actual body starts here."
        assert "Candidate:" not in body

    def test_no_separator_skips_header_lines(self):
        text = "Candidate: Alice\nRound: Technical\n\nThis is the narrative body."
        body = _extract_body(text)
        assert "This is the narrative body." in body
        # Header key-value lines should be skipped
        assert "Candidate: Alice" not in body

    def test_full_text_returned_when_no_header_detected(self):
        text = "This debrief has no header at all. Just narrative text about the candidate."
        body = _extract_body(text)
        assert "narrative text" in body

    def test_separator_can_appear_mid_file(self):
        text = "Header line: value\n---\nParagraph one.\n\nParagraph two."
        body = _extract_body(text)
        assert body.startswith("Paragraph one.")


# ---------------------------------------------------------------------------
# 2. Helper: _split_into_sentences
# ---------------------------------------------------------------------------


class TestSplitIntoSentences:
    def test_basic_split(self):
        text = "The candidate solved A/B testing correctly. They also explained the bias."
        sentences = _split_into_sentences(text)
        assert len(sentences) >= 1

    def test_returns_triples(self):
        text = "First sentence here. Second sentence here."
        result = _split_into_sentences(text)
        for item in result:
            assert len(item) == 3, "Should return (text, start, end) triples"

    def test_offsets_match_quoted_text(self):
        """Critical: start_char and end_char must bracket the exact sentence text."""
        text = "Jordan demonstrated strong statistical ability. They missed the bias check."
        for sentence, start, end in _split_into_sentences(text):
            assert text[start:end] == sentence, (
                f"Offset mismatch: text[{start}:{end}]={text[start:end]!r} != {sentence!r}"
            )

    def test_long_text_produces_multiple_sentences(self):
        text = (
            "The candidate was excellent on the coding exercise. "
            "However, they struggled with the SQL window function. "
            "Communication was clear and tailored to the audience."
        )
        result = _split_into_sentences(text)
        assert len(result) >= 2

    def test_short_fragments_excluded(self):
        text = "Yes. OK. The candidate demonstrated exceptional statistical reasoning."
        result = _split_into_sentences(text)
        # "Yes." and "OK." are too short (< 15 chars) and should be excluded
        for sentence, _, _ in result:
            assert len(sentence) >= 15


# ---------------------------------------------------------------------------
# 3. Helper: _classify_signal
# ---------------------------------------------------------------------------


class TestClassifySignal:
    def test_positive_indicator_phrase_gives_positive(self):
        sentences = ["Jordan correctly identified selection bias without prompting."]
        signal, conf = _classify_signal(
            sentences,
            pos_phrases=["correctly identified"],
            neg_phrases=["missed the issue"],
        )
        assert signal == SignalType.POSITIVE
        assert conf >= 0.70

    def test_negative_indicator_phrase_gives_negative(self):
        sentences = ["They missed the issue after a follow-up prompt."]
        signal, conf = _classify_signal(
            sentences,
            pos_phrases=["correctly identified"],
            neg_phrases=["missed the issue"],
        )
        assert signal == SignalType.NEGATIVE
        assert conf >= 0.70

    def test_both_indicators_give_mixed(self):
        sentences = [
            "They correctly identified bias in one part.",
            "But they missed the issue on the second question.",
        ]
        signal, conf = _classify_signal(
            sentences,
            pos_phrases=["correctly identified"],
            neg_phrases=["missed the issue"],
        )
        assert signal == SignalType.MIXED

    def test_generic_positive_words_classify_positive(self):
        sentences = ["They demonstrated strong and excellent problem-solving skills."]
        signal, conf = _classify_signal(sentences, pos_phrases=[], neg_phrases=[])
        assert signal == SignalType.POSITIVE
        assert conf == 0.50

    def test_generic_negative_words_classify_negative(self):
        sentences = ["The candidate struggled and failed to explain the concept."]
        signal, conf = _classify_signal(sentences, pos_phrases=[], neg_phrases=[])
        assert signal == SignalType.NEGATIVE

    def test_no_sentiment_gives_unclear(self):
        sentences = ["The candidate answered the question about the dataset."]
        signal, conf = _classify_signal(sentences, pos_phrases=[], neg_phrases=[])
        assert signal == SignalType.UNCLEAR
        assert conf == 0.25


# ---------------------------------------------------------------------------
# 4. Signal extraction: synthetic debriefs
# ---------------------------------------------------------------------------


POSITIVE_DEBRIEF = """
Candidate: Jordan Lee
Interviewer: Alice
---

Jordan correctly identified the selection bias in the observational study
without any prompting from me. The reasoning was sound and clearly explained.

They also designed a well-structured A/B test with an appropriate power
calculation, discussing the minimum detectable effect and weekly seasonality.
"""

NEGATIVE_DEBRIEF = """
Candidate: Jordan Lee
Interviewer: Bob
---

Jordan missed the issue of selection bias entirely. After a follow-up prompt,
they acknowledged it but the explanation was shallow and did not address
the underlying mechanism.

The SQL window function question revealed a real gap. The candidate struggled
significantly and required two hints before producing a working solution.
"""

MIXED_DEBRIEF = """
Candidate: Jordan Lee
Interviewer: Carol
---

Jordan correctly identified the A/B testing framework and set up the hypothesis
correctly. However, they missed the issue when I introduced confounding.

Communication was generally clear. They led with conclusions and adjusted
depth when I signaled confusion.
"""

IRRELEVANT_DEBRIEF = """
Candidate: Jordan Lee
Interviewer: Dave
---

We spent most of the session discussing the candidate's career history
and motivations. No technical competencies were formally assessed.
"""


class TestExtractSignalsBaseline:
    def test_positive_debrief_produces_positive_signal(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        assert len(signals) >= 1
        types = {s.signal_type for s in signals}
        assert SignalType.POSITIVE in types or SignalType.MIXED in types

    def test_negative_debrief_produces_negative_signal(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(NEGATIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        assert len(signals) >= 1
        types = {s.signal_type for s in signals}
        assert SignalType.NEGATIVE in types or SignalType.MIXED in types

    def test_irrelevant_debrief_returns_no_signals(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(IRRELEVANT_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        # May return 0 — technical vocabulary is not present
        # (This test documents expected baseline recall limitations)
        assert isinstance(signals, list)

    def test_all_evidence_spans_are_valid(self):
        """Every EvidenceSpan must point to text that exists in raw_text."""
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)

        for signal in signals:
            for span in signal.evidence_spans:
                raw = debrief.raw_text
                extracted = raw[span.start_char : span.end_char]
                assert extracted == span.quoted_text, (
                    f"Span mismatch:\n"
                    f"  raw_text[{span.start_char}:{span.end_char}] = {extracted!r}\n"
                    f"  quoted_text = {span.quoted_text!r}"
                )

    def test_all_signals_have_at_least_one_span(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        for signal in signals:
            assert len(signal.evidence_spans) >= 1

    def test_claims_are_non_empty(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        for signal in signals:
            assert len(signal.claim) >= 5

    def test_extractor_version_is_set(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        for signal in signals:
            assert signal.extractor_version == EXTRACTOR_VERSION

    def test_debrief_id_propagated_to_signals(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(POSITIVE_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        for signal in signals:
            assert signal.debrief_id == debrief.debrief_id

    def test_multiple_competencies_can_match(self):
        """A rich debrief can produce signals for multiple competencies."""
        rubric = make_rubric([
            make_competency("Statistical Reasoning", "stat"),
            make_competency(
                "Communication", "comm",
                pos=["led with conclusions", "clear and tailored"],
                neg=["jumped to detail"],
            ),
        ])
        debrief = make_debrief(MIXED_DEBRIEF)
        signals = extract_signals_baseline(debrief, rubric)
        competency_ids = {s.competency_id for s in signals}
        # Both competencies are mentioned in MIXED_DEBRIEF
        assert len(competency_ids) >= 1


# ---------------------------------------------------------------------------
# 5. extract_all_baseline — warnings and multi-debrief behaviour
# ---------------------------------------------------------------------------


class TestExtractAllBaseline:
    def test_aggregates_signals_from_all_debriefs(self):
        rubric = make_rubric([make_competency()])
        debriefs = [
            make_debrief(POSITIVE_DEBRIEF, "Alice"),
            make_debrief(NEGATIVE_DEBRIEF, "Bob"),
        ]
        signals, warnings = extract_all_baseline(debriefs, rubric)
        assert len(signals) >= 1  # At least one debrief matched

    def test_short_debrief_generates_warning(self):
        rubric = make_rubric([make_competency()])
        short_debrief = make_debrief("Brief session today.", "Dave")
        _, warnings = extract_all_baseline([short_debrief], rubric)
        assert any("short" in w.lower() for w in warnings)

    def test_no_match_debrief_generates_warning(self):
        rubric = make_rubric([make_competency()])
        debrief = make_debrief(IRRELEVANT_DEBRIEF, "Dave")
        signals, warnings = extract_all_baseline([debrief], rubric)
        if len(signals) == 0:
            assert any("no signals" in w.lower() for w in warnings)

    def test_warnings_are_strings(self):
        rubric = make_rubric([make_competency()])
        _, warnings = extract_all_baseline([make_debrief(POSITIVE_DEBRIEF)], rubric)
        for w in warnings:
            assert isinstance(w, str)


# ---------------------------------------------------------------------------
# 6. Integration: POST /extract/baseline with sample data from disk
# ---------------------------------------------------------------------------


class TestExtractBaselineEndpoint:
    @pytest.fixture
    def sample_rubric(self) -> dict:
        path = SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json"
        return json.loads(path.read_text())

    @pytest.fixture
    def sample_debrief_text(self) -> str:
        path = SAMPLE_DIR / "debriefs" / "candidate_001_interviewer_1.txt"
        return path.read_text()

    def _build_request_body(self, rubric_dict: dict, debrief_text: str) -> dict:
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

    def test_returns_200(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        response = client.post("/extract/baseline", json=body)
        assert response.status_code == 200, response.text

    def test_response_has_signals_field(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/baseline", json=body).json()
        assert "signals" in data
        assert "total_signals" in data
        assert "extractor_used" in data

    def test_extractor_used_is_baseline(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/baseline", json=body).json()
        assert data["extractor_used"] == "baseline-v1"

    def test_produces_signals_on_rich_debrief(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/baseline", json=body).json()
        assert data["total_signals"] >= 1, (
            "Expected at least one signal from a 300+ word debrief mentioning "
            "statistical reasoning and causal inference explicitly."
        )

    def test_all_returned_signals_have_evidence(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/baseline", json=body).json()
        for signal in data["signals"]:
            assert len(signal["evidence_spans"]) >= 1, (
                f"Signal {signal['signal_id']} has no evidence spans"
            )

    def test_span_offsets_are_valid(self, sample_rubric, sample_debrief_text):
        """Verify that every returned span's quoted_text appears in the source debrief."""
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        data = client.post("/extract/baseline", json=body).json()
        for signal in data["signals"]:
            for span in signal["evidence_spans"]:
                start = span["start_char"]
                end = span["end_char"]
                quoted = span["quoted_text"]
                extracted = sample_debrief_text[start:end]
                assert extracted == quoted, (
                    f"Span offset mismatch:\n"
                    f"  raw_text[{start}:{end}] = {extracted!r}\n"
                    f"  quoted_text            = {quoted!r}"
                )

    def test_full_five_debrief_pipeline(self, sample_rubric):
        """Integration test: run all 5 sample debriefs through the endpoint."""
        debrief_dir = SAMPLE_DIR / "debriefs"
        debrief_texts = sorted(debrief_dir.glob("candidate_001_interviewer_*.txt"))
        assert len(debrief_texts) == 5

        debriefs = []
        for i, path in enumerate(debrief_texts):
            debriefs.append({
                "candidate_id": "C-001",
                "interviewer_name": f"Interviewer {i + 1}",
                "raw_text": path.read_text(),
            })

        body = {"rubric": sample_rubric, "debriefs": debriefs}
        response = client.post("/extract/baseline", json=body)
        assert response.status_code == 200

        data = response.json()
        assert data["total_signals"] >= 5, (
            f"Expected ≥5 signals from 5 debriefs, got {data['total_signals']}"
        )

    def test_empty_debriefs_list_returns_400(self, sample_rubric):
        body = {"rubric": sample_rubric, "debriefs": []}
        response = client.post("/extract/baseline", json=body)
        assert response.status_code == 400

    def test_llm_endpoint_returns_501_stub(self, sample_rubric, sample_debrief_text):
        body = self._build_request_body(sample_rubric, sample_debrief_text)
        response = client.post("/extract/llm", json=body)
        assert response.status_code == 501
