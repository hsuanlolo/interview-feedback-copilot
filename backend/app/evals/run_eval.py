"""
Evaluation suite for the Interview Feedback Copilot.

Runs the full baseline pipeline against gold-labeled datasets and reports
the six metrics defined in docs/eval_plan.md.

Usage:
    cd backend
    python -m app.evals.run_eval
    python -m app.evals.run_eval --gold-dir ../sample_data/gold --output eval_results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Make sure backend root is importable when run directly
sys.path.insert(0, str(Path(__file__).parents[2]))

from app.schemas.models import InterviewDebrief, RoleRubric
from app.services.baseline_extractor import extract_all_baseline
from app.services.coverage_analyzer import analyze_coverage
from app.services.disagreement_detector import detect_disagreements
from app.services.evidence_verifier import verifier

SAMPLE_DIR = Path(__file__).parents[2] / "sample_data"


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class MetricResult:
    name: str
    value: float
    target: float
    passes: bool
    detail: str


@dataclass
class EvalResult:
    gold_id: str
    candidate_id: str
    metrics: List[MetricResult]
    all_pass: bool

    def summary_lines(self) -> List[str]:
        lines = [f"  Gold: {self.gold_id}  Candidate: {self.candidate_id}"]
        for m in self.metrics:
            status = "PASS" if m.passes else "FAIL"
            lines.append(f"    [{status}] {m.name}: {m.value:.2f} (target {m.target:.2f}) — {m.detail}")
        overall = "ALL PASS" if self.all_pass else "FAILED"
        lines.append(f"  Overall: {overall}")
        return lines


# ---------------------------------------------------------------------------
# Individual metric computations
# ---------------------------------------------------------------------------

def _citation_validity(signals, debriefs) -> MetricResult:
    result = verifier.verify(signals, debriefs)
    val = result.citation_validity_rate
    return MetricResult(
        name="citation_validity_rate",
        value=val,
        target=1.0,
        passes=(val == 1.0),
        detail=f"{result.valid_spans}/{result.total_spans_checked} spans valid",
    )


def _json_schema_validity(signals) -> MetricResult:
    """All signals must have been constructed via Pydantic — count is always 100% from baseline."""
    total = len(signals)
    # Signals produced by extract_all_baseline are already Pydantic objects; if any failed
    # validation they would have raised. Count any with unexpected defaults as invalid.
    valid = sum(1 for s in signals if s.signal_id and s.competency_id and s.extractor_version)
    val = valid / total if total > 0 else 1.0
    return MetricResult(
        name="json_schema_validity",
        value=val,
        target=1.0,
        passes=(val == 1.0),
        detail=f"{valid}/{total} signals valid",
    )


def _disagreement_recall(flags, gold_disagreements) -> MetricResult:
    """Recall: how many gold-labeled disagreements did the detector catch?"""
    if not gold_disagreements:
        return MetricResult(
            name="disagreement_recall",
            value=1.0,
            target=0.8,
            passes=True,
            detail="no gold disagreements to check",
        )
    detected_cids = {f.competency_id for f in flags}
    gold_cids = {d["competency_id"] for d in gold_disagreements}
    caught = len(detected_cids & gold_cids)
    total_gold = len(gold_cids)
    val = caught / total_gold if total_gold > 0 else 1.0
    return MetricResult(
        name="disagreement_recall",
        value=val,
        target=0.8,
        passes=(val >= 0.8),
        detail=f"caught {caught}/{total_gold} gold-labeled disagreements",
    )


def _coverage_completeness(coverage_map, gold_coverage_gaps) -> MetricResult:
    """Share of gold-labeled gaps correctly identified as partial or not_covered."""
    if not gold_coverage_gaps:
        return MetricResult(
            name="coverage_completeness",
            value=1.0,
            target=0.9,
            passes=True,
            detail="no gold coverage gaps to check",
        )
    # Build lookup: competency_id → coverage_status from computed map
    status_by_cid: Dict[str, str] = {
        ca.competency_id: ca.coverage_status
        for ca in coverage_map.competency_assessments
    }
    caught = 0
    for gap in gold_coverage_gaps:
        cid = gap["competency_id"]
        detected_status = status_by_cid.get(cid, "strong")
        # A gap is caught if the system also identified it as partial or not_covered
        if detected_status in ("partial", "not_covered", "conflicted"):
            caught += 1
    total = len(gold_coverage_gaps)
    val = caught / total if total > 0 else 1.0
    return MetricResult(
        name="coverage_completeness",
        value=val,
        target=0.9,
        passes=(val >= 0.9),
        detail=f"correctly identified {caught}/{total} gold-labeled gaps",
    )


def _omission_rate(signals, gold_concerns) -> MetricResult:
    """Share of must-not-be-omitted concerns that appear in extracted signals."""
    critical = [c for c in gold_concerns if c.get("must_not_be_omitted", False)]
    if not critical:
        return MetricResult(
            name="omission_rate",
            value=0.0,
            target=0.1,
            passes=True,
            detail="no must-not-be-omitted concerns labeled",
        )
    # Check whether each concern's verbatim phrase (or competency) appears in signals
    signal_text = " ".join(
        (s.claim + " " + " ".join(span.quoted_text for span in s.evidence_spans)).lower()
        for s in signals
    )
    signal_cids = {s.competency_id for s in signals}
    missed = 0
    for concern in critical:
        phrase = concern.get("verbatim_phrase", "").lower()
        cid = concern.get("competency_id", "")
        # A concern is present if either its competency was extracted OR the phrase appears
        found_by_cid = cid in signal_cids
        found_by_phrase = phrase and len(phrase) > 5 and phrase in signal_text
        if not (found_by_cid or found_by_phrase):
            missed += 1
    omission_rate = missed / len(critical)
    return MetricResult(
        name="omission_rate",
        value=omission_rate,
        target=0.1,
        passes=(omission_rate <= 0.1),
        detail=f"missed {missed}/{len(critical)} critical concerns",
    )


def _faithfulness(signals, debriefs) -> MetricResult:
    """
    Proxy faithfulness: for each signal, check that the claim contains no content
    that contradicts its evidence spans (heuristic: claim words must overlap with
    span text or be stop words). This is a weak proxy; production uses an LLM judge.
    """
    if not signals:
        return MetricResult(
            name="faithfulness_rate",
            value=1.0,
            target=0.9,
            passes=True,
            detail="no signals to check",
        )
    STOP = {"the", "a", "an", "is", "was", "were", "has", "have", "had", "it",
            "they", "their", "this", "that", "and", "or", "of", "in", "to",
            "for", "with", "on", "at", "from", "by", "about", "candidate",
            "demonstrated", "showed", "exhibited", "showed", "the", "some"}
    faithful_count = 0
    for signal in signals:
        if not signal.evidence_spans:
            # No spans — counts as unfaithful
            continue
        span_words = set()
        for span in signal.evidence_spans:
            span_words.update(span.quoted_text.lower().split())
        claim_content_words = [
            w.strip(".,;:\"'").lower()
            for w in signal.claim.split()
            if w.strip(".,;:\"'").lower() not in STOP and len(w) > 3
        ]
        if not claim_content_words:
            faithful_count += 1
            continue
        # A claim is faithful if ≥ 30% of its content words appear in the evidence spans
        overlap = sum(1 for w in claim_content_words if w in span_words)
        ratio = overlap / len(claim_content_words)
        if ratio >= 0.30:
            faithful_count += 1
    val = faithful_count / len(signals)
    return MetricResult(
        name="faithfulness_rate",
        value=val,
        target=0.9,
        passes=(val >= 0.9),
        detail=f"{faithful_count}/{len(signals)} signals pass word-overlap proxy",
    )


# ---------------------------------------------------------------------------
# Per-gold-record evaluation
# ---------------------------------------------------------------------------

def _load_debriefs_for_gold(gold: dict) -> List[InterviewDebrief]:
    debrief_dir = SAMPLE_DIR / "debriefs"
    debriefs: List[InterviewDebrief] = []
    for filename in gold["debrief_files"]:
        path = debrief_dir / filename
        if not path.exists():
            print(f"  WARNING: debrief file not found: {path}", file=sys.stderr)
            continue
        debriefs.append(InterviewDebrief(
            candidate_id=gold["candidate_id"],
            interviewer_name=_parse_interviewer_name(path.read_text()),
            raw_text=path.read_text(),
        ))
    return debriefs


def _parse_interviewer_name(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("Interviewer:"):
            return line.split(":", 1)[1].strip()
    return "Unknown"


def _load_rubric_for_gold(gold: dict) -> Optional[RoleRubric]:
    rubric_path = SAMPLE_DIR / "rubrics" / "data_scientist_rubric.json"
    if not rubric_path.exists():
        return None
    return RoleRubric.model_validate(json.loads(rubric_path.read_text()))


def eval_gold_record(gold: dict) -> EvalResult:
    print(f"\nEvaluating {gold['gold_id']} …")

    debriefs = _load_debriefs_for_gold(gold)
    rubric = _load_rubric_for_gold(gold)

    if not debriefs or rubric is None:
        print("  ERROR: could not load debriefs or rubric", file=sys.stderr)
        return EvalResult(
            gold_id=gold["gold_id"],
            candidate_id=gold["candidate_id"],
            metrics=[],
            all_pass=False,
        )

    # Run the full pipeline
    signals, warnings = extract_all_baseline(debriefs, rubric)
    if warnings:
        for w in warnings:
            print(f"  WARN: {w}", file=sys.stderr)

    coverage_map = analyze_coverage(signals, rubric, debriefs)
    flags = detect_disagreements(signals, rubric, debriefs)

    # Compute metrics
    metrics = [
        _citation_validity(signals, debriefs),
        _json_schema_validity(signals),
        _disagreement_recall(flags, gold.get("disagreements", [])),
        _coverage_completeness(coverage_map, gold.get("coverage_gaps", [])),
        _omission_rate(signals, gold.get("concerns", [])),
        _faithfulness(signals, debriefs),
    ]
    all_pass = all(m.passes for m in metrics)
    return EvalResult(
        gold_id=gold["gold_id"],
        candidate_id=gold["candidate_id"],
        metrics=metrics,
        all_pass=all_pass,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_eval(gold_dir: Path, output_path: Optional[Path]) -> bool:
    gold_files = sorted(gold_dir.glob("*.json"))
    if not gold_files:
        print(f"No gold files found in {gold_dir}", file=sys.stderr)
        return False

    print(f"Found {len(gold_files)} gold file(s) in {gold_dir}")

    results: List[EvalResult] = []
    for gf in gold_files:
        gold = json.loads(gf.read_text())
        result = eval_gold_record(gold)
        results.append(result)

    # Print summary table
    print("\n" + "=" * 60)
    print("EVAL RESULTS")
    print("=" * 60)
    for r in results:
        for line in r.summary_lines():
            print(line)

    overall_pass = all(r.all_pass for r in results)
    print("\n" + "=" * 60)
    print(f"OVERALL: {'ALL PASS — meets release gates' if overall_pass else 'FAILED — does not meet release gates'}")
    print("=" * 60)

    if output_path:
        output = [asdict(r) for r in results]
        output_path.write_text(json.dumps(output, indent=2))
        print(f"\nResults written to {output_path}")

    return overall_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Interview Feedback Copilot eval suite.")
    parser.add_argument(
        "--gold-dir",
        type=Path,
        default=SAMPLE_DIR / "gold",
        help="Directory containing gold JSON files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write JSON results (optional)",
    )
    args = parser.parse_args()
    passed = run_eval(args.gold_dir, args.output)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
