"""
Coverage map analyzer (PROMPT 8).

Rolls up ExtractedSignals across all interviewers per competency and produces:
  - CompetencyAssessment for each competency in the rubric
  - CoverageGap for each NOT_COVERED or PARTIAL competency
  - overall_coverage_pct across all required competencies

CoverageStatus logic
--------------------
  NOT_COVERED  — no signals at all for this competency
  PARTIAL      — exactly 1 debrief assessed it (regardless of direction)
  STRONG       — ≥2 debriefs assessed, at least one POSITIVE/MIXED signal
  CONFLICTED   — ≥2 debriefs assessed, directions disagree (some POS, some NEG)

Why "per debrief" not "per interviewer name"?
  Multiple debriefs from the same interviewer name would double-count.
  debrief_id is the unique unit of observation.
"""

from __future__ import annotations

from collections import defaultdict

from app.schemas.models import (
    Competency,
    CompetencyAssessment,
    CoverageGap,
    CoverageMapResponse,
    CoverageStatus,
    ExtractedSignal,
    InterviewDebrief,
    InterviewerAssessment,
    RoleRubric,
    SignalType,
)


def _interviewer_name(signal: ExtractedSignal, debrief_map: dict[str, str]) -> str:
    if signal.debrief_id in debrief_map:
        return debrief_map[signal.debrief_id]
    if signal.evidence_spans:
        return signal.evidence_spans[0].interviewer_name
    return f"Interviewer-{signal.debrief_id[:6]}"


def _dominant_signal_type(signals: list[ExtractedSignal]) -> SignalType:
    """Return the dominant direction across a list of signals from one debrief."""
    types = [s.signal_type for s in signals]
    if SignalType.POSITIVE in types and SignalType.NEGATIVE in types:
        return SignalType.MIXED
    if SignalType.NEGATIVE in types:
        return SignalType.NEGATIVE
    if SignalType.POSITIVE in types:
        return SignalType.POSITIVE
    if SignalType.MIXED in types:
        return SignalType.MIXED
    return SignalType.UNCLEAR


def _coverage_status(assessments: list[InterviewerAssessment]) -> CoverageStatus:
    if not assessments:
        return CoverageStatus.NOT_COVERED
    if len(assessments) == 1:
        return CoverageStatus.PARTIAL

    types = {a.signal_type for a in assessments}
    has_positive = bool(types & {SignalType.POSITIVE, SignalType.MIXED})
    has_negative = bool(types & {SignalType.NEGATIVE, SignalType.MIXED})

    if has_positive and has_negative:
        return CoverageStatus.CONFLICTED
    if has_positive:
        return CoverageStatus.STRONG
    # ≥2 interviewers, all negative or unclear
    return CoverageStatus.PARTIAL


def _suggested_followup(competency: Competency, status: CoverageStatus) -> str:
    name = competency.name.lower()
    if status == CoverageStatus.NOT_COVERED:
        return (
            f"No interviewer assessed {competency.name}. "
            f'Suggested question: "Can you describe a situation where you demonstrated {name}?"'
        )
    if status == CoverageStatus.PARTIAL:
        return (
            f"{competency.name} was assessed by only one interviewer. "
            "A second opinion would strengthen or challenge this single data point."
        )
    return ""


def analyze_coverage(
    signals: list[ExtractedSignal],
    rubric: RoleRubric,
    debriefs: list[InterviewDebrief] | None = None,
) -> CoverageMapResponse:
    """
    Build a coverage map for all competencies in the rubric.

    Parameters
    ----------
    signals:  All extracted signals for this candidate (may span multiple debriefs).
    rubric:   The role rubric — defines which competencies must be assessed.
    debriefs: Optional list of source debriefs for accurate interviewer name lookup.
    """
    # Build debrief_id → interviewer_name lookup
    debrief_map: dict[str, str] = {}
    all_interviewers: list[str] = []
    if debriefs:
        for d in debriefs:
            debrief_map[d.debrief_id] = d.interviewer_name
            if d.interviewer_name not in all_interviewers:
                all_interviewers.append(d.interviewer_name)

    # Group signals by (competency_id, debrief_id)
    # comp_id → debrief_id → [signals]
    grouped: dict[str, dict[str, list[ExtractedSignal]]] = defaultdict(lambda: defaultdict(list))
    for signal in signals:
        grouped[signal.competency_id][signal.debrief_id].append(signal)

    # Derive interviewers from signals if debriefs not provided
    if not all_interviewers:
        seen = set()
        for signal in signals:
            name = _interviewer_name(signal, debrief_map)
            if name not in seen:
                all_interviewers.append(name)
                seen.add(name)

    competency_assessments: list[CompetencyAssessment] = []
    coverage_gaps: list[CoverageGap] = []
    covered_required = 0
    total_required = 0

    for competency in rubric.competencies:
        cid = competency.competency_id
        if competency.required:
            total_required += 1

        debrief_signals = grouped.get(cid, {})

        # Build one InterviewerAssessment per debrief
        assessments: list[InterviewerAssessment] = []
        positive_evidence: list[ExtractedSignal] = []
        negative_evidence: list[ExtractedSignal] = []
        vague_claims: list[ExtractedSignal] = []

        for debrief_id, sigs in debrief_signals.items():
            name = _interviewer_name(sigs[0], debrief_map)
            dominant = _dominant_signal_type(sigs)
            summary_sig = max(sigs, key=lambda s: s.confidence)
            summary = summary_sig.claim

            assessments.append(
                InterviewerAssessment(
                    interviewer_name=name,
                    signal_type=dominant,
                    signals=sigs,
                    summary=summary,
                )
            )

            for sig in sigs:
                if sig.signal_type in (SignalType.POSITIVE, SignalType.MIXED):
                    positive_evidence.append(sig)
                if sig.signal_type in (SignalType.NEGATIVE, SignalType.MIXED):
                    negative_evidence.append(sig)
                if sig.is_vague:
                    vague_claims.append(sig)

        status = _coverage_status(assessments)

        if competency.required and status not in (
            CoverageStatus.NOT_COVERED,
            CoverageStatus.PARTIAL,
        ):
            covered_required += 1

        competency_assessments.append(
            CompetencyAssessment(
                competency_id=cid,
                competency_name=competency.name,
                coverage_status=status,
                assessments_by_interviewer=assessments,
                positive_evidence=positive_evidence,
                negative_evidence=negative_evidence,
                vague_claims=vague_claims,
            )
        )

        if status in (CoverageStatus.NOT_COVERED, CoverageStatus.PARTIAL):
            coverage_gaps.append(
                CoverageGap(
                    competency_id=cid,
                    competency_name=competency.name,
                    coverage_status=status,
                    interviewers_who_assessed=[a.interviewer_name for a in assessments],
                    suggested_followup=_suggested_followup(competency, status),
                )
            )

    overall_pct = (covered_required / total_required * 100.0) if total_required > 0 else 100.0

    return CoverageMapResponse(
        competency_assessments=competency_assessments,
        coverage_gaps=coverage_gaps,
        overall_coverage_pct=round(overall_pct, 1),
        interviewers=all_interviewers,
    )


# Module-level singleton — stateless, safe to share
coverage_analyzer = type("CoverageAnalyzer", (), {"analyze_coverage": staticmethod(analyze_coverage)})()
