# Product Brief — Evidence-Grounded Interview Feedback Copilot

**Author:** Hsuan Lo  
**Version:** 1.0  
**Status:** Active development

---

## 1. Problem Statement

Hiring managers reviewing candidate slates face three recurring failure modes:

**Buried signal.** A debrief may be 600 words of narrative prose. Key concerns — a shallow answer, a missed concept — are grammatically buried under hedged phrasing. Reviewers often miss them on a first pass.

**Late-surfacing disagreements.** Interviewer A scores a candidate 4/5 on analytical reasoning; Interviewer B gives 2/5. This conflict surfaces at the debrief meeting, after all interviews are complete, when it is too late to run a follow-up.

**Anchoring effects.** The first debrief read shapes how the hiring manager interprets everything that follows. Leading with an enthusiastic debrief raises the prior; leading with a negative one lowers it. Neither is fair to the evidence.

A prior summarization pilot was considered unsuccessful because it **missed or softened obvious red flags**. The tool was too eager to produce clean, positive-sounding summaries.

---

## 2. Users

**Primary:** Hiring managers reviewing candidates for technical roles (data science, engineering, quant research).

**Secondary:** Recruiting coordinators managing interview loops; interviewers who want to see how their feedback compares to others (after decision).

**Not in scope:** Candidates. This tool is internal to the hiring team.

---

## 3. Product Goals

| Goal | Metric |
|------|--------|
| Surface red flags reliably | Omission rate of labeled red flags ≤ 10% |
| Reduce time-to-debrief review | Time per candidate slate reduced vs. baseline |
| Surface interviewer disagreements early | Disagreement recall ≥ 80% |
| Build reviewer trust through transparency | Reviewer edits per report (lower = trust; ~0 = over-reliance, both are signals) |
| Ensure all claims are grounded | Citation validity ≥ 95% |

---

## 4. Non-Goals (Deliberate Design Boundaries)

These are not gaps. They are deliberate constraints.

- **No hire/no-hire recommendation.** An aggregate recommendation compresses away the evidence that makes a decision defensible. It also reproduces "AI scoring" concerns already voiced by stakeholders.
- **No cross-candidate ranking.** Ranking amplifies any wording or selection bias latent in the debriefs. The model would inherit and potentially entrench it.
- **No protected-characteristic inference.** No sentiment about personality, communication style as a proxy, or any inference beyond competency-grounded evidence from the debrief text.
- **No automated decisions.** Human review is required before any synthesis is used in a hiring decision.

---

## 5. User Workflow (Before / After)

### Before (Current State)
1. Recruiter collects 4–6 email or form-based debriefs
2. Hiring manager reads all debriefs sequentially (30–45 min)
3. Hiring manager builds a mental model of each competency
4. Debrief meeting: conflicts surfaced in real time, no time to resolve
5. Decision made with partial, unstructured evidence

### After (With Tool)
1. Debriefs uploaded to the tool (file upload or paste)
2. Tool extracts structured signals with source citations
3. Tool shows coverage map: which competencies were and weren't assessed
4. Tool flags disagreements between interviewers, ranked by severity
5. Tool generates synthesis draft — reviewer reads, edits, approves
6. Debrief meeting: structured report reviewed, conflicts already identified
7. Decision made with organized, traceable evidence

---

## 6. Product Assumptions

- Interviewer scoring scales are not standardized across teams. The normalization layer accounts for this.
- The rubric is defined per role, not per interviewer. Rubrics are pre-loaded or uploaded by the recruiter.
- Debriefs are written in English prose. Structured forms (checkboxes, dropdowns) are out of scope for v1.
- The hiring loop has 3–6 interviewers. A single-interviewer debrief is valid but will show thin coverage.

---

## 7. Open Questions

1. What decision is being made at the synthesis point, and what evidence would change it?
2. Do we have labeled historical slates to anchor evaluation? (Needed for eval harness)
3. Is the rubric shared across interviewers, or does each interviewer define their own?
4. What is the governance process before this tool is used in real hiring decisions?
5. Who owns the final synthesis — recruiter, hiring manager, or HR?
