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

<!-- Future milestones will be appended below -->
