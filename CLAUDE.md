# CLAUDE.md — Operating Rules for This Project

This file governs how the AI pair programmer should behave in this repo.
Read this before every coding session.

---

## Project Identity

**Name:** Evidence-Grounded Interview Feedback Copilot
**Stack:** FastAPI (backend) · Next.js / TypeScript (frontend) · SQLite → Postgres (persistence)
**Purpose:** Help hiring teams synthesize interview debriefs — without making hire/no-hire recommendations.

---

## Non-Negotiable Design Rules

1. **No hire/no-hire recommendation.** The tool organizes evidence; humans decide.
2. **No candidate ranking.** No aggregate score across candidates.
3. **Every model-generated claim must cite a source span** from the original debrief text.
4. **Pydantic validation must gate all LLM output.** Invalid output is surfaced as an error, not silently accepted.
5. **Human review is a required step**, not an optional add-on.
6. **API keys live in environment variables only.** Never in code, never in docs.

---

## Working Rules for the AI Assistant

### Before Changing Files
- Inspect the current repo state (`ls`, `cat` key files) before proposing edits.
- State a clear plan before touching files.
- Keep each change small and independently testable.
- Ask a short clarification question if requirements are ambiguous.

### Code Quality
- Prefer readable code over clever code.
- No hardcoded secrets, API keys, or credentials — use `.env` / environment variables.
- Explain every new dependency before adding it (what it does, why we need it, any risks).
- Add tests for all core logic. Tests live in `backend/app/tests/`.
- Use type hints throughout Python code.
- Use TypeScript types throughout frontend code.

### Documentation
- After each implementation milestone, update `docs/learning_log.md` with:
  - What changed
  - Why it was designed that way
  - What engineering concept the user should understand
  - How to test it manually
  - What could fail in production
- Do not delete files without asking.
- Update `docs/decisions.md` when a non-obvious architecture decision is made.

### File Safety
- Do not delete files without explicit permission.
- Do not overwrite sample data or gold eval data.
- Do not push secrets to git.

---

## Project Conventions

### Python (Backend)
- Python 3.11+
- FastAPI for HTTP API
- Pydantic v2 for schemas and validation
- SQLAlchemy / SQLModel for ORM (when added)
- pytest for tests
- ruff for linting and formatting
- pyproject.toml for dependency management (uv or pip)

### TypeScript (Frontend)
- Next.js 14 App Router
- TypeScript strict mode
- Tailwind CSS for styling
- No UI library with heavy opinions — keep it clean and professional
- Fetch API for backend calls (no axios unless needed)

### Git
- Commit after each milestone
- Commit message format: `feat: <what>`, `fix: <what>`, `docs: <what>`, `test: <what>`
- Never commit `.env` files

---

## Folder Purposes (Quick Reference)

| Path | Purpose |
|------|---------|
| `backend/app/schemas/` | Pydantic models — data contracts for the entire system |
| `backend/app/services/` | Business logic (extraction, verification, coverage, synthesis) |
| `backend/app/routers/` | FastAPI route handlers — thin, delegates to services |
| `backend/app/evals/` | Evaluation scripts against gold-labeled datasets |
| `backend/app/tests/` | pytest unit and integration tests |
| `backend/app/models/` | SQLAlchemy ORM models (added in persistence milestone) |
| `frontend/app/` | Next.js App Router pages |
| `frontend/components/` | Reusable React components |
| `frontend/lib/` | API clients, type definitions, utilities |
| `sample_data/debriefs/` | Synthetic interview debrief text files |
| `sample_data/rubrics/` | Role rubric JSON files |
| `sample_data/gold/` | Gold-labeled eval datasets |
| `docs/` | Product, architecture, learning, and decision docs |

---

## Milestone Checklist (to track progress)

- [ ] PROMPT 0: Project documentation
- [ ] PROMPT 1: Repo structure
- [ ] PROMPT 2: Pydantic data models
- [ ] PROMPT 3: Sample data
- [x] PROMPT 4: FastAPI skeleton
- [x] PROMPT 5: Deterministic baseline extractor
- [x] PROMPT 6: LLM extraction interface
- [ ] PROMPT 7: Evidence verification
- [ ] PROMPT 8: Coverage map
- [ ] PROMPT 9: Disagreement detection
- [ ] PROMPT 10: Synthesis report generation
- [ ] PROMPT 11: Frontend MVP
- [ ] PROMPT 12: Reviewer edit/approval workflow
- [ ] PROMPT 13: Evaluation suite
- [ ] PROMPT 14: Privacy/security safeguards
- [ ] PROMPT 15: Database persistence
- [ ] PROMPT 16: Docker
- [ ] PROMPT 17: Developer quality workflow
- [ ] PROMPT 18: Portfolio documentation
