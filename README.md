# Evidence-Grounded Interview Feedback Copilot

A full-stack AI tool that helps hiring teams synthesize interview debriefs into structured, evidence-grounded reports — without making hire/no-hire decisions.

> **Design principle:** The tool surfaces and structures evidence. The human decides.

**232 tests · TypeScript clean · eval suite passing · Dockerized · GitHub Actions CI**

---

## What This Demonstrates

Built as a portfolio project to show forward-deployed AI engineering skills:

| Skill | Implementation |
|-------|---------------|
| Structured LLM output | Claude `tool_use` with forced tool calling; Python computes character offsets from verbatim quotes |
| Pydantic-gated pipelines | Every LLM response is validated before use; `HTTPException(422)` on failure |
| Evidence grounding | Each claim carries `start_char/end_char` into the original text; verified by `EvidenceVerifier` before synthesis |
| Human-in-the-loop | `SynthesisReport` starts `reviewer_approved=False`; reviewer PATCH required before sharing |
| Eval suite | Six metrics from the eval plan, measured against gold-labeled synthetic data; release-gated |
| Security | PII scrubbing for logs, security headers middleware, request size limits, env-var-only secrets |
| Persistence | SQLite via SQLAlchemy 1.4 + Alembic migrations; same interface as in-memory store for tests |
| Deployment | Multi-stage Docker builds, `docker compose` orchestration, GitHub Actions CI |

---

## What This Does

Hiring managers reviewing many candidates face recurring problems:
- Key concerns are buried in long-form narratives
- Interviewer disagreements are hard to spot across separate documents
- The first debrief read anchors all subsequent interpretations

This tool solves them by:
1. **Extracting structured signals** from each debrief, grounded in verbatim quotes
2. **Verifying every citation** — `quoted_text` must exist at the stated `[start:end]` position
3. **Mapping evidence to competencies** from the role rubric
4. **Flagging disagreements** between interviewers on the same competency
5. **Identifying coverage gaps** — competencies no one assessed
6. **Generating a reviewable synthesis** for the hiring committee

What it deliberately does **not** do: score candidates, rank candidates, or recommend hire/no-hire.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- (Optional) Docker + Docker Compose

### Local Development

```bash
# Clone the repo
git clone <repo-url>
cd interview-feedback-copilot

# Set up environment
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env for LLM extraction (optional)

# Backend
cd backend
pip install -e ".[dev]"
alembic upgrade head        # create SQLite tables
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, click **New Analysis**, load sample data, and step through the pipeline.

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs

### With Docker

```bash
docker compose up --build
```

### Common Commands (via Makefile)

```bash
make test          # run 232 backend tests
make lint          # ruff check + format check
make typecheck     # tsc --noEmit (frontend)
make eval          # eval suite against gold data
make migrate       # alembic upgrade head
make docker-up     # docker compose up --build
```

---

## Architecture

```
Upload debriefs + role rubric
          ↓
  Baseline extraction (deterministic, no API key)
  LLM extraction (Claude tool_use, verbatim quotes)
          ↓
  Evidence Verifier (100% citation validity gate)
          ↓
  Coverage Map (STRONG / PARTIAL / NOT_COVERED / CONFLICTED)
  Disagreement Detector (DIRECTION_CONFLICT / EVIDENCE_ABSENT)
          ↓
  Synthesis Report (no recommendation language)
          ↓
  Human Reviewer (required PATCH before sharing)
```

### Key technical decisions

**Python computes offsets, not Claude.** Instead of asking the LLM for `start_char/end_char` (unreliable), we ask for verbatim quotes and use `str.find()`. Accuracy is deterministic regardless of which model is used.

**Verification is a hard gate.** Any signal with a span that can't be located in the debrief fails validation. The synthesizer raises `HTTP 422` rather than producing an unverified report.

**Schema-first design.** Pydantic models are the source of truth. Frontend TypeScript types mirror them manually (could be auto-generated from the OpenAPI spec in a production system).

**In-memory store for tests, SQLite for production.** `InMemoryStore` and `DatabaseStore` implement the same interface. Tests use `app.dependency_overrides` to inject the in-memory version without hitting disk.

---

## Project Structure

```
interview-feedback-copilot/
├── backend/
│   ├── app/
│   │   ├── schemas/          Pydantic models — source of truth
│   │   ├── services/         Business logic (extractor, verifier, analyzer, synthesizer)
│   │   ├── routers/          HTTP handlers (thin, delegates to services)
│   │   ├── models/           SQLAlchemy ORM models
│   │   ├── evals/            Evaluation suite
│   │   └── tests/            232 pytest tests
│   ├── alembic/              Database migrations
│   └── Dockerfile
├── frontend/
│   ├── app/                  Next.js App Router pages
│   ├── components/           UI components (SignalCard, CompetencyGrid, etc.)
│   ├── lib/                  Typed API client, TypeScript types
│   └── Dockerfile
├── sample_data/
│   ├── debriefs/             5 synthetic interview debriefs
│   ├── rubrics/              Data Scientist role rubric
│   └── gold/                 Gold-labeled eval dataset
├── docs/                     Product brief, architecture, decisions, eval plan, learning log
├── .github/workflows/ci.yml  GitHub Actions CI
├── docker-compose.yml
├── Makefile
└── CLAUDE.md                 AI pair-programmer operating rules
```

---

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/product_brief.md`](docs/product_brief.md) | Problem, users, goals, non-goals |
| [`docs/architecture.md`](docs/architecture.md) | System design, data flow, technology choices |
| [`docs/decisions.md`](docs/decisions.md) | Architecture decision records |
| [`docs/eval_plan.md`](docs/eval_plan.md) | Evaluation metrics and release gates |
| [`docs/learning_log.md`](docs/learning_log.md) | Engineering learning notes for each milestone |
| [`CLAUDE.md`](CLAUDE.md) | AI pair-programmer operating rules |

---

## Non-Negotiable Design Constraints

All enforced in code, not just documentation:

1. **No hire/no-hire recommendation** — `SynthesisReport` has no such field; a schema change would surface in code review
2. **Every claim cites source text** — `EvidenceVerifier` blocks synthesis on any invalid span
3. **Human review required** — reports start `reviewer_approved=False`; no "skip" path exists
4. **PII-aware logging** — `scrub_pii_for_log()` strips emails, phones, SSNs before any LLM logging
5. **API keys in env only** — enforced by `.gitignore` + startup warning if key is missing

---

## Test Coverage

| Layer | Tests | What's covered |
|-------|-------|----------------|
| Pydantic schemas | 18 | Validation, field constraints |
| API endpoints | 29 | HTTP contracts, status codes |
| Baseline extractor | 37 | Offset accuracy, signal classification |
| LLM extractor | 38 | Mock client, quote location, validation gate |
| Evidence verifier | 26 | Span verification, adversarial inputs |
| Coverage analyzer | 17 | Four coverage states, gap detection |
| Disagreement detector | 13 | Direction conflict, evidence absent |
| Synthesizer + review | 19 | End-to-end pipeline, reviewer workflow |
| Eval suite | 7 | Gold-label metrics, release gates |
| Security | 14 | PII scrubbing, security headers, input limits |
| DatabaseStore | 14 | SQLite persistence, session isolation |
| **Total** | **232** | |

---

## Status

All 18 milestones complete. Built incrementally with an AI pair-programmer following the rules in `CLAUDE.md`.

## Authorship / Build Process

This project was designed, scoped, and reviewed by Hsuan “Jimmy” Lo as a portfolio prototype. I used Claude Code as an AI coding assistant for implementation support, debugging, refactoring, and documentation drafts. The core product framing, workflow design, evaluation logic, human-in-the-loop safeguards, and hiring-process analysis are my own.
