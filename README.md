# AI Document Review Agent

An agent that ingests SEC financial filings (10-K / 10-Q), extracts structured
findings against a schema, flags anomalies, **pauses for human approval on
consequential findings**, and **logs every decision**. Built for investment
due-diligence and trend analysis across companies — a public, open-source
version of the pattern used in validated/regulated environments, where
change control and audit trails are the point, not an afterthought.

## Stack

Python, FastAPI, LangGraph, Postgres + pgvector, Langfuse, Docker, Claude
Opus 5 (via the Anthropic SDK's structured outputs).

## How it works

```
POST /documents (ticker, filing_type, fiscal_year, fiscal_period + file)
        │
        ▼
   companies / documents rows written, 202 returned immediately
        │
        ▼ (background)
┌─────────────────────── LangGraph review pipeline ───────────────────────┐
│ load_context → [extract_metrics ∥ extract_findings] → persist_extraction │
│                                                              │            │
│                                                        review_gate        │
│                                                   (interrupt() here iff   │
│                                                    a finding needs a      │
│                                                    human sign-off)        │
│                                                              │            │
│                                                          finalize         │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  documents.status: processing → awaiting_approval → complete | rejected
```

- **Extraction** is two concurrent, independently-tunable Claude Opus 5 calls
  using structured outputs (`client.messages.parse`) — one for quantitative
  `financial_metrics` (revenue, margins, EPS...), one for qualitative
  `findings` (risk factors, legal proceedings, anomalies). Kept as separate
  calls and separate tables: a citation-and-severity finding and a
  value-unit-period metric aren't the same shape, and separating them keeps
  trend/comparison queries a plain `ORDER BY`/`WHERE` instead of parsing
  numbers back out of text.
- **The pause is real**, not a Python function sleeping. `interrupt()` inside
  the graph checkpoints the entire run to Postgres via a
  `langgraph-checkpoint-postgres` saver — the process can exit completely,
  and a *separate* process later resumes the exact same run with
  `Command(resume=...)`, keyed by `thread_id`.
- **Every LLM call is traced to Langfuse** — the actual prompt, Claude's raw
  output, token usage, and cost, per node, per run.
- **`audit_log` is the compliance record**, separate from Langfuse: who
  approved or rejected what, and why, permanently.

## API

| Endpoint | Purpose |
|---|---|
| `POST /documents` | Submit a filing (`ticker`, `filing_type`, `fiscal_year`, `fiscal_period`, `period_end_date`, file). Returns immediately; review runs in the background. |
| `GET /documents/{id}` | Poll status: `processing` → `awaiting_approval` → `complete` / `rejected` / `failed`. |
| `GET /reviews/{id}/findings` | See findings — including pending ones, visible while a run is paused. |
| `POST /reviews/{id}/decision` | `{"decision": "approve" \| "reject", "reason": ..., "reviewer": ...}` — resumes a paused run. `409` if the document isn't actually paused. |
| `GET /companies` | List tracked companies. |
| `GET /companies/{ticker}/metrics` | One company's metrics over time (quarter/year-over-year trend). |
| `GET /metrics/compare?metric_name=...&tickers=A,B` | Same metric across companies — peer comparison. |

Interactive docs at `/docs` once the app is running.

## Running it locally

**1. Start Postgres (pgvector-enabled) in Docker:**

```bash
docker compose up -d
```

**2. Configure environment** — copy `.env.example` to `.env` and fill in:

```
POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB   # match compose.yaml
DATABASE_URL                                       # postgresql://user:pass@localhost:5432/db
ANTHROPIC_API_KEY                                  # console.anthropic.com
ANTHROPIC_WORKSPACE_ID                              # only if using an identity-linked key
LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY           # optional — tracing no-ops without these
```

**3. Install dependencies** ([uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

**4. Run the app:**

```bash
python main.py
```

> **Windows note:** run `python main.py` directly — **not** `uvicorn main:app`
> or `fastapi dev`. Both of those resolve their own event loop before this
> module is ever imported, and psycopg's async mode (used by the LangGraph
> Postgres checkpointer) can't run under Windows' default `ProactorEventLoop`.
> `main.py` hands `uvicorn.run()` a `SelectorEventLoop` factory directly —
> only running it as a script gets that in before uvicorn's own internals
> fire. Full explanation in [`docs/DEVELOPMENT_HISTORY.md`](docs/DEVELOPMENT_HISTORY.md).

**Driving a review without the API** — useful for iterating on extraction
prompts directly:

```bash
uv run python scripts/run_review.py <document_id> <path/to/filing.txt>
uv run python scripts/approve_review.py <document_id> approve
```

## Project layout

```
app/
├── main.py            FastAPI app + lifespan (DB pool, LangGraph checkpointer)
├── config.py           Settings (pydantic-settings, reads .env)
├── db.py                asyncpg pool + FastAPI dependency
├── models/
│   ├── schemas.py       DB-facing Pydantic models
│   └── extraction.py    LLM structured-output models
├── routers/              documents / reviews / companies / metrics
└── graph/
    ├── agent.py           the LangGraph pipeline
    ├── extraction.py      the two Claude Opus 5 calls
    ├── persist.py          shared Postgres writes
    ├── checkpointer.py     Postgres checkpointer lifecycle
    ├── tracing.py           Langfuse instrumentation
    └── state.py             graph state shape
db/init/                  schema, applied automatically on first container init
scripts/                    CLI entry points for driving a review directly
docs/DEVELOPMENT_HISTORY.md  full build history — decisions, bugs, and why
```

## Known limitations

- No auth on any endpoint yet.
- Ingestion only handles plain UTF-8 text — a real EDGAR filing (HTML/PDF)
  needs a text-extraction step first.
- No direct EDGAR pull-by-ticker; filings are uploaded, not fetched.
- The FastAPI app itself isn't containerized yet (only Postgres is).
- `document_chunks` (pgvector) exists in the schema but is unused — filings
  fit whole inside Claude Opus 5's 1M-token context, so chunking wasn't
  needed for extraction; it would matter for a future retrieval/Q&A feature.

See [`docs/DEVELOPMENT_HISTORY.md`](docs/DEVELOPMENT_HISTORY.md) for the full
technical narrative — every architectural decision, every bug hit along the
way, and why each fix is shaped the way it is.
