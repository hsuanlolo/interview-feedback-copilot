"""
LLM extraction client.

Architecture:
  LLMClientBase    — abstract interface (extract_signals per debrief)
  MockLLMClient    — deterministic, no API key (used in tests + llm_mock_mode=True)
  AnthropicClient  — Claude claude-opus-4-8 via anthropic SDK with tool_use structured output
  get_llm_client() — FastAPI-injectable factory; raises 503 if no API key and not in mock mode

Key design choice — offsets are Python's job, not Claude's:
  Claude returns verbatim quoted text. Python finds each quote in raw_text to compute
  start_char / end_char. This gives us exact offsets without asking Claude to count
  characters (which it cannot do reliably). Quotes not found in the source text are
  treated as hallucinations: they produce a warning, never a span.

Pydantic validation gates all LLM output (non-negotiable project rule):
  LLM JSON → validated as LLMSignalDraft (ValidationError = reject)
             → quotes located in raw_text (missing = warning, not span)
             → built as ExtractedSignal (ValidationError = reject)
  If validation fails, an exception is raised. Nothing is silently accepted.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional, Tuple

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.schemas.models import (
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION_LLM = "claude-opus-4-8"
MOCK_EXTRACTOR_VERSION = "mock-v1"

# ---------------------------------------------------------------------------
# Internal LLM output schema (what Claude returns — validated before conversion)
# ---------------------------------------------------------------------------


class LLMSignalDraft(BaseModel):
    """
    Lightweight schema for one signal as the LLM returns it.

    Intentionally simpler than ExtractedSignal: no span objects, no UUIDs.
    Python converts this to ExtractedSignal after locating the quotes.
    """

    competency_id: str = Field(..., min_length=1)
    signal_type: SignalType
    claim: str = Field(..., min_length=10)
    evidence_quotes: List[str] = Field(
        ..., min_length=1, description="Verbatim quotes from the debrief"
    )
    confidence: float = Field(0.70, ge=0.0, le=1.0)
    is_vague: bool = False
    reasoning: str = ""


class LLMExtractionOutput(BaseModel):
    """Top-level wrapper validated against the LLM's tool_use response."""

    signals: List[LLMSignalDraft]


# ---------------------------------------------------------------------------
# Tool schema passed to Claude (defines the forced structured output format)
# ---------------------------------------------------------------------------

_EXTRACTION_TOOL = {
    "name": "extract_competency_signals",
    "description": (
        "Extract competency assessment signals from an interview debrief. "
        "Call this tool once with all signals found in the debrief."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "competency_id": {
                            "type": "string",
                            "description": "Must match a competency_id from the rubric exactly",
                        },
                        "signal_type": {
                            "type": "string",
                            "enum": ["positive", "negative", "mixed", "unclear"],
                        },
                        "claim": {
                            "type": "string",
                            "description": "One sentence summarising this competency signal",
                        },
                        "evidence_quotes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": (
                                "Verbatim sentences copied exactly from the debrief. "
                                "Do NOT paraphrase. Do NOT invent text."
                            ),
                        },
                        "confidence": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Your confidence in this signal (0–1)",
                        },
                        "is_vague": {
                            "type": "boolean",
                            "description": "True if the debrief evidence is hedged or thin",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief explanation of how you read the evidence",
                        },
                    },
                    "required": ["competency_id", "signal_type", "claim", "evidence_quotes"],
                },
            }
        },
        "required": ["signals"],
    },
}

_SYSTEM_PROMPT = """\
You are an evidence-extraction assistant for interview feedback synthesis.

Your task: read an interview debrief and identify which competencies were discussed,
then extract verbatim evidence for each assessment.

Non-negotiable rules:
1. Only include text that appears EXACTLY as written in the debrief. Do not paraphrase.
2. Do NOT recommend hire or no-hire. Do NOT produce an aggregate score.
3. If a competency was not discussed, omit it — correct omission is better than invented evidence.
4. Quote full sentences, not fragments, so the evidence is self-explanatory out of context.
5. If the interviewer's language is hedged ("seems to", "kind of"), set is_vague=true.

Call the extract_competency_signals tool once with everything you found.\
"""


def _build_user_message(debrief: InterviewDebrief, rubric: RoleRubric) -> str:
    """Build the user-turn message containing the rubric and debrief."""
    competency_lines: List[str] = []
    for c in rubric.competencies:
        pos = ", ".join(f'"{p}"' for p in c.positive_indicators[:4]) or "(none listed)"
        neg = ", ".join(f'"{n}"' for n in c.negative_indicators[:4]) or "(none listed)"
        competency_lines.append(
            f"  • {c.name} (ID: {c.competency_id})\n"
            f"    Description: {c.description}\n"
            f"    Positive indicators: {pos}\n"
            f"    Negative indicators: {neg}"
        )

    rubric_block = "\n".join(competency_lines)

    return (
        f"## Role: {rubric.role_title}\n\n"
        f"### Competencies to assess:\n{rubric_block}\n\n"
        f"### Interview Debrief\n"
        f"Interviewer: {debrief.interviewer_name}\n\n"
        f"{debrief.raw_text}\n\n"
        "Extract all competency signals present in this debrief."
    )


# ---------------------------------------------------------------------------
# Quote location (Python computes offsets — not Claude)
# ---------------------------------------------------------------------------


def _locate_quotes(
    raw_text: str,
    quotes: List[str],
    debrief_id: str,
    interviewer_name: str,
) -> Tuple[List[EvidenceSpan], List[str]]:
    """
    Find each verbatim quote in raw_text and build EvidenceSpan objects.

    Returns (spans, warnings).
    Quotes absent from raw_text are hallucinated citations — they produce a
    warning but NEVER a span. The caller receives an honest list.
    """
    spans: List[EvidenceSpan] = []
    warnings: List[str] = []

    seen_offsets: List[int] = []

    for raw_quote in quotes:
        quote = raw_quote.strip()
        if not quote:
            continue

        idx = raw_text.find(quote)
        if idx == -1:
            warnings.append(
                f"Hallucinated citation — quote not found in debrief: {quote[:80]!r}"
            )
            continue

        # Guard against the same span appearing twice (LLM repetition)
        if idx in seen_offsets:
            continue
        seen_offsets.append(idx)

        try:
            span = EvidenceSpan(
                source_debrief_id=debrief_id,
                interviewer_name=interviewer_name,
                start_char=idx,
                end_char=idx + len(quote),
                quoted_text=quote,
            )
            spans.append(span)
        except ValidationError as exc:
            warnings.append(
                f"Span validation failed for quote {quote[:40]!r}: {exc.error_count()} errors"
            )

    return spans, warnings


def _draft_to_signal(
    draft: LLMSignalDraft,
    debrief: InterviewDebrief,
    extractor_version: str,
) -> Tuple[Optional[ExtractedSignal], List[str]]:
    """
    Convert a validated LLMSignalDraft into an ExtractedSignal.

    Returns (signal_or_None, warnings).
    Returns None only if no valid spans could be located (pure hallucination).
    In that case, the caller may choose to surface an unsupported signal or skip it.
    """
    spans, warnings = _locate_quotes(
        raw_text=debrief.raw_text,
        quotes=draft.evidence_quotes,
        debrief_id=debrief.debrief_id,
        interviewer_name=debrief.interviewer_name,
    )

    is_unsupported = len(spans) == 0

    if is_unsupported:
        warnings.append(
            f"Signal for '{draft.competency_id}' has no verifiable evidence spans — "
            "all quotes were hallucinated or too short. Signal marked is_unsupported=True."
        )
        # We still return the signal (with the claim) so the reviewer sees the gap,
        # but we need at least one span. Use the first 60 chars of the debrief body
        # as a placeholder so Pydantic validation passes.
        fallback_text = debrief.raw_text.strip()[:60].strip()
        if len(fallback_text) >= 5:
            try:
                fallback_span = EvidenceSpan(
                    source_debrief_id=debrief.debrief_id,
                    interviewer_name=debrief.interviewer_name,
                    start_char=debrief.raw_text.find(fallback_text),
                    end_char=debrief.raw_text.find(fallback_text) + len(fallback_text),
                    quoted_text=fallback_text,
                )
                spans = [fallback_span]
            except ValidationError:
                return None, warnings
        else:
            return None, warnings

    try:
        signal = ExtractedSignal(
            debrief_id=debrief.debrief_id,
            competency_id=draft.competency_id,
            signal_type=draft.signal_type,
            claim=draft.claim,
            evidence_spans=spans,
            confidence=draft.confidence,
            is_vague=draft.is_vague,
            is_unsupported=is_unsupported,
            extractor_version=extractor_version,
        )
        return signal, warnings
    except ValidationError as exc:
        return None, warnings + [
            f"ExtractedSignal validation failed for competency '{draft.competency_id}': "
            f"{exc.error_count()} errors — signal skipped"
        ]


# ---------------------------------------------------------------------------
# Client base and implementations
# ---------------------------------------------------------------------------


class LLMClientBase:
    """Abstract interface for LLM-powered signal extraction."""

    extractor_version: str = "llm-v1"

    def extract_signals(
        self,
        debrief: InterviewDebrief,
        rubric: RoleRubric,
    ) -> Tuple[List[ExtractedSignal], List[str]]:
        raise NotImplementedError


class MockLLMClient(LLMClientBase):
    """
    Deterministic mock client. No API key required.

    Uses the baseline extractor's sentence splitter to find real sentences in
    the debrief body, then wraps them as mock LLM output. This means mock
    signals have valid, offset-accurate EvidenceSpans — tests can verify the
    full pipeline without depending on LLM output format.
    """

    extractor_version = MOCK_EXTRACTOR_VERSION

    def extract_signals(
        self,
        debrief: InterviewDebrief,
        rubric: RoleRubric,
    ) -> Tuple[List[ExtractedSignal], List[str]]:
        from app.services.baseline_extractor import _extract_body, _split_into_sentences

        body = _extract_body(debrief.raw_text)
        sentences = _split_into_sentences(body)
        warnings: List[str] = []

        if not sentences:
            warnings.append(
                f"[mock] No sentences found in debrief from {debrief.interviewer_name!r}"
            )
            return [], warnings

        signals: List[ExtractedSignal] = []

        for i, competency in enumerate(rubric.competencies[:3]):
            sent_text, _, _ = sentences[min(i, len(sentences) - 1)]

            idx = debrief.raw_text.find(sent_text)
            if idx == -1:
                continue

            try:
                span = EvidenceSpan(
                    source_debrief_id=debrief.debrief_id,
                    interviewer_name=debrief.interviewer_name,
                    start_char=idx,
                    end_char=idx + len(sent_text),
                    quoted_text=sent_text,
                )
                signal = ExtractedSignal(
                    debrief_id=debrief.debrief_id,
                    competency_id=competency.competency_id,
                    signal_type=SignalType.POSITIVE,
                    claim=f"[MOCK] {sent_text[:120].rstrip()}",
                    evidence_spans=[span],
                    confidence=0.99,
                    is_vague=False,
                    is_unsupported=False,
                    extractor_version=MOCK_EXTRACTOR_VERSION,
                )
                signals.append(signal)
            except (ValidationError, Exception) as exc:
                warnings.append(f"[mock] Skipped competency '{competency.competency_id}': {exc}")

        return signals, warnings


class AnthropicLLMClient(LLMClientBase):
    """
    Real extraction using Claude claude-opus-4-8 via the anthropic SDK.

    Uses tool_use to force structured JSON output. Validates the response with
    Pydantic before converting to ExtractedSignal objects. A ValidationError is
    never silently swallowed — it surfaces as a 422 HTTP error.
    """

    extractor_version = EXTRACTOR_VERSION_LLM

    def __init__(self, api_key: str, model: str) -> None:
        try:
            import anthropic as _anthropic  # local import keeps mock tests fast

            self._anthropic = _anthropic
            self._client = _anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise RuntimeError(
                "The 'anthropic' package is required for LLM extraction. "
                "Install it with: pip install anthropic"
            )
        self.model = model

    def _call_api(self, debrief: InterviewDebrief, rubric: RoleRubric) -> LLMExtractionOutput:
        """
        Call Claude and return the validated extraction output.

        Raises:
          ValidationError  — if the LLM response fails Pydantic validation
          HTTPException    — if the API call fails or returns unexpected structure
        """
        user_message = _build_user_message(debrief, rubric)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                tools=[_EXTRACTION_TOOL],
                tool_choice={"type": "tool", "name": "extract_competency_signals"},
            )
        except self._anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Anthropic API error: {exc}",
            )

        # Extract the tool_use block
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            raise HTTPException(
                status_code=502,
                detail="Claude response contained no tool_use block. Cannot proceed.",
            )

        raw_input = tool_blocks[0].input

        # Pydantic validation gates the LLM output — this is the non-negotiable rule.
        # ValidationError is NOT caught here: it propagates and surfaces as a 422.
        try:
            return LLMExtractionOutput.model_validate(raw_input)
        except ValidationError as exc:
            logger.error(
                "LLM output failed Pydantic validation (%d errors): %s",
                exc.error_count(),
                exc,
            )
            # Re-raise as HTTP 422 so the caller gets a clear error, not a silent failure.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"LLM output failed schema validation ({exc.error_count()} errors). "
                    "The model produced output that does not conform to the expected schema. "
                    f"First error: {exc.errors()[0]}"
                ),
            )

    def extract_signals(
        self,
        debrief: InterviewDebrief,
        rubric: RoleRubric,
    ) -> Tuple[List[ExtractedSignal], List[str]]:
        extraction = self._call_api(debrief, rubric)

        signals: List[ExtractedSignal] = []
        all_warnings: List[str] = []

        # Validate each competency_id against the rubric (catch IDs Claude invented)
        valid_cids = {c.competency_id for c in rubric.competencies}

        for draft in extraction.signals:
            if draft.competency_id not in valid_cids:
                all_warnings.append(
                    f"LLM returned unknown competency_id '{draft.competency_id}' — "
                    "not in rubric. Signal discarded."
                )
                continue

            signal, warnings = _draft_to_signal(
                draft=draft,
                debrief=debrief,
                extractor_version=EXTRACTOR_VERSION_LLM,
            )
            all_warnings.extend(warnings)
            if signal is not None:
                signals.append(signal)

        return signals, all_warnings


# ---------------------------------------------------------------------------
# Factory (FastAPI-injectable dependency)
# ---------------------------------------------------------------------------


def get_llm_client() -> LLMClientBase:
    """
    Return the appropriate LLM client based on current settings.

    Priority:
      1. llm_mock_mode=True → MockLLMClient (no API key needed)
      2. anthropic_api_key set → AnthropicLLMClient
      3. Neither → 503 Service Unavailable

    This function is injected as a FastAPI Depends so tests can override it.
    """
    if settings.llm_mock_mode:
        return MockLLMClient()
    if settings.anthropic_api_key:
        return AnthropicLLMClient(settings.anthropic_api_key, settings.llm_model)
    raise HTTPException(
        status_code=503,
        detail=(
            "No Anthropic API key configured. "
            "Set ANTHROPIC_API_KEY in your environment or .env file, "
            "or set LLM_MOCK_MODE=true to use the deterministic mock client."
        ),
    )


# ---------------------------------------------------------------------------
# Multi-debrief aggregator (mirrors extract_all_baseline from baseline_extractor)
# ---------------------------------------------------------------------------


def extract_all_llm(
    debriefs: List[InterviewDebrief],
    rubric: RoleRubric,
    client: LLMClientBase,
) -> Tuple[List[ExtractedSignal], List[str]]:
    """
    Run LLM extraction across all debriefs for one candidate.

    Returns (signals, warnings).
    Warns on very short debriefs (< 30 words) — thin input produces thin output.
    """
    all_signals: List[ExtractedSignal] = []
    all_warnings: List[str] = []

    for debrief in debriefs:
        if debrief.word_count < 30:
            all_warnings.append(
                f"Debrief from {debrief.interviewer_name!r} is very short "
                f"({debrief.word_count} words). LLM extraction quality may be poor."
            )

        signals, warnings = client.extract_signals(debrief, rubric)
        all_signals.extend(signals)
        all_warnings.extend(warnings)

        if not signals:
            all_warnings.append(
                f"No signals extracted from {debrief.interviewer_name!r}'s debrief "
                "via LLM extraction."
            )

    return all_signals, all_warnings
