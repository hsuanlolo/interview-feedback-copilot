# Evaluation Plan

---

## Why Evaluation Matters

A prior summarization pilot was considered unsuccessful because it **missed obvious red flags**. Without a formal eval, we cannot know if our tool has the same problem. Every release must be gated on measurable quality.

---

## Gold Dataset

**Source:** Small set of anonymized historical slates with expert-labeled annotations.  
**Size target:** 10–20 candidate slates for initial eval, growing over time.  
**Location:** `sample_data/gold/`

Each gold record includes:
- The raw debrief text(s)
- The role rubric used
- Human-labeled `strengths`: positive evidence that should appear in the synthesis
- Human-labeled `concerns`: concerns / red flags that must not be omitted
- Human-labeled `disagreements`: cases where interviewers conflict
- Human-labeled `coverage_gaps`: required competencies no one assessed

For portfolio purposes, gold labels are hand-crafted from the synthetic sample data.

---

## Metrics

### 1. Faithfulness Rate (Primary — Release Gating)

**Definition:** Share of model-generated claims that are entailed by their cited source span.

**Method:** For each claim + evidence span pair, check if the claim is a reasonable inference from the quoted text. In production this would use an LLM judge or NLI model; in portfolio eval we use manual spot-check + string overlap heuristics.

**Target:** ≥ 90%  
**Release gate:** Must exceed target before any pilot use.

---

### 2. Omission Rate (Primary — Release Gating)

**Definition:** Share of human-labeled red flags (concerns) that are absent from the generated synthesis.

**Why primary:** The prior pilot failed on exactly this metric. Missing a red flag is a worse error than including a false concern (reviewer can delete false positives; they can't correct missing evidence they didn't see).

**Method:** For each gold-labeled concern, check if equivalent signal appears in the synthesis.

**Target:** ≤ 10% (no more than 1 in 10 labeled red flags omitted)  
**Release gate:** Hard ceiling.

---

### 3. Citation Validity Rate

**Definition:** Share of evidence spans where `quoted_text` appears verbatim in the source debrief at the stated character offsets.

**Method:** Deterministic string search. `EvidenceVerifier` computes this automatically.

**Target:** 100% (any invalid citation is a hallucination — unacceptable)  
**Release gate:** Hard ceiling.

---

### 4. Disagreement Recall

**Definition:** Share of human-labeled interviewer disagreements that appear in the generated disagreement flags.

**Why recall over precision:** A missed disagreement is worse than a spurious flag. The reviewer can dismiss a false alarm; they cannot address a conflict they didn't know existed.

**Target:** ≥ 80%  
**Monitored:** Precision also tracked to avoid alert fatigue (too many spurious flags hurt trust).

---

### 5. Coverage Completeness

**Definition:** Share of gold-labeled coverage gaps correctly identified in the coverage map.

**Method:** For each competency the gold dataset marks as "not assessed," check if the coverage map correctly shows it as Not Covered or Thin Coverage.

**Target:** ≥ 90%

---

### 6. JSON Schema Validity

**Definition:** Share of LLM extraction responses that pass Pydantic validation without errors.

**Target:** 100% (Pydantic validation is the gate — invalid output is surfaced as an error, not accepted)  
**Note:** This is a measure of prompt quality, not model quality.

---

## Eval Script

Located at: `backend/app/evals/run_eval.py`

Usage:
```bash
cd backend
python -m app.evals.run_eval --gold-dir ../sample_data/gold --output eval_results.json
```

Output: Metrics table printed to stdout + JSON results file.

---

## Release Gating Criteria

Before any pilot deployment with real hiring data:

| Metric | Minimum |
|--------|---------|
| Faithfulness rate | ≥ 90% |
| Omission rate (red flags) | ≤ 10% |
| Citation validity | 100% |
| Disagreement recall | ≥ 80% |
| JSON schema validity | 100% |

All gates must pass simultaneously.

---

## Long-Horizon Metrics (Production Only)

These require real deployment and human feedback:
- **Time-to-decision per slate:** Compared to pre-tool baseline
- **Raw-debrief click-through rate:** Healthy = some verification; near zero = over-reliance
- **Reviewer edit patterns:** Additions of missed concerns = weak red-flag extraction; deletions of strong claims = over-assertive synthesis prompt
- **Decision quality:** Correlation of surfaced concerns with downstream performance (long lag, small N — interpret cautiously)

---

## Known Eval Limitations

1. **Gold labels are synthetic for portfolio.** In real deployment, labels must come from expert human annotators reviewing real (anonymized) debriefs.
2. **LLM judge for faithfulness is itself fallible.** String-overlap heuristics are used as a proxy.
3. **Recall-precision tradeoff is implicit.** Lowering the omission rate threshold may increase spurious flags.
4. **No inter-annotator agreement measured.** Disagreement labels especially benefit from multiple annotators.
