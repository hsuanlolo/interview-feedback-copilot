"""
Evidence verifier service.

Validates every EvidenceSpan in a set of ExtractedSignals against the
verbatim text in the source debrief at the stated character offsets.

Non-negotiable rule: invalid citations must never reach synthesis.
This service is the enforcement gate — citation_validity_rate < 1.0
means synthesis should not proceed (enforced in PROMPT 10).

Verification outcome per span
------------------------------
  valid             raw_text[start_char:end_char] == quoted_text exactly
  offset_mismatch   quoted_text exists in the debrief, but not at [start:end]
  text_not_found    quoted_text does not appear anywhere in the debrief
  source_missing    span references a debrief_id not present in the input list

Signal-level rollup
-------------------
  unsupported_claim — ALL spans for that signal failed (no grounded evidence)
  vague_claim       — signal.is_vague is True (separate from span validity)

is_valid is True only when citation_validity_rate == 1.0 (zero errors).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from app.schemas.models import (
    ExtractedSignal,
    InterviewDebrief,
    VerificationError,
    VerificationResult,
)

VERIFIER_VERSION = "verifier-v1"


def _check_span(
    raw_text: str,
    span_id: str,
    start_char: int,
    end_char: int,
    quoted_text: str,
) -> Tuple[bool, List[VerificationError]]:
    """
    Check one span against its source text.

    Returns (is_valid, errors).
    is_valid is True only on an exact offset match.
    """
    # Exact match: the gold standard
    extracted = raw_text[start_char:end_char]
    if extracted == quoted_text:
        return True, []

    # Text exists, but at a different position — extractor offset bug
    if quoted_text in raw_text:
        correct_idx = raw_text.find(quoted_text)
        return False, [
            VerificationError(
                span_id=span_id,
                error_type="offset_mismatch",
                description=(
                    f"Text found in debrief at index {correct_idx}, "
                    f"but span states [{start_char}:{end_char}]. "
                    f"raw_text[{start_char}:{end_char}]={extracted[:40]!r}"
                ),
            )
        ]

    # Text not found anywhere — hallucinated citation
    return False, [
        VerificationError(
            span_id=span_id,
            error_type="text_not_found",
            description=(
                f"quoted_text {quoted_text[:60]!r} does not appear "
                "anywhere in the source debrief."
            ),
        )
    ]


class EvidenceVerifier:
    """
    Validates ExtractedSignal evidence spans against source debrief text.

    Usage:
        verifier = EvidenceVerifier()
        result = verifier.verify(signals, debriefs)
        if not result.is_valid:
            # Do not proceed to synthesis
    """

    def verify(
        self,
        signals: List[ExtractedSignal],
        debriefs: List[InterviewDebrief],
    ) -> VerificationResult:
        """
        Verify all spans in signals against their source debriefs.

        Parameters
        ----------
        signals:  Extracted signals to verify (may come from baseline or LLM extractor).
        debriefs: The original debrief objects used during extraction.
                  Must include every debrief referenced by span.source_debrief_id.
        """
        # Build lookup by debrief_id for O(1) access per span
        debrief_map: Dict[str, str] = {d.debrief_id: d.raw_text for d in debriefs}

        all_errors: List[VerificationError] = []
        unsupported_claims: List[str] = []
        vague_claims: List[str] = []
        total_spans = 0
        valid_span_count = 0

        for signal in signals:
            if signal.is_vague:
                vague_claims.append(signal.signal_id)

            signal_valid_spans = 0

            for span in signal.evidence_spans:
                total_spans += 1

                # Source debrief must be in the provided list
                if span.source_debrief_id not in debrief_map:
                    all_errors.append(
                        VerificationError(
                            span_id=span.span_id,
                            error_type="source_missing",
                            description=(
                                f"Debrief '{span.source_debrief_id}' referenced by span "
                                f"is not in the provided debriefs list."
                            ),
                        )
                    )
                    continue

                raw_text = debrief_map[span.source_debrief_id]
                is_valid, errors = _check_span(
                    raw_text=raw_text,
                    span_id=span.span_id,
                    start_char=span.start_char,
                    end_char=span.end_char,
                    quoted_text=span.quoted_text,
                )

                if is_valid:
                    valid_span_count += 1
                    signal_valid_spans += 1
                else:
                    all_errors.extend(errors)

            # Signal is unsupported if ALL its spans failed verification
            if signal_valid_spans == 0:
                unsupported_claims.append(signal.signal_id)

        # Citation validity rate — 1.0 when no spans were checked (nothing to invalidate)
        rate = valid_span_count / total_spans if total_spans > 0 else 1.0

        warnings: List[str] = []
        if vague_claims:
            warnings.append(
                f"{len(vague_claims)} signal(s) are marked vague — "
                "review for specificity before synthesis."
            )
        if unsupported_claims:
            warnings.append(
                f"{len(unsupported_claims)} unsupported signal(s) have no verifiable "
                "evidence spans. Synthesis must not proceed until these are resolved."
            )

        return VerificationResult(
            is_valid=(len(all_errors) == 0),
            errors=all_errors,
            warnings=warnings,
            unsupported_claims=unsupported_claims,
            vague_claims=vague_claims,
            citation_validity_rate=round(rate, 4),
            total_spans_checked=total_spans,
            valid_spans=valid_span_count,
        )


# Module-level singleton — stateless, safe to share
verifier = EvidenceVerifier()
