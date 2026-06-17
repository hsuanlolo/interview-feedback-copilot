"""
Deterministic baseline extractor.

Uses keyword matching and simple sentiment heuristics to extract competency
signals from debrief text. No LLM, no API key required.

Intentional limitations (by design — to establish a lower bound for eval):
  - Cannot understand negation ("not strong" → may score POSITIVE due to "strong")
  - Misses signals expressed without rubric vocabulary
  - May conflate competencies sharing vocabulary (e.g., "clear" hits both
    Communication and Statistical Reasoning)
  - Paragraph context is ignored — sentence-level only

Why build this before an LLM extractor?
  The baseline gives us measurable recall/precision targets. When the LLM
  extractor is added, we can say: "LLM improves omission rate from X% to Y%".
  Without the baseline, we have no anchor to prove the LLM is earning its cost.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from uuid import uuid4

from app.schemas.models import (
    Competency,
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)

EXTRACTOR_VERSION = "baseline-v1"

# Generic sentiment word lists used when rubric indicator phrases don't match.
# These are intentionally broad — the LLM extractor will be more precise.
_POSITIVE_WORDS: List[str] = [
    "strong", "excellent", "clear", "impressive", "exceptional", "solid",
    "correctly", "well-structured", "well structured", "good", "demonstrated",
    "thorough", "proactively", "accurate", "insightful", "effective",
    "articulate", "confident", "competent", "great", "outstanding",
]
_NEGATIVE_WORDS: List[str] = [
    "weak", "poor", "missed", "failed", "struggled", "unclear", "incorrect",
    "wrong", "shallow", "vague", "confused", "difficulty", "did not",
    "didn't", "unable", "inadequate", "hesitat", "couldn't", "lacked",
    "limited", "surface-level", "high-level response", "required hints",
    "required prompting", "fell short",
]
_VAGUE_PHRASES: List[str] = [
    "kind of", "sort of", "seems to", "somewhat", "maybe", "perhaps",
    "might be", "not sure", "hard to say",
]


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def _extract_body(raw_text: str) -> str:
    """
    Return only the body portion of the debrief text.

    If the file contains a '---' separator (our sample format), everything
    after it is the body. Otherwise, we skip short header-looking lines
    (e.g., 'Candidate: Jordan Lee') and return the narrative.
    """
    if "---" in raw_text:
        _, _, body = raw_text.partition("---")
        return body.strip()

    # No separator: skip lines that look like headers
    # (≤90 chars, contains exactly one ':', not starting a quote)
    lines = raw_text.splitlines()
    body_lines: List[str] = []
    header_done = False

    for line in lines:
        stripped = line.strip()
        if not header_done:
            is_header_line = (
                stripped
                and ":" in stripped
                and len(stripped) <= 90
                and not stripped.startswith('"')
            )
            if is_header_line or (not stripped and not body_lines):
                continue
            header_done = True
        body_lines.append(line)

    return "\n".join(body_lines).strip()


def _split_into_sentences(text: str) -> List[Tuple[str, int, int]]:
    """
    Return [(sentence_text, start_char, end_char), ...] for text.

    Character offsets are positions within the `text` argument.
    We split on:
      - Sentence-ending punctuation (. ! ?) followed by whitespace + uppercase
      - Two or more consecutive newlines (paragraph breaks)

    Offsets are found by searching for the sentence substring in `text`,
    starting after the previous sentence's end. This keeps them accurate
    even after stripping whitespace from each part.
    """
    results: List[Tuple[str, int, int]] = []
    search_from = 0

    # Split pattern: sentence boundary OR paragraph break
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\"\'])|(?:\n\s*){2,}', text)

    for raw_part in parts:
        sentence = raw_part.strip()
        if len(sentence) < 15:
            # Skip header lines, very short fragments
            idx = text.find(raw_part, search_from)
            search_from = (idx + len(raw_part)) if idx != -1 else search_from + len(raw_part) + 2
            continue

        start = text.find(sentence, search_from)
        if start == -1:
            # Couldn't locate the sentence — advance and skip
            search_from += len(raw_part) + 2
            continue

        end = start + len(sentence)
        results.append((sentence, start, end))
        search_from = end

    return results


def _build_keyword_sets(
    competency: Competency,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Return (name_keywords, positive_phrases, negative_phrases).

    name_keywords  – words extracted from the competency name + description.
                     Used for broad "does this sentence discuss this competency?" matching.
    positive_phrases – exact substrings from rubric positive_indicators (lowercase).
    negative_phrases – exact substrings from rubric negative_indicators (lowercase).
    """
    stopwords = {
        "with", "from", "that", "this", "they", "their", "have", "about",
        "when", "able", "make", "well", "also", "than", "more", "less",
    }

    name_words = re.findall(r"\w+", competency.name.lower())
    desc_words = re.findall(r"\w{5,}", competency.description.lower())

    name_kws = list(
        dict.fromkeys(  # preserve order, deduplicate
            w for w in name_words + desc_words[:8]
            if len(w) > 3 and w not in stopwords
        )
    )

    pos_phrases = [p.lower() for p in (competency.positive_indicators or [])]
    neg_phrases = [n.lower() for n in (competency.negative_indicators or [])]

    return name_kws, pos_phrases, neg_phrases


def _sentence_matches_competency(
    sentence: str,
    name_kws: List[str],
    pos_phrases: List[str],
    neg_phrases: List[str],
) -> bool:
    """
    True if the sentence likely discusses this competency.

    Matching criteria (any one is sufficient):
      - A name keyword appears in the sentence
      - Any positive or negative indicator phrase appears in the sentence
    """
    lower = sentence.lower()
    if any(kw in lower for kw in name_kws):
        return True
    if any(phrase in lower for phrase in pos_phrases):
        return True
    if any(phrase in lower for phrase in neg_phrases):
        return True
    return False


def _classify_signal(
    sentences: List[str],
    pos_phrases: List[str],
    neg_phrases: List[str],
) -> Tuple[SignalType, float]:
    """
    Classify signal direction and assign a confidence score.

    Confidence rules:
      0.75 — rubric indicator phrase matched (most reliable)
      0.50 — generic positive/negative words present
      0.35 — name keyword only, no clear sentiment
      0.25 — no sentiment detected (UNCLEAR)

    Note: this method cannot handle negation. "Did not demonstrate strong X"
    would be classified as POSITIVE. The LLM extractor fixes this.
    """
    full_lower = " ".join(sentences).lower()

    pos_indicator_hits = sum(1 for p in pos_phrases if p in full_lower)
    neg_indicator_hits = sum(1 for n in neg_phrases if n in full_lower)
    pos_word_hits = sum(1 for w in _POSITIVE_WORDS if w in full_lower)
    neg_word_hits = sum(1 for w in _NEGATIVE_WORDS if w in full_lower)

    if pos_indicator_hits > 0 and neg_indicator_hits > 0:
        return SignalType.MIXED, 0.65

    if neg_indicator_hits > 0:
        return SignalType.NEGATIVE, 0.75

    if pos_indicator_hits > 0:
        return SignalType.POSITIVE, 0.75

    # Fall back to generic word sentiment
    if neg_word_hits > 0 and pos_word_hits == 0:
        return SignalType.NEGATIVE, 0.50
    if pos_word_hits > 0 and neg_word_hits == 0:
        return SignalType.POSITIVE, 0.50
    if pos_word_hits > 0 and neg_word_hits > 0:
        return SignalType.MIXED, 0.40

    return SignalType.UNCLEAR, 0.25


def _is_vague(sentences: List[str]) -> bool:
    """True if the evidence is too sparse or hedged to be reliable."""
    text = " ".join(sentences).lower()
    if any(phrase in text for phrase in _VAGUE_PHRASES):
        return True
    total_words = sum(len(s.split()) for s in sentences)
    return total_words < 10


def _generate_claim(
    sentences: List[str],
    competency: Competency,
    signal_type: SignalType,
) -> str:
    """
    Generate a one-sentence claim from the matched sentences.

    Uses the first matching sentence. Truncated at 200 characters.
    The claim is the basis for the human-readable synthesis row.
    """
    first = sentences[0].strip()
    if not first[-1:] in ".!?":
        first += "."
    return first if len(first) <= 200 else first[:197] + "..."


# ---------------------------------------------------------------------------
# Main extraction functions
# ---------------------------------------------------------------------------


def extract_signals_baseline(
    debrief: InterviewDebrief,
    rubric: RoleRubric,
) -> List[ExtractedSignal]:
    """
    Extract evidence signals from one debrief using keyword matching.

    Returns one ExtractedSignal per (debrief × competency) pair where at
    least one matching sentence was found. Each signal carries up to 4
    EvidenceSpan objects (the matched sentences).

    The quoted_text in each span is taken verbatim from raw_text, so
    character offsets are exact — the EvidenceVerifier will confirm this.
    """
    body = _extract_body(debrief.raw_text)
    sentences_in_body = _split_into_sentences(body)

    # body_offset: where 'body' starts inside raw_text.
    # We search for the first 60 chars of body to avoid false matches.
    search_anchor = body[:60].strip()
    body_offset = debrief.raw_text.find(search_anchor) if search_anchor else 0
    if body_offset == -1:
        body_offset = 0

    signals: List[ExtractedSignal] = []

    for competency in rubric.competencies:
        name_kws, pos_phrases, neg_phrases = _build_keyword_sets(competency)

        # Find matching sentences and adjust offsets to raw_text coordinates
        matched: List[Tuple[str, int, int]] = []
        for sent_text, s_start, s_end in sentences_in_body:
            if _sentence_matches_competency(sent_text, name_kws, pos_phrases, neg_phrases):
                abs_start = s_start + body_offset
                abs_end = s_end + body_offset
                matched.append((sent_text, abs_start, abs_end))

        if not matched:
            continue

        # Build EvidenceSpan objects (cap at 4 to keep responses concise)
        spans: List[EvidenceSpan] = []
        for sent_text, abs_start, abs_end in matched[:4]:
            try:
                span = EvidenceSpan(
                    source_debrief_id=debrief.debrief_id,
                    interviewer_name=debrief.interviewer_name,
                    start_char=abs_start,
                    end_char=abs_end,
                    quoted_text=sent_text,
                )
                spans.append(span)
            except Exception:
                # Validation failed (e.g., offset mismatch) — skip this span
                continue

        if not spans:
            continue

        matched_texts = [s for s, _, _ in matched]
        signal_type, confidence = _classify_signal(matched_texts, pos_phrases, neg_phrases)
        claim = _generate_claim(matched_texts, competency, signal_type)
        vague = _is_vague(matched_texts)

        signals.append(
            ExtractedSignal(
                debrief_id=debrief.debrief_id,
                competency_id=competency.competency_id,
                signal_type=signal_type,
                claim=claim,
                evidence_spans=spans,
                confidence=confidence,
                is_vague=vague,
                is_unsupported=False,  # the span itself IS the support in baseline mode
                extractor_version=EXTRACTOR_VERSION,
            )
        )

    return signals


def extract_all_baseline(
    debriefs: List[InterviewDebrief],
    rubric: RoleRubric,
) -> Tuple[List[ExtractedSignal], List[str]]:
    """
    Run baseline extraction across all debriefs for one candidate.

    Returns (signals, warnings).
    Warnings surface quality issues the reviewer should know about:
      - Very short debriefs (< 30 words)
      - Debriefs from which no signals were extracted
    """
    all_signals: List[ExtractedSignal] = []
    warnings: List[str] = []

    for debrief in debriefs:
        if debrief.word_count < 30:
            warnings.append(
                f"Debrief from {debrief.interviewer_name!r} is very short "
                f"({debrief.word_count} words). Extraction quality may be low."
            )

        signals = extract_signals_baseline(debrief, rubric)
        all_signals.extend(signals)

        if not signals:
            warnings.append(
                f"No signals extracted from {debrief.interviewer_name!r}'s debrief. "
                "The rubric vocabulary may not match this debrief's language."
            )

    return all_signals, warnings
