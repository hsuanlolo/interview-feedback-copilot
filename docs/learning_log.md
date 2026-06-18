# Learning Log

Each entry records what changed, why it was designed that way, what you should learn, how to test it, and what could fail in production.

---

## Milestone 0: Project Documentation

**What changed:**  
Created `CLAUDE.md`, `README.md`, and all `docs/` files. No code yet.

**Why designed this way:**  
Documentation-first forces clarity before code. The non-negotiable rules (no hire/no-hire, all claims cite source text) must be written down before implementation so that every later code decision can reference them.

**Engineering concept to understand:**  
**Architecture Decision Records (ADRs).** An ADR is a short document that records a significant technical decision: the context, the options considered, and the rationale for the choice. The key insight is that the "why" is more valuable than the "what" — code is readable, but the reasoning behind it is not.

Read: `docs/decisions.md` to see the ADR format in practice.

**How to test it manually:**  
- Read `CLAUDE.md` and verify the rules make sense for the project.
- Read `docs/product_brief.md` and ask: "What is the tool NOT supposed to do?" (Answer: no hire/no-hire recommendation, no ranking, no protected-characteristic inference.)
- Read `docs/eval_plan.md` and identify which metric has a hard ceiling on release. (Answer: citation validity — 100% required.)

**What could fail in production:**  
Documentation that doesn't match code is worse than no documentation. The `CLAUDE.md` rules must be enforced in code reviews, not just stated.

---

## Milestone 1: Repo Structure

**What changed:**  
Created full project directory tree. Backend uses FastAPI. Frontend uses Next.js. Placeholder files in each directory.

**Why designed this way:**  
Separating backend and frontend into distinct directories (`backend/`, `frontend/`) reflects how they will be deployed separately. The backend is a Python service; the frontend is a Node.js service. They communicate via HTTP/JSON, not via function calls or shared state.

**Engineering concept to understand:**  
**Separation of concerns in a full-stack app.** The backend owns business logic, data models, and LLM calls. The frontend owns user interaction and display. They agree on an API contract (documented by FastAPI's auto-generated OpenAPI spec at `/docs`).

Compare this to a data science notebook project: a notebook mixes data loading, model logic, and visualization in one file. A production app separates them so each part can be tested, deployed, and modified independently.

**How to test it manually:**
```bash
# Verify structure
find interview-feedback-copilot -type f | head -40

# Start backend
cd backend && uvicorn app.main:app --reload
# Open http://localhost:8000/docs — should show Swagger UI

# Start frontend
cd frontend && npm run dev
# Open http://localhost:3000
```

**What could fail in production:**  
CORS misconfiguration — the browser will block frontend requests to the backend if the backend doesn't explicitly allow the frontend's origin. Configure `CORSMiddleware` in FastAPI.

---

## Milestone 2: Pydantic Data Models

**What changed:**  
Created `backend/app/schemas/models.py` with all core data schemas. Added `backend/app/tests/test_schemas.py`.

**Why designed this way:**  
Pydantic schemas are the source of truth for data shape throughout the system. Before writing a single API endpoint or LLM prompt, we define what data looks like. This prevents the common mistake of building an API and then discovering the data model doesn't support the query you need.

**Engineering concept to understand:**  
**Schema-first design.** In LLM applications, Pydantic serves a second role beyond data validation: it defines the structured output format you ask the LLM to produce. When you ask an LLM to return JSON, that JSON must conform to a Pydantic schema. If it doesn't, the app rejects it. This is the most important protection against hallucination-shaped failures.

**How to test it manually:**
```bash
cd backend
python -m pytest app/tests/test_schemas.py -v
```

Try instantiating a schema with invalid data and observe the error:
```python
from app.schemas.models import ExtractedSignal
# This should raise a ValidationError:
s = ExtractedSignal(signal_type="very_positive", claim="great candidate")
```

**What could fail in production:**  
Schema drift: the LLM prompt says "return JSON with field X" but the Pydantic schema expects field Y. This happens when prompts are updated without updating schemas, or vice versa. Always update both together.

---

## Milestone 3: Sample Data

**What changed:**  
Created synthetic role rubric (`data_scientist_rubric.json`) and 5 debrief files for one fictional candidate.

**Why designed this way:**  
Synthetic data lets us build and test the full pipeline without using real candidate data. It is also intentionally messy — vague claims, missing competencies, interviewer disagreements — because the system must handle realistic imperfection, not clean idealized input.

**Engineering concept to understand:**  
**Evaluation-first data design.** The sample data was designed to test specific failure modes: omission of red flags, disagreement detection, coverage gap identification. A good test dataset is one where you know what the correct output should be, so you can measure whether the system produces it.

**How to test it manually:**  
Read `sample_data/debriefs/candidate_001_interviewer_3.txt` and identify:
1. Which competency gets a negative signal?
2. Which claim is vague or unsupported?
3. Which claim contradicts Interviewer 1's assessment?

Then run the baseline extractor (after Milestone 5) and check if it finds those signals.

**What could fail in production:**  
"Garbage in, garbage out." A two-sentence debrief cannot be enriched. The tool must represent thin evidence honestly (low evidence density signal) rather than manufacture depth. Poorly written debriefs are a real-world problem; the system must not make them look authoritative.

---

## Milestone 4: FastAPI API Skeleton

**What changed:**  
Added three routers (`rubrics`, `debriefs`, `projects`), an in-memory store, and 29 integration tests. The server now starts and all five PROMPT 4 endpoints are live.

**Why designed this way:**  
**Thin routers, logic in services.** Each router file is ~30 lines — it receives the HTTP request, delegates to a service or store, and returns a response. The store holds the business data. This separation means you can test the store logic (unit test) and the HTTP contract (integration test) independently.

**The store is a singleton dict.** Rather than reach for a database on day one, we keep the state in a module-level object. This is deliberately fragile (data disappears on restart) — the point is to prove the API works before adding migration complexity.

**Engineering concept to understand:**  
**REST API design.** `POST /projects` creates a resource and returns `201 Created`. `GET /projects/{id}` returns that resource or `404 Not Found`. `422 Unprocessable Entity` is returned automatically by FastAPI + Pydantic when the request body fails validation — you don't have to write that error handling yourself. This is one of FastAPI's core value propositions.

**Automatic API docs.** Run the server and visit `http://localhost:8000/docs`. FastAPI generates an interactive Swagger UI from your code — no extra work. This is your first testing surface for collaborators who don't write Python.

**How to test it manually:**
```bash
cd backend
uvicorn app.main:app --reload

# In another terminal:
curl http://localhost:8000/health
curl http://localhost:8000/rubrics/sample | python -m json.tool
curl http://localhost:8000/debriefs/sample | python -m json.tool | head -30

# Create a project
curl -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"candidate_name": "Jordan Lee", "role_title": "Data Scientist"}'

# Then GET it with the returned project_id
curl http://localhost:8000/projects/<project_id>
```

Or visit `http://localhost:8000/docs` and use the interactive UI.

**What could fail in production:**  
1. **State loss.** The in-memory store loses all data on restart. Fine for demos; unacceptable for production. Fix: database (PROMPT 15).  
2. **No auth.** Anyone with the URL can create projects. Fix: authentication middleware (post-v1 scope).  
3. **No input size limit.** A very large debrief body could exhaust memory. Fix: FastAPI body size limits + request size middleware.  
4. **CORS.** The default config only allows `localhost:3000`. Fix: configure `CORS_ORIGINS` env var for the deployed frontend URL.

---

## Milestone 5: Deterministic Baseline Extractor

**What changed:**  
Added `backend/app/services/baseline_extractor.py` — a keyword-matching extractor that produces `ExtractedSignal` objects without calling any LLM. Added `backend/app/routers/extract.py` with `POST /extract/baseline` (live) and `POST /extract/llm` (501 stub). Added 37 new tests in `backend/app/tests/test_baseline_extractor.py`. Total test count: 84.

**Why designed this way:**  
**Baseline-first evaluation.** Before writing a single LLM prompt, we need a lower bound: how well does the dumbest possible extractor do? This makes the LLM's value measurable. If the LLM extractor achieves 80% recall and the baseline achieves 45%, that 35-point lift is evidence the LLM is worth its cost and latency.

The baseline has known, designed-in limitations: it cannot handle negation ("did not demonstrate strong reasoning" → classified POSITIVE because "strong" is present), it misses signals phrased without rubric vocabulary, and it conflates competencies that share generic vocabulary. These are documented in the module docstring — this transparency is the design, not a bug.

**The offset problem.** Every `EvidenceSpan` must carry `start_char` and `end_char` that point into the original `raw_text`. This means when the extractor processes only the body (after the "---" separator), offsets must be adjusted by `body_offset` before being stored. The test `test_span_offsets_are_valid` verifies this by doing `raw_text[start_char:end_char] == quoted_text` for every span returned by the endpoint.

**Confidence is a gradient, not a binary.** Confidence scores differentiate three cases: rubric indicator phrase match (0.75), generic sentiment vocabulary match (0.50), and no sentiment signal (0.25/UNCLEAR). The LLM extractor will produce finer-grained confidence from its reasoning trace.

**Engineering concept to understand:**  
**Text extraction with character offsets.** A naive implementation stores which sentence matched but not where in the original document. Adding character offsets (`start_char`, `end_char`) enables three things: (1) a verifier can check that `raw_text[start:end] == quoted_text`, catching hallucinated citations; (2) the frontend can highlight the exact span; (3) the eval suite can measure whether the LLM and baseline agree on the same text. Offsets are annoying to get right (off-by-one errors are common) but they are the foundation of an honest citation system.

**How to test it manually:**
```bash
cd backend
uvicorn app.main:app --reload

# In another terminal:
# 1. Get the sample rubric
curl http://localhost:8000/rubrics/sample > rubric.json

# 2. Get a sample debrief
curl http://localhost:8000/debriefs/sample | python -m json.tool | head -40

# 3. Run baseline extraction (build the JSON manually or use /docs)
# Visit http://localhost:8000/docs → POST /extract/baseline
# Paste the rubric JSON and one debrief object, click Execute.

# 4. Run tests
python -m pytest app/tests/test_baseline_extractor.py -v
```

Key things to inspect in the response:
- `extractor_used`: should be `"baseline-v1"`
- `total_signals`: should be ≥ 1 for a substantive debrief
- Each signal's `evidence_spans[].quoted_text` should be verbatim text from the debrief
- `warnings`: will note short debriefs or debriefs with no vocabulary overlap

**What could fail in production:**  
1. **Negation blindness.** "The candidate did not show strong statistical reasoning" will be classified POSITIVE because "strong" matches `_POSITIVE_WORDS`. This is acceptable for the baseline (we document it); the LLM extractor must handle it.  
2. **Offset drift from Unicode.** If the raw text contains multi-byte UTF-8 characters (e.g., smart quotes, em-dashes), Python's `str.find()` and string indexing work on Unicode code points, not bytes. This is correct for our use case (we store the Python string, not bytes). Watch for issues if the frontend or database introduces byte-level indexing.  
3. **Rubric vocabulary mismatch.** If interviewers use "quantitative thinking" instead of "statistical reasoning," the baseline will miss the signal. The LLM extractor handles paraphrasing; the baseline does not.  
4. **Span cap.** We cap at 4 evidence spans per signal. For very long, rich debriefs, relevant sentences beyond the first 4 are silently dropped. This is a deliberate simplification — the claim should be supported by the first 4 matches; more is noise for the reviewer.

---

## Milestone 6: LLM Extraction Interface

**What changed:**  
Added `backend/app/services/llm_client.py` with three classes (`LLMClientBase`, `MockLLMClient`, `AnthropicLLMClient`) and supporting helpers (`_locate_quotes`, `_draft_to_signal`, `extract_all_llm`). Replaced the 501 stub in `POST /extract/llm` with a real implementation using FastAPI dependency injection. Added 38 new tests in `backend/app/tests/test_llm_extractor.py`. Total test count: 122.

**Why designed this way:**  
**The offset problem — Python computes positions, not Claude.** Asking Claude to produce character offsets (`start_char=42, end_char=89`) would be unreliable — LLMs can't count characters accurately. Instead, we ask Claude to produce verbatim quoted text, then `_locate_quotes()` uses Python's `str.find()` to compute exact offsets. This means every `EvidenceSpan` produced by the LLM extractor has the same accuracy guarantee as the baseline extractor, even though the mechanism is completely different.

**Pydantic validation gates all LLM output** (the non-negotiable rule in practice). The flow is:  
1. Claude responds via `tool_use` → raw dict → `LLMExtractionOutput.model_validate()` → `ValidationError` if invalid  
2. Each quote searched in `raw_text` → missing quotes produce warnings, never spans  
3. `ExtractedSignal(...)` construction → another Pydantic validation pass  
At no step is invalid data silently accepted. `AnthropicLLMClient._call_api()` raises `HTTPException(422)` on validation failure so the caller sees a structured error.

**`get_llm_client()` as a FastAPI Depends** lets tests inject `MockLLMClient()` via `app.dependency_overrides` without touching production code or env vars. The test for "503 when no API key" deliberately does NOT use the override, confirming the factory raises the right error in the default test environment.

**Engineering concept to understand:**  
**Dependency injection in FastAPI.** When `Depends(get_llm_client)` appears in a route signature, FastAPI resolves it before calling the handler. In tests, `app.dependency_overrides[get_llm_client] = lambda: MockLLMClient()` swaps out the real factory for the mock. This is the same pattern used to swap databases, auth, email providers, and any other external dependency in tests — no monkeypatching, no global state mutation, no `if TEST_MODE:` branches in production code.

**Tool-use for structured output.** The `tool_choice={"type": "tool", "name": "extract_competency_signals"}` parameter forces Claude to call that specific tool, guaranteeing a structured JSON response. Without `tool_choice`, Claude might respond in prose and the JSON parsing would fail. Forced tool calling is the reliable path to structured LLM output.

**How to test it manually:**  
```bash
cd backend
uvicorn app.main:app --reload

# With a real API key:
export ANTHROPIC_API_KEY="your-key-here"

# Then POST to /extract/llm with sample data (use /docs Swagger UI)
# GET /rubrics/sample to get the rubric, GET /debriefs/sample for debriefs,
# then POST /extract/llm

# Without an API key — enable mock mode:
LLM_MOCK_MODE=true uvicorn app.main:app --reload
# /extract/llm now returns mock-v1 signals

# Run tests (all use mock mode via dependency_overrides — no API key needed):
python -m pytest app/tests/test_llm_extractor.py -v
```

**What could fail in production:**  
1. **Claude changes its tool_use response format.** If Anthropic updates the API response structure, `tool_blocks[0].input` might change shape. Pin the `anthropic` SDK version in `pyproject.toml` and test upgrades in CI.  
2. **Quote inexact match.** If Claude slightly misquotes (adds a trailing space, changes punctuation), `str.find()` returns -1 and the span is flagged as hallucinated. In practice, Claude with the verbatim-quote instruction is very accurate. A fuzzy match fallback (e.g., `difflib.SequenceMatcher`) could recover mild misquotes but risks accepting paraphrases — not implemented here.  
3. **Long debriefs approach token limits.** A 10,000-word debrief plus the rubric plus the system prompt can exceed `max_tokens=4096` for the output. Consider chunking very long debriefs by competency or adding input size validation in the endpoint.  
4. **Cost.** At current claude-opus-4-8 pricing, 5 rich debriefs = ~10,000 tokens input + ~2,000 tokens output ≈ $0.10–0.15 per extraction run. Fine for demo; budget for production throughput.

---

## Milestone 7: Evidence Verifier

**What changed:**  
Added `backend/app/services/evidence_verifier.py` (`EvidenceVerifier`, `_check_span`), `backend/app/routers/verify.py` (`POST /verify/evidence`), and `VerificationRequest` schema. Added 26 new tests, including an end-to-end integration test that runs the baseline extractor and then verifies every returned span. Total test count: 148.

**Why designed this way:**  
**Verification is a separate pass, not part of extraction.** The extractor produces signals; the verifier independently confirms that each signal's evidence actually exists at the stated position. Keeping them separate means you can swap or upgrade either component — a better LLM extractor still gets verified the same way. It also lets you verify baseline-extracted signals and LLM-extracted signals through a single, auditable code path.

**Three failure modes, deliberately distinct:**
- `text_not_found` — the quoted text does not appear anywhere in the debrief. This is a hallucination: the LLM invented a quote. Hard failure; synthesis blocked.
- `offset_mismatch` — the text exists in the debrief but not at the stated `[start_char:end_char]`. This is an extractor bug: the text is real but the index is wrong. Still a hard failure because the span is unusable as a verifiable citation until fixed.
- `source_missing` — the span references a `debrief_id` that wasn't provided to the verifier. This catches pipeline integration errors where debriefs and signals are assembled from different runs.

**`is_valid` is a hard binary gate.** Any single error flips `is_valid=False`. This mirrors the eval plan's "citation validity 100% (hard gate)" requirement. The `citation_validity_rate` field gives the reviewer a proportional view (e.g., "19 of 20 spans valid"), but synthesis in PROMPT 10 will check `is_valid`, not the rate.

**`is_vague` is a reviewer flag, not a validity error.** A vague signal (hedged language) with a valid span is still a valid citation — the evidence is real, just thin. The reviewer sees it in `vague_claims` and decides whether to include or remove it from the report.

**Engineering concept to understand:**  
**model_construct() for adversarial testing.** Tests for the verifier need spans with deliberately invalid offsets or invented text. Pydantic's normal constructors would reject these. `model_construct()` bypasses all validators, letting tests create intentionally broken objects to confirm the verifier detects them. This is the correct tool when you want to test downstream validation logic with inputs that would never reach production through normal paths.

**How to test it manually:**
```bash
cd backend
uvicorn app.main:app --reload

# Step 1: get signals from the baseline extractor
curl http://localhost:8000/rubrics/sample > rubric.json
curl http://localhost:8000/debriefs/sample | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d[0]))" > debrief.json

# Step 2: POST /extract/baseline, save the signals

# Step 3: POST /verify/evidence with the signals + the debrief
# Use /docs Swagger UI — it's easier to compose nested JSON there.
# Expected: is_valid=true, citation_validity_rate=1.0 for baseline-extracted signals.

# Run tests
python -m pytest app/tests/test_evidence_verifier.py -v
```

**What could fail in production:**
1. **Unicode character boundaries.** Python string indexing works on Unicode code points. If a debrief contains multi-byte characters (em-dashes, smart quotes, non-ASCII names) and the LLM returns offsets computed from byte positions (e.g., from a different tokenization), `start_char:end_char` indexing will be wrong. The verifier will catch this as `offset_mismatch`, but the underlying cause may need a byte-vs-character encoding fix at the ingestion layer.
2. **Debrief mutation.** If the stored debrief text differs from the text that was used during extraction (e.g., whitespace normalization on ingest), all spans will fail verification even if they were correct at extraction time. Store the text exactly as it was submitted.
3. **Large signal sets.** With 5 debriefs × 7 competencies × 3 extractors, the signal set can be large. The verifier is O(signals × spans) and very fast per span (just string operations), but watch for memory pressure if all signals are passed in one request. PROMPT 15's database persistence will help by keeping only relevant signals in memory.

---

## Milestone 8: Coverage Map Analyzer

**What changed:**  
Added `backend/app/services/coverage_analyzer.py` (`analyze_coverage`), `backend/app/routers/analyze.py` (`POST /analyze/coverage`), and `CoverageRequest`/`CoverageMapResponse` schemas. Added 17 tests in `backend/app/tests/test_coverage_analyzer.py`. Total test count: 165.

**Why designed this way:**  
**Four-state coverage model.** Rather than a binary "assessed/not assessed," coverage has four states — `STRONG` (≥2 interviewers, consistent direction), `PARTIAL` (only 1 interviewer), `CONFLICTED` (≥2 interviewers with opposing signals), and `NOT_COVERED` (no interviewer mentioned it). This communicates confidence, not just presence. A single interviewer saying a candidate is strong at SQL is very different from three interviewers independently agreeing.

**Separation of gap types.** `PARTIAL` and `NOT_COVERED` both appear as `coverage_gaps`. This lets the hiring committee know which competencies need follow-up questions (PARTIAL — one opinion is insufficient) vs. which were simply never discussed (NOT_COVERED — a panel process failure).

**Coverage is per-rubric, not just per-signal.** The analyzer iterates over every competency in the rubric, including ones with zero signals. This ensures no competency silently disappears from the report because no interviewer mentioned it.

**Engineering concept to understand:**  
**Aggregation with known categories.** A common LLM pipeline mistake is to summarize only what signals exist, silently omitting things that weren't mentioned. Here, the rubric defines the expected categories, and the coverage map is computed against that complete list — not just the signals that were extracted. This is the difference between "what was said" and "what should have been said."

**How to test it manually:**
```bash
cd backend
uvicorn app.main:app --reload

# POST /analyze/coverage with signals=[] and the sample rubric
# Expected: all competency_assessments have status=not_covered, overall_coverage_pct=0.0

# Run tests
python -m pytest app/tests/test_coverage_analyzer.py -v
```

**What could fail in production:**  
1. **Rubric drift.** If the rubric used at extraction time differs from the rubric used at coverage analysis time (e.g., a competency was renamed), signals will be assigned to competency IDs that don't exist in the rubric. They won't appear in the coverage map. Always use the same rubric object throughout a pipeline run.  
2. **Single-interviewer halo effect.** A single very positive interviewer will produce `PARTIAL` coverage across many competencies — which looks better than `NOT_COVERED` but still isn't sufficient. The UI must communicate that PARTIAL is a yellow flag, not a green one.

---

## Milestone 9: Disagreement Detector

**What changed:**  
Added `backend/app/services/disagreement_detector.py` (`detect_disagreements`), `POST /analyze/disagreements`, and `DisagreementsRequest`/`DisagreementsResponse` schemas. Added 13 tests in `backend/app/tests/test_disagreement_detector.py`. Total test count: 178.

**Why designed this way:**  
**Two distinct disagreement types.** `DIRECTION_CONFLICT` catches the most dangerous case: one interviewer says "strong" and another says "weak" on the same competency. `EVIDENCE_ABSENT` catches a subtler problem: a confident claim with no verifiable evidence span — the extractor assigned high confidence, but there's nothing to cite. Both are `HIGH` severity and must be surfaced before synthesis.

**Sorted by severity, not by occurrence.** The flags list is sorted `HIGH → MEDIUM → LOW`, not in the order signals were extracted. This ensures the reviewer sees the most critical issues first, regardless of which competency was processed last.

**Resolution suggestions are template-based, not LLM-generated.** The suggestion text ("Ask the hiring committee to discuss...") is written in code, not produced by an LLM. This ensures suggestions are consistent, auditable, and safe — they don't introduce new claims or analysis.

**Engineering concept to understand:**  
**Detecting inconsistency in structured data.** Disagreement detection is a classic data quality problem: for each group key (competency_id), check whether all members of the group agree. In a database you'd use `GROUP BY + HAVING COUNT(DISTINCT signal_type) > 1`. Here it's Python dict-based grouping. The pattern is identical. When LLM output is stored as structured records, SQL-style analytics become possible — this is one of the main benefits of schema-first design.

**How to test it manually:**
```bash
cd backend
python -m pytest app/tests/test_disagreement_detector.py -v

# Manual test: post two signals for the same competency,
# one POSITIVE (from Alice) and one NEGATIVE (from Bob).
# POST /analyze/disagreements — expect one DIRECTION_CONFLICT flag.
```

**What could fail in production:**  
1. **Many-interviewer averaging.** With 5 interviewers, 3 positive and 2 negative signals is a conflict but also a majority. The current implementation flags `DIRECTION_CONFLICT` whenever both POSITIVE and NEGATIVE appear, regardless of proportion. A production version might weight by confidence or add a "weak conflict" state for 3v1 cases.  
2. **Same interviewer, multiple signals.** If one interviewer produces both POSITIVE and NEGATIVE signals for the same competency (contradicting themselves), this is not currently detected. A `SELF_CONFLICT` type could be added.

---

## Milestone 10: Synthesis Report Generation

**What changed:**  
Added `backend/app/services/synthesizer.py` (`synthesize`, `_generate_executive_summary`), `backend/app/routers/synthesize.py` (`POST /synthesize` → 201), and `SynthesisRequest`/`SynthesisReport` schemas. Added 11 tests in `backend/app/tests/test_synthesizer.py`. Total test count: 189.

**Why designed this way:**  
**Verification is the first step of synthesis, not a prerequisite to call separately.** The synthesizer calls `verifier.verify()` internally and raises `HTTPException(422)` if `is_valid=False`. This means synthesis cannot be called with unverified signals — the hard gate is enforced at the code boundary, not by convention or documentation.

**Executive summary is template-based, not LLM-generated.** This is a deliberate, non-obvious choice. A template-based summary cannot introduce new claims, cannot hallucinate evidence, and cannot produce recommendation language. The summary describes what the data shows (coverage rate, signal counts, flag counts) without interpreting it. The hiring committee does the interpretation.

**No hire/no-hire fields in the schema.** `SynthesisReport` has no `recommendation`, `hire_decision`, `should_hire`, or equivalent field. This constraint is enforced at the schema level, not by convention. Adding such a field would require a schema change, which would be visible in code review.

**Engineering concept to understand:**  
**Orchestration as code.** The synthesizer calls four sub-operations in sequence: verify → coverage → disagreements → build_report. Each sub-operation is independently tested. The synthesizer test verifies that they're called correctly and that the result is assembled properly. This is the "orchestrator" pattern: one component owns the sequence, each step owns its logic. This is how production LLM pipelines are structured when reliability matters more than speed.

**How to test it manually:**
```bash
cd backend
python -m pytest app/tests/test_synthesizer.py -v

# Manual: POST /synthesize with valid signals (from baseline extractor + verifier).
# The response will have a report_id. Then GET /review/{report_id} to confirm it's stored.
```

**What could fail in production:**  
1. **Synthesis blocks on any invalid span.** A single hallucinated quote (text_not_found) stops the entire report. This is intentional but strict — if even one signal is bad, the whole pipeline needs re-extraction. Future improvement: allow synthesis to proceed with the invalid signals excluded, if the exclusion rate is below a threshold.  
2. **Empty executive summary for minimal data.** If signals=[] and debriefs=1, the template produces a valid but nearly empty summary. Add a minimum-signal warning to the report.

---

## Milestone 11: Frontend MVP

**What changed:**  
Built the complete Next.js 14 App Router frontend. Key files:
- `frontend/lib/api.ts` — typed API client for all backend endpoints
- `frontend/lib/types.ts` — TypeScript types mirroring all backend Pydantic schemas
- `frontend/app/page.tsx` — home page explaining the tool, pipeline, and design constraints
- `frontend/app/analyze/page.tsx` — 6-step analysis wizard (client component with React state)
- `frontend/app/reports/[id]/page.tsx` — report viewer (server component, fetches by report_id)
- `frontend/components/Navbar.tsx`, `SignalCard.tsx`, `CompetencyGrid.tsx`, `DisagreementList.tsx`, `SynthesisReportViewer.tsx`

**Why designed this way:**  
**Single wizard page with step-local state.** Rather than separate URLs for each pipeline step (which would require URL-based state management or a backend session), the wizard holds all intermediate results in React `useState`. The user can go back and re-run any step. This keeps routing simple (one page) without sacrificing the step-by-step UX.

**Server vs. client components.** The home page and report viewer are server components (no `'use client'`): they render on the server, have no interactivity, and benefit from server-side data fetching for the report page. The analyze wizard is a client component because it has user interactions and holds mutable state. This is the correct Next.js 14 App Router division: server for read/display, client for interactivity.

**`@/` path alias for imports.** `tsconfig.json` maps `@/*` to `./`, so `import { Navbar } from '@/components/Navbar'` works from any file in the project without `../../` path counting. Next.js resolves this at build time.

**Engineering concept to understand:**  
**Type-safe API clients.** `frontend/lib/api.ts` uses the TypeScript types from `frontend/lib/types.ts` for every request and response. If the backend changes a field name or type, the TypeScript compiler catches the mismatch at build time. This is a weaker version of schema-sharing (the types are manually kept in sync) — a stronger version would auto-generate TypeScript types from the FastAPI OpenAPI spec using `openapi-typescript` or similar.

**How to test it manually:**
```bash
# Terminal 1: start backend
cd backend && uvicorn app.main:app --reload

# Terminal 2: start frontend
cd frontend && npm run dev

# Open http://localhost:3000
# 1. Click "New Analysis"
# 2. Enter a candidate name, click "Load Sample Data"
# 3. Step through extraction → verification → analysis → synthesis → review
```

**What could fail in production:**  
1. **CORS.** The frontend calls `http://localhost:8000` in dev. In production, set `NEXT_PUBLIC_API_URL` to the backend's deployed URL and configure `CORS_ORIGINS` on the backend.  
2. **State loss on refresh.** Closing or refreshing the analyze page during a wizard run discards all intermediate results. For production, persist intermediate state to localStorage or to the backend.  
3. **No loading skeleton.** API calls show a spinner but no content placeholder. For slow connections (LLM calls can take 5–10s), add skeleton loaders.

---

## Milestone 12: Reviewer Edit/Approval Workflow

**What changed:**  
Added `ReviewUpdate` schema, `backend/app/routers/review.py` (`GET /review/{report_id}`, `PATCH /review/{report_id}`), and `store.update_report_review()`. Added 8 review-workflow tests to `backend/app/tests/test_synthesizer.py`. Total test count: 197. The review step in the frontend wizard (`Step 6`) calls these endpoints.

**Why designed this way:**  
**PATCH, not PUT.** `PATCH` allows partial updates — the reviewer can save notes without setting `reviewer_approved`, or approve without adding notes. `PUT` would require sending the complete report object on every edit, including all the synthesized data. PATCH is correct here because we're updating reviewer metadata only, not the full resource.

**`reviewed_at` set only on approval.** Saving notes without checking "I approve" does not set `reviewed_at`. This ensures the timestamp reflects actual human sign-off, not a draft note-taking session. A report with `reviewer_approved=False` should not be shared externally even if it has `final_reviewer_notes`.

**Human review is a required step by design.** The `SynthesisReport` schema always includes `reviewer_approved: bool = False` and `reviewer_name: str = ""`. A report straight from `/synthesize` is always in "pending review" state. The frontend enforces this by making Step 6 the only way to get a report out of the system. There is no "skip review" button.

**Engineering concept to understand:**  
**Idempotent PATCH operations.** Calling `PATCH /review/{id}` twice with the same body produces the same result both times. This is idempotency: the operation is safe to retry if the network fails after the server processes it but before the client receives the 200. The test `test_patch_is_idempotent` verifies this. Most write operations should be designed for idempotency when building systems that retry on failure.

**How to test it manually:**
```bash
cd backend
python -m pytest app/tests/test_synthesizer.py -v

# End-to-end:
# 1. POST /synthesize → get report_id
# 2. GET /review/{report_id} → confirm reviewer_approved=false
# 3. PATCH /review/{report_id} with reviewer_name + reviewer_approved=true
# 4. GET /review/{report_id} → confirm reviewed_at is set
```

**What could fail in production:**  
1. **No auth on PATCH.** Any caller can approve any report. In production, tie the review endpoint to an authenticated user identity and record who approved.  
2. **Double approval.** Calling PATCH with `reviewer_approved=True` twice silently succeeds — the second call overwrites `reviewed_at`. Consider rejecting re-approval or logging each approval event separately.  
3. **Reviewer notes lost on re-synthesis.** If someone re-runs `/synthesize` for the same candidate, a new `report_id` is generated. The old report's reviewer notes are on the old ID. The new report starts in "pending review" state. Link reports to a project/candidate record to avoid this confusion.

---

## Milestone 13: Evaluation Suite

**What changed:**  
Created `sample_data/gold/candidate_001_gold.json` (hand-labeled strengths, concerns, disagreements, coverage gaps for the synthetic candidate) and `backend/app/evals/run_eval.py` (six-metric eval runner). Added 7 tests in `backend/app/tests/test_eval_suite.py`. Total test count: 218. All six release gates pass.

**Why designed this way:**  
**Eval-before-deploy is a hard rule from the product brief.** A prior summarization pilot failed because it missed red flags. The eval suite measures exactly that: `omission_rate` checks that critical labeled concerns appear in the extracted signals. If the extractor gets worse, this metric fails CI.

**Metrics are tiered by consequence.** Citation validity (must be 100%) and omission rate (must be ≤10%) are the release gates — these prevent the two failure modes that motivated the project. Disagreement recall and coverage completeness are secondary: they matter but a small miss doesn't block a demo. This prioritization is explicit in the results table.

**Gold labels are synthetic but realistic.** The five debrief files have intentional variation: a 2/5 product judgment score, a SQL weakness, an explicit interviewer note that they didn't cover a competency. The gold labels encode what a careful human reader would flag. This is "evaluation-first data design" in practice.

**Engineering concept to understand:**  
**Release gates in CI.** The eval runner exits with code 1 if any metric fails. The CI job (`ci.yml`) runs the eval suite on every push. This means a code change that degrades extraction quality will fail CI before merging. The eval runner is not just a diagnostic tool — it's a guard rail.

**How to test it manually:**
```bash
cd backend
python -m app.evals.run_eval
# Expected: ALL PASS — meets release gates

python -m pytest app/tests/test_eval_suite.py -v
```

**What could fail in production:**  
1. **Gold labels age out.** If the extractor improves and starts catching signals the gold didn't anticipate, coverage completeness might show lower (false negatives in the gold). Re-label periodically.  
2. **Word-overlap faithfulness proxy is weak.** A more accurate faithfulness check would use an NLI model or an LLM judge. The proxy is good enough to catch catastrophic hallucinations; it won't catch subtle unfaithful paraphrases.

---

## Milestone 14: Privacy and Security Safeguards

**What changed:**  
Added `backend/app/security.py` with: `SecurityHeadersMiddleware` (X-Content-Type-Options, X-Frame-Options, Cache-Control: no-store), `scrub_pii_for_log()` (strips emails, phones, SSNs before logging), `validate_debrief_text()` (size limits), and `warn_if_no_api_key()` (startup warning). Wired `SecurityHeadersMiddleware` into `main.py`. Added 14 tests. Total test count: 232.

**Why designed this way:**  
**PII scrubbing is for logs only — never applied to stored text.** Applying scrubbing to debrief text before storage would corrupt character offsets, breaking the evidence verification system. The scrubber is called explicitly in logging paths. This distinction must be preserved if logging is later added to extraction or synthesis.

**Security headers have no performance cost.** Adding them in middleware means every response gets them automatically, including future endpoints. The `Cache-Control: no-store` header prevents sensitive report data from being cached in browser or proxy caches, which is important because reports contain real candidate information.

**Engineering concept to understand:**  
**Defense in depth for LLM applications.** LLM apps have unique security considerations: the model might be prompted to leak input data, candidates' raw debrief text is sensitive PII, and outputs might be cached where they shouldn't be. Standard API security (HTTPS, CORS, input validation) must be combined with LLM-specific concerns (prompt injection is possible if debrief text reaches the model, output logging must be PII-safe).

**How to test it manually:**
```bash
python -m pytest app/tests/test_security.py -v

# Check headers on a live server:
curl -I http://localhost:8000/health
# Look for: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Cache-Control: no-store
```

**What could fail in production:**  
1. **PII in structured fields.** The scrubber checks `claim` and `quoted_text` but not `interviewer_name` or `candidate_name`. These fields can contain real names. If logging includes full signal dicts, extend the scrubber to cover them.  
2. **No rate limiting.** A client can call `/synthesize` in a tight loop, sending expensive LLM requests. Add rate limiting per IP or per API key before production exposure.

---

## Milestone 15: Database Persistence

**What changed:**  
Added `backend/app/models/db_models.py` (SQLAlchemy 1.4 ORM models: `ProjectRow`, `DebriefRow`, `ReportRow`), `backend/app/database.py` (engine, `SessionLocal`, `init_db`, `db_session` context manager), `backend/app/services/db_store.py` (`DatabaseStore` implementing the same interface as `InMemoryStore`), and Alembic migrations. Called `init_db()` at startup in `main.py`. Added 14 tests for `DatabaseStore`. Total test count: 232.

**Why designed this way:**  
**Same interface, swappable backends.** `DatabaseStore` and `InMemoryStore` both have `create_project`, `get_report`, `update_report_review`, etc. Tests continue to use `InMemoryStore` via `app.dependency_overrides` — they're fast, isolated, and don't touch disk. The production server uses `DatabaseStore` initialized at startup. This is the **repository pattern**: the API layer doesn't know or care which store is active.

**Reports stored as JSON blobs.** Rather than decomposing `SynthesisReport` (15+ nested fields) into dozens of normalized tables, the full Pydantic model is serialized to `TEXT`. This keeps the migration simple, lets the schema evolve without database changes for non-key fields, and makes reads fast (one query, no JOINs). The tradeoff: you can't write SQL queries over report content. For a portfolio project and early production, this is acceptable.

**`flush()` before reading within a session.** SQLAlchemy 1.4 expires objects after `commit()`. All attribute access happens inside the session context (before `db_session()` exits) to avoid `DetachedInstanceError`.

**Engineering concept to understand:**  
**Database migrations as code.** Alembic generates a migration file (in `alembic/versions/`) that records the exact SQL to create or alter tables. Running `alembic upgrade head` applies all pending migrations in order. This means the database schema is version-controlled alongside the application code — a new developer can reproduce the exact schema by running one command. Never manually `ALTER TABLE` in a production database.

**How to test it manually:**
```bash
cd backend
make migrate        # alembic upgrade head
python -m pytest app/tests/test_db_store.py -v
```

**What could fail in production:**  
1. **SQLite write contention.** SQLite allows only one writer at a time. For concurrent requests, use PostgreSQL. Just change `DATABASE_URL` to `postgresql://...` — the SQLAlchemy code is dialect-agnostic.  
2. **Report JSON migration.** If `SynthesisReport` gains a required field in a future schema version, existing stored JSON won't have it. Add `Field(default=...)` to all new fields and handle the `ValidationError` on deserialization.  
3. **No connection pooling.** The current `create_engine` uses the default pool. Under load, configure `pool_size` and `max_overflow` for PostgreSQL.

---

## Milestone 16: Docker

**What changed:**  
Added `backend/Dockerfile` (Python 3.11 slim, non-root user, `uvicorn` CMD), `frontend/Dockerfile` (multi-stage: deps → builder → runner, `next/standalone` output), updated `docker-compose.yml` (healthcheck on backend, `depends_on` with `service_healthy`, named volume for SQLite). Added `output: 'standalone'` to `next.config.mjs`.

**Why designed this way:**  
**Multi-stage frontend build.** The `builder` stage installs all dev dependencies and compiles Next.js. The `runner` stage copies only the compiled output (`.next/standalone`, `.next/static`, `public`). The final image has no `node_modules`, no TypeScript sources, no dev tooling — it's ~3x smaller than a single-stage build.

**Non-root users in both containers.** Running as root inside a container is a security risk: if the container is compromised, the attacker has root on the host's filesystem mounts. Both Dockerfiles create a dedicated low-privilege user.

**Backend healthcheck enables ordered startup.** The frontend's `depends_on: service_healthy` means Docker waits for the backend to respond at `/health` before starting the frontend container. Without this, the frontend might start before the backend is ready and show connection errors.

**Engineering concept to understand:**  
**Docker layer caching.** `COPY pyproject.toml .` followed by `RUN pip install ...` is the first layer. This layer is only rebuilt when `pyproject.toml` changes — not when application code changes. Application code (`COPY . .`) comes after. This means a code change doesn't reinstall all Python packages; it only rebuilds the last layer. Order Dockerfile instructions from least-changing to most-changing.

**How to test it manually:**
```bash
docker compose up --build

# In another terminal:
curl http://localhost:8000/health
# Open http://localhost:3000
```

**What could fail in production:**  
1. **SQLite in a volume.** The `db_data` volume persists the SQLite file across restarts, but volume backups require manual `docker cp` or a separate backup container. Use a managed database (RDS, Supabase) in production.  
2. **`NEXT_PUBLIC_API_URL` is baked in at build time.** If the backend URL changes after the frontend image is built, rebuild the frontend image. For dynamic URLs, use a runtime proxy (nginx) instead.

---

## Milestone 17: Developer Quality Workflow

**What changed:**  
Added `Makefile` (12 targets: `dev-backend`, `dev-frontend`, `test`, `lint`, `typecheck`, `eval`, `migrate`, `docker-up`, `docker-down`, `clean`), `.github/workflows/ci.yml` (two jobs: backend tests+lint+eval, frontend typecheck+build). The `.env.example` was already present from Milestone 4.

**Why designed this way:**  
**Makefile as the single entry point.** A new contributor runs `make test` without knowing the project's Python package manager, virtual environment path, or pytest flags. The Makefile encodes the correct invocations so they don't have to. This is especially useful in projects with both a Python backend and a Node.js frontend — otherwise each contributor remembers different commands.

**CI runs the eval suite, not just tests.** Many projects separate "tests" (fast, in-memory, no IO) from "evals" (slower, touches disk, measures quality metrics). Running the eval suite in CI means a regression in extraction quality fails the build before merging, not after deployment. The 7 eval tests run in under a second because they use the fast baseline extractor.

**Engineering concept to understand:**  
**CI as a collaboration protocol.** CI is not just about catching bugs — it's a shared contract between contributors. When the CI pipeline is well-defined, a developer can merge with confidence that the test suite, linter, type checker, and eval suite all passed. Without CI, "it works on my machine" is the best guarantee. With CI, every merge is validated against the same environment.

**How to test it manually:**
```bash
make test       # should show 232 passed
make lint       # should show no issues
make typecheck  # should show no errors
make eval       # should show ALL PASS
```

**What could fail in production:**  
1. **Ruff version skew.** If the CI pinned version differs from the dev machine version, linting rules may differ. Pin ruff in `pyproject.toml` and update explicitly.  
2. **CI does not test Docker.** The CI pipeline runs tests natively, not inside Docker. If the Dockerfile has a bug, it won't be caught until `docker compose up`. Add a `docker build` step to CI to catch this early.

---

## Milestone 18: Portfolio Documentation

**What changed:**  
Rewrote `README.md` with: skills table linking features to implementations, architecture diagram with key decision notes, full test count breakdown by layer, non-negotiable constraints documented with enforcement mechanisms, and quick-start instructions for both local and Docker modes.

**Why designed this way:**  
**README as a technical portfolio artifact.** A hiring manager or technical interviewer will read the README before cloning the repo. The skills table connects each engineering decision to a real implementation detail (e.g., "Python computes offsets, not Claude") so the reader can see the reasoning without reading source files. The constraints table shows that product guardrails are enforced in code, not just stated in documentation.

**Engineering concept to understand:**  
**Documentation as design accountability.** Writing down the non-negotiable constraints in the README creates a public commitment. If a future change weakens the citation verification gate or adds a hire recommendation field, the README becomes false. This tension is useful — it makes regressions visible. The best documentation is not a description of the system, but a description of the invariants the system must maintain.

**What could fail in production:**  
Documentation that doesn't match code erodes trust faster than no documentation. Treat the README as a living document and update it when the architecture changes, not after.

<!-- Future milestones will be appended below -->
