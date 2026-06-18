"""
Disagreement detector (PROMPT 9).

Detects conflicts between interviewers in the extracted signals and produces
DisagreementFlag objects for the hiring committee's attention.

Implemented detection types
----------------------------
  DIRECTION_CONFLICT  — one interviewer rated positive, another rated negative
                        for the same competency. Severity: HIGH.
  EVIDENCE_ABSENT     — a signal makes a strong claim (confidence ≥ 0.7) but
                        is_unsupported=True (all evidence spans were unverifiable).
                        Severity: HIGH.

Not yet implemented (no numeric scores in v1)
----------------------------------------------
  SCORE_GAP           — would require parsing score_raw into a numeric scale.
  SCALE_MISMATCH      — would require correlating score_raw with signal_type.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from app.schemas.models import (
    Competency,
    DisagreementFlag,
    DisagreementSeverity,
    DisagreementType,
    EvidenceSpan,
    ExtractedSignal,
    InterviewDebrief,
    RoleRubric,
    SignalType,
)


def _interviewer_name_from_signal(
    signal: ExtractedSignal,
    debrief_map: Dict[str, str],
) -> str:
    if signal.debrief_id in debrief_map:
        return debrief_map[signal.debrief_id]
    if signal.evidence_spans:
        return signal.evidence_spans[0].interviewer_name
    return f"Interviewer-{signal.debrief_id[:6]}"


def _collect_spans(signals: List[ExtractedSignal], max_per_signal: int = 1) -> List[EvidenceSpan]:
    spans: List[EvidenceSpan] = []
    for sig in signals:
        spans.extend(sig.evidence_spans[:max_per_signal])
    return spans[:6]  # Cap total to keep flags readable


def _net_direction(sigs: List[ExtractedSignal]) -> Optional[SignalType]:
    """Return the net direction for a set of signals from one interviewer.

    An interviewer who says both positive and negative things about a competency
    is nuanced, not a conflict party — return None so they are excluded from the
    direction-conflict calculation.
    """
    pos = sum(1 for s in sigs if s.signal_type in {SignalType.POSITIVE, SignalType.MIXED})
    neg = sum(1 for s in sigs if s.signal_type in {SignalType.NEGATIVE, SignalType.MIXED})
    if pos > neg:
        return SignalType.POSITIVE
    if neg > pos:
        return SignalType.NEGATIVE
    return None  # tied → mixed view, not a conflict contributor


def _detect_direction_conflict(
    competency: Competency,
    debrief_groups: Dict[str, List[ExtractedSignal]],
    debrief_map: Dict[str, str],
    min_minority_voters: int = 1,
    min_minority_ratio: float = 0.30,
) -> Optional[DisagreementFlag]:
    positive_names: List[str] = []
    negative_names: List[str] = []
    all_signals: List[ExtractedSignal] = []

    for debrief_id, sigs in debrief_groups.items():
        name = _interviewer_name_from_signal(sigs[0], debrief_map)
        net = _net_direction(sigs)
        # Interviewers with tied/mixed signals are excluded — they add nuance, not conflict.
        if net == SignalType.POSITIVE:
            positive_names.append(name)
        elif net == SignalType.NEGATIVE:
            negative_names.append(name)
        all_signals.extend(sigs)

    if not (positive_names and negative_names):
        return None

    # Only flag when the minority side is a meaningful fraction of clear-direction voters.
    # 1-vs-3 (25%) is a lone outlier; 1-vs-1 (50%) or 2-vs-3 (40%) is a genuine split.
    minority_voters = min(len(positive_names), len(negative_names))
    total_voters = len(positive_names) + len(negative_names)
    minority_ratio = minority_voters / total_voters if total_voters > 0 else 0.0

    if minority_voters < min_minority_voters or minority_ratio < min_minority_ratio:
        return None

    # HIGH = nearly even split, requires committee discussion.
    # MEDIUM = notable but skewed — worth mentioning, not blocking.
    severity = (
        DisagreementSeverity.HIGH
        if minority_ratio >= 0.45
        else DisagreementSeverity.MEDIUM
    )

    return DisagreementFlag(
        competency_id=competency.competency_id,
        competency_name=competency.name,
        disagreement_type=DisagreementType.DIRECTION_CONFLICT,
        severity=severity,
        description=(
            f"Interviewers disagree on {competency.name}. "
            f"{_join_names(positive_names)} assessed positively; "
            f"{_join_names(negative_names)} assessed negatively."
        ),
        interviewer_names=sorted(set(positive_names + negative_names)),
        supporting_evidence_spans=_collect_spans(all_signals),
        resolution_suggestion=(
            f"Discuss {competency.name} in the hiring committee. "
            "Ask each interviewer to describe the specific candidate behavior they observed "
            "and whether the bar was met for this role level."
        ),
    )


def _detect_evidence_absent(
    competency: Competency,
    debrief_groups: Dict[str, List[ExtractedSignal]],
    debrief_map: Dict[str, str],
) -> List[DisagreementFlag]:
    """Flag signals that make strong claims but have no verifiable evidence."""
    flags: List[DisagreementFlag] = []
    for debrief_id, sigs in debrief_groups.items():
        unsupported_high_conf = [
            s for s in sigs
            if s.is_unsupported and s.confidence >= 0.70
        ]
        if not unsupported_high_conf:
            continue
        name = _interviewer_name_from_signal(sigs[0], debrief_map)
        flags.append(
            DisagreementFlag(
                competency_id=competency.competency_id,
                competency_name=competency.name,
                disagreement_type=DisagreementType.EVIDENCE_ABSENT,
                severity=DisagreementSeverity.HIGH,
                description=(
                    f"{name}'s assessment of {competency.name} makes a confident claim "
                    f"(confidence={unsupported_high_conf[0].confidence:.0%}) "
                    "but no verbatim evidence was found in the debrief. "
                    "The claim cannot be independently verified."
                ),
                interviewer_names=[name],
                supporting_evidence_spans=[],
                resolution_suggestion=(
                    f"Ask {name} to provide specific examples or quotes that support "
                    f"their {competency.name} assessment."
                ),
            )
        )
    return flags


def _join_names(names: List[str]) -> str:
    if not names:
        return "no interviewer"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def detect_disagreements(
    signals: List[ExtractedSignal],
    rubric: RoleRubric,
    debriefs: Optional[List[InterviewDebrief]] = None,
) -> List[DisagreementFlag]:
    """
    Detect conflicts between interviewers across all competencies.

    Returns a list of DisagreementFlag objects sorted by severity (HIGH first).
    """
    debrief_map: Dict[str, str] = {}
    if debriefs:
        for d in debriefs:
            debrief_map[d.debrief_id] = d.interviewer_name

    # comp_id → debrief_id → [signals]
    grouped: Dict[str, Dict[str, List[ExtractedSignal]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for signal in signals:
        grouped[signal.competency_id][signal.debrief_id].append(signal)

    # Build competency lookup
    comp_map: Dict[str, Competency] = {c.competency_id: c for c in rubric.competencies}

    all_flags: List[DisagreementFlag] = []

    for comp_id, debrief_groups in grouped.items():
        competency = comp_map.get(comp_id)
        if competency is None:
            continue  # Signal references unknown competency — skip

        # Only check for conflicts when ≥2 debriefs assessed this competency
        if len(debrief_groups) >= 2:
            conflict = _detect_direction_conflict(competency, debrief_groups, debrief_map)
            if conflict:
                all_flags.append(conflict)

        # Evidence-absent check works per-debrief regardless of count
        all_flags.extend(
            _detect_evidence_absent(competency, debrief_groups, debrief_map)
        )

    # Sort: HIGH first, then MEDIUM, then LOW
    severity_order = {
        DisagreementSeverity.HIGH: 0,
        DisagreementSeverity.MEDIUM: 1,
        DisagreementSeverity.LOW: 2,
    }
    all_flags.sort(key=lambda f: severity_order.get(f.severity, 9))

    return all_flags
