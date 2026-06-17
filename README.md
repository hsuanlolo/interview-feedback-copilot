# Evidence-Grounded Interview Feedback Copilot

A full-stack AI tool that helps hiring teams synthesize interview debriefs into structured, evidence-grounded reports — without making hire/no-hire decisions.

> **Design principle:** The tool surfaces and structures evidence. The human decides.

---

## What This Does

Hiring managers reviewing 10–15 candidates each face the same problems:
- Key concerns are buried in uneven, long-form narratives
- Interviewer disagreements surface too late to resolve
- The first debrief read anchors how all subsequent debriefs are interpreted

This tool solves those problems by:
1. **Extracting structured evidence** from each debrief (skill, signal type, cited text)
2. **Mapping evidence to role competencies** from the rubric
3. **Flagging disagreements** between interviewers on the same skill
4. **Showing coverage gaps** — required competencies no one assessed
5. **Generating a human-reviewable synthesis** with inline citations

What it does **not** do: score candidates, rank candidates, or recommend hire/no-hire.

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- (Optional) Docker + Docker Compose

### Local Development

```bash
# Clone the repo
git clone <repo-url>
cd interview-feedback-copilot

# Set up environment variables
cp .env.example .env
# Edit .env and add your API key if using real LLM extraction

# Backend
cd backend
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev
```

App runs at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### With Docker

```bash
docker compose up --build
```

---

## Project Structure

```
interview-feedback-copilot/
├── backend/                  FastAPI backend
│   └── app/
│       ├── schemas/          Pydantic data models (source of truth)
│       ├── services/         Business logic (extraction, coverage, synthesis)
│       ├── routers/          HTTP route handlers
│       ├── evals/            Evaluation scripts
│       └── tests/            pytest tests
├── frontend/                 Next.js frontend
│   ├── app/                  App Router pages
│   ├── components/           Reusable UI components
│   └── lib/                  API client, types, utilities
├── sample_data/              Synthetic debriefs, rubrics, gold labels
├── docs/                     Product, architecture, learning notes
└── docker-compose.yml
```

---

## Architecture Overview

```
Upload debriefs + rubric
        ↓
  Ingestion & normalization
        ↓
  LLM extraction (with Pydantic validation)
        ↓
  Evidence verification (citation check)
        ↓
  Coverage map + disagreement detection
        ↓
  Synthesis report generation
        ↓
  Human reviewer edits & approves
        ↓
  Export (JSON / Markdown)
```

See `docs/architecture.md` for full system design.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [`docs/product_brief.md`](docs/product_brief.md) | Problem, users, goals, non-goals |
| [`docs/architecture.md`](docs/architecture.md) | System design, data flow, technology choices |
| [`docs/decisions.md`](docs/decisions.md) | Architecture decision records |
| [`docs/eval_plan.md`](docs/eval_plan.md) | Evaluation metrics and release gating |
| [`docs/learning_log.md`](docs/learning_log.md) | Engineering learning notes by milestone |
| [`CLAUDE.md`](CLAUDE.md) | AI pair programmer operating rules |

---

## Important Constraints

- **No hire/no-hire recommendation** — deliberate design boundary
- **All claims cite source text** — traceability is the core guarantee
- **Human review is required** — tool assists, does not decide
- **PII-aware** — uploaded text treated as sensitive

---

## Demo Mode

Run without an API key using the deterministic baseline extractor:

```bash
POST /extract/baseline  # No API key required
```

For LLM extraction, set `ANTHROPIC_API_KEY` in `.env`.

---

## Status

This is a portfolio project demonstrating forward-deployed AI engineering skills:
workflow discovery · structured extraction · RAG-style rubric grounding · human-in-the-loop review · evaluation · auditability · deployment readiness
