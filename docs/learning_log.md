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

<!-- Future milestones will be appended below -->
