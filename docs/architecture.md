# Architecture — Evidence-Grounded Interview Feedback Copilot

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│  Upload → Rubric → Extraction → Coverage → Disagreements →       │
│  Synthesis → Human Review → Export                               │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP / JSON
┌───────────────────────────▼─────────────────────────────────────┐
│                        Backend (FastAPI)                         │
│                                                                   │
│  /extract/baseline  ──►  BaselineExtractor                       │
│  /extract/llm       ──►  LLMExtractor ──► LLMClient              │
│  /verify/evidence   ──►  EvidenceVerifier                        │
│  /analyze/coverage  ──►  CoverageAnalyzer                        │
│  /analyze/disagreements ► DisagreementDetector                   │
│  /synthesize        ──►  SynthesisGenerator ──► LLMClient        │
│  /review/approve    ──►  ReviewService                           │
│                                                                   │
│  All inputs/outputs validated by Pydantic schemas                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │   Storage (SQLite → Postgres) │
              │   Projects, Signals, Reports  │
              └────────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │   LLM (Claude via Anthropic  │
              │   API) — optional, mock-able │
              └────────────────────────────┘
```

---

## Processing Pipeline

```
Input: debrief text files + role rubric JSON
           │
    ① Ingest & Normalize
       • Parse text
       • Map score scales (e.g. 1-5 vs. 1-10)
       • Prepare candidate packet
           │
    ② Extraction Layer (choose one)
       • Baseline: deterministic keyword extraction (no API key needed)
       • LLM: Claude structured-JSON extraction with tool/function calling
           │
    ③ Pydantic Validation Gate
       • Reject malformed extraction output
       • Require evidence spans on all claims
           │
    ④ Evidence Verification
       • Confirm quoted_text appears in source debrief
       • Confirm char offsets are correct
       • Flag unsupported or vague claims
           │
    ⑤ Analysis Layer
       • Coverage map (skill × interviewer matrix)
       • Disagreement detection (cross-interviewer conflicts)
           │
    ⑥ Synthesis Generation
       • LLM produces human-reviewable report
       • All claims cite verified evidence spans
       • No hire/no-hire recommendation
           │
    ⑦ Human Review
       • Reviewer edits synthesis
       • Reviewer marks evidence accepted/rejected
       • Reviewer adds final notes
           │
Output: Approved synthesis report (JSON + Markdown export)
```

---

## Technology Choices

### Backend: FastAPI
- **Why:** Fast, Python-native, excellent async support, automatic OpenAPI docs.
- **Alternative considered:** Flask — rejected because it requires more boilerplate for async and schema validation.
- **Pydantic v2:** Built into FastAPI. Provides data validation at every layer boundary.

### Frontend: Next.js 14 (App Router)
- **Why:** Full-stack capable, strong TypeScript support, easy Vercel deployment.
- **Styling:** Tailwind CSS — utility-first, no component library opinions.
- **Alternative considered:** Plain React SPA — rejected because App Router gives us SSR and easier routing.

### LLM: Anthropic Claude
- **Why:** Strong at structured extraction, tool use / function calling, long context for multi-debrief packets.
- **Abstraction layer:** `LLMClient` interface allows swapping to other providers or mocking in tests.
- **Key constraint:** API key is optional — the system must work in demo/baseline mode without it.

### Storage: SQLite → Postgres
- **Why SQLite first:** Zero-config for local development and portfolio demos.
- **Migration path:** SQLAlchemy abstracts the DB; swap the connection string for Postgres in production.

### Extraction Design
- **Structured JSON extraction** via LLM tool/function calling (not freeform prose).
- **Schema-first:** Pydantic models define the extraction schema; the prompt references that schema.
- **Validation gates LLM output:** Any output that fails Pydantic validation is surfaced as an error, not silently accepted.

---

## Key Data Flow: Evidence Traceability

Every `ExtractedSignal` carries:
- `claim`: the substantive takeaway
- `evidence_spans`: list of `EvidenceSpan` objects
  - `quoted_text`: exact substring from the debrief
  - `start_char`, `end_char`: character offsets into the source document
  - `source_debrief_id`: which debrief this span came from
  - `interviewer_name`: who wrote it

The `EvidenceVerifier` confirms `quoted_text` appears in the source document at the stated offsets before the synthesis is generated. This prevents hallucinated citations.

---

## Evaluation Architecture

```
Gold dataset (labeled by human expert)
           │
    eval/run_eval.py
           │
    ┌──────▼──────┐
    │ Faithfulness │ → share of claims entailed by their cited span
    │ Omission     │ → share of labeled red flags absent from synthesis
    │ Citation     │ → share of citations that resolve to real spans
    │ Disagreement │ → recall/precision on labeled conflicts
    │ Schema valid │ → 100% required before any release
    └─────────────┘
           │
    Metrics table printed to stdout
    Hard gates: schema validity 100%, omission rate ≤ 10%
```

---

## Security / Privacy Model

- Uploaded debriefs are treated as sensitive, untrusted input.
- PII redaction utility runs on upload (emails, phone numbers, addresses).
- Prompt injection detection: uploaded text checked for instruction-override attempts.
- Audit log captures every LLM API call (timestamp, model, prompt hash, token count).
- API keys: environment variables only. Never in code or version control.

---

## Deployment (Local → Cloud)

| Stage | Hosting | Notes |
|-------|---------|-------|
| Local dev | `uvicorn` + `next dev` | No Docker required |
| Demo / portfolio | Vercel (frontend) + Railway/Fly.io (backend) | Free tier available |
| Production | Docker Compose → Kubernetes | Backend stateless; DB on managed Postgres |

---

## What Is Not In Scope (v1)

- Real-time multi-user collaboration
- Authentication and authorization
- Multi-tenant data isolation
- Fine-tuned models
- Automated debrief fetching from ATS (Greenhouse, Lever, Workday)
