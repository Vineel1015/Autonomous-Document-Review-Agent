# AI Document Review Agent

## The problem this solves

You're doing due diligence on a company. Somewhere in a 150-page 10-K is the
one sentence that matters — a restatement buried under "Legal Proceedings"
instead of in the accounting notes where it belongs, a risk factor section
that's suspiciously thin for a company this size, a margin that moved in a
direction the rest of the filing doesn't explain. Reading closely enough to
catch that, across every filing for every company you're tracking, doesn't
scale. Skimming risks missing exactly the thing that mattered.

The usual fix — "just have an LLM summarize it" — trades one risk for
another. A model that quietly hallucinates a number, or flags something based
on what it *remembers* about a company rather than what's actually in front
of it, is worse than no automation at all when the output feeds an investment
decision. And a black-box summary with no record of who signed off on what
isn't something you can stand behind later.

This project is built for that middle ground: an agent that does the reading
— extracting the numbers into a structured, comparable shape and flagging
what looks off — but **stops and asks a human** before anything consequential
gets treated as final, and **writes down every decision** so there's a real
record afterward. It's a public rebuild of a pattern from validated,
regulated environments (pharma, finance, anywhere "who approved this and
why" is a question that gets asked), applied here to investment research: 10-Ks
and 10-Qs in, structured findings and an audit trail out. What used to be an
analyst reading a full filing end to end becomes reading the two or three
findings the agent actually flagged — the rest of the filing, extracted and
searchable, is just there when you need to check something.

## How this got built

The interesting parts of this build weren't the happy path.

**The environment fought back first.** Postgres was already broken before
any application code existed — a native Windows install missing most of its
own binaries, almost certainly antivirus quarantine. The fix wasn't repairing
it; it was recognizing that the project needed pgvector anyway, and Docker
gets you there in one line instead of compiling from source on Windows.
Getting Docker itself running took its own detour through a per-user install
that wasn't on any PATH, a credential helper that broke even anonymous image
pulls, and a close look at whether OneDrive's folder sync was about to eat a
multi-gigabyte WSL2 disk image (it wasn't, but it was worth checking before
it became a real problem instead of a hypothetical one).

**The schema started generic and got reshaped once the real domain showed
up.** A first pass had one flat `findings` table for everything. Once the
project's actual purpose — financial filings, compared across companies —
was clear, that stopped being enough: a risk-factor paragraph and a revenue
figure aren't the same shape. Findings need a citation and a severity;
numbers need a value, a unit, and a period to be queryable as a trend. Split
into two tables, and "show me this company's margin over the last four
quarters" turns into an `ORDER BY`, instead of a script that parses numbers
back out of sentences.

**The extraction prompts lied twice, in two different ways worth knowing
about.** The first time, the model flagged an "anomaly" by comparing a filing
against what it remembered about the real company from training — not
against anything actually in the document. Ungrounded, and dangerous for
exactly the kind of finding this tool exists to catch. Fixed with an explicit
constraint: ground every finding in the filing's own internal consistency,
never in memorized outside knowledge.

The second time was subtler and took longer to actually close. A table
headed "in millions" would get labeled correctly for three line items and
incorrectly for a fourth — same table, same scale, one wrong unit tag. Two
rounds of prompting (a rule, then a worked example) cut the error rate but
never fully closed it — LLM output isn't deterministic, and a prompt can
lower the odds of a mistake without guaranteeing it away. The real fix was a
small piece of code that cross-checks a batch of extracted numbers against
each other and corrects an outlier's *label*. The near-miss worth mentioning:
the first version of that fix did unit *conversion* instead of relabeling —
which would have taken a correct number and silently divided it by a
million, a worse bug than the one it was supposed to fix. Caught by tracing
through what the digits actually meant before it ever touched real data. The
lesson that shaped the rest of the project: prompting reduces an error rate;
it doesn't guarantee correctness. Anything that matters needs a real check
behind it, not just a well-worded instruction.

**The human-in-the-loop pause needed to be real, not simulated.** LangGraph's
`interrupt()` checkpoints an entire run to Postgres and halts it — proven by
starting a review in one process, letting it pause, killing that process
completely, and resuming the exact same run from a *different* process
using nothing but the paused run's ID. If the whole thing were an in-memory
wait, that would have been impossible. Getting there on Windows meant one
more real bug: the Postgres checkpointer's driver can't run under Windows'
default event loop, and the obvious fix — setting the event loop policy
before starting the server — silently didn't work, because the web server
resolves its own event loop internally before that fix ever gets a chance to
run. The actual fix meant reading the server's own source to find the one
parameter that lets the app hand it the correct loop directly.

**Every LLM call got instrumented for tracing, and verified against the
tracing tool's own API** — not just "no errors locally," but querying the
trace back afterward and confirming the token counts and auto-computed cost
matched the model's real pricing exactly.

**The frontend caught its own bug the same day it was built.** A decision
panel's expand animation looked fine in code and was actually clipping the
form fields it was supposed to reveal — found by actually driving a browser
through the real approve/reject flow against a live filing, not by reading
the component and assuming it was fine.

## Architecture

```mermaid
flowchart TD
    subgraph Client["Browser"]
        UI["React frontend (Vite)"]
    end

    subgraph Server["FastAPI backend"]
        API["REST API — documents / reviews / companies / metrics"]
        BG["Background task runner"]
    end

    subgraph Graph["LangGraph review pipeline"]
        LC["load_context"]
        EM["extract_metrics"]
        EF["extract_findings"]
        PE["persist_extraction"]
        RG["review_gate — interrupt() pauses here"]
        FZ["finalize"]
        LC --> EM
        LC --> EF
        EM --> PE
        EF --> PE
        PE --> RG --> FZ
    end

    subgraph External["External services"]
        Claude["Claude Opus 5 (Anthropic API)"]
        Langfuse["Langfuse — tracing"]
    end

    subgraph DB["Postgres + pgvector"]
        Tables[("documents · companies · findings · financial_metrics · audit_log")]
        Checkpoints[("checkpoints — paused LangGraph state")]
    end

    UI -- "submit filing / poll status / read findings / approve or reject" --> API
    API -- "202 Accepted, immediately" --> UI
    API -- "kicks off in the background" --> BG
    BG -- "graph.ainvoke(...)" --> LC
    EM -- "structured output call" --> Claude
    EF -- "structured output call" --> Claude
    EM -- "trace span" --> Langfuse
    EF -- "trace span" --> Langfuse
    PE -- "write metrics + findings" --> Tables
    RG -- "checkpoint state, pause" --> Checkpoints
    FZ -- "status + decision" --> Tables
    API -- "Command(resume=...) on decision" --> RG
    RG -- "reload on resume" --> Checkpoints
```

A filing comes in through the frontend or a direct API call and returns
immediately — the actual review runs in the background so nothing blocks on
the LLM. Extraction is two independent Claude calls running concurrently
(quantitative metrics, qualitative findings), each traced to Langfuse as it
happens. Everything gets written to Postgres as soon as it exists, so a
reviewer can see pending findings *while* a run is paused, not only after.
If anything needs a human decision, the graph's state — not just a status
flag — is checkpointed to Postgres and the run genuinely stops; a decision
made hours or days later, from anywhere, resumes that exact run. `audit_log`
is the permanent compliance record of who decided what; Langfuse is the
separate, dev-facing record of what the model actually saw and said.

## Getting started

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

**3. Install backend dependencies** ([uv](https://docs.astral.sh/uv/)):

```bash
uv sync
```

**4. Run the backend:**

```bash
python main.py
```

> **Windows note:** run `python main.py` directly — **not** `uvicorn main:app`
> or `fastapi dev`. Both resolve their own event loop before this module is
> ever imported, and the Postgres checkpointer's driver can't run under
> Windows' default event loop by the time that happens. `main.py` hands the
> server the correct loop directly; only running it as a script gets that in
> early enough.

**5. Run the frontend** (separate terminal):

```bash
cd frontend
npm install
npm run dev
```

Frontend at `http://localhost:5173`, backend at `http://127.0.0.1:8000`
(interactive API docs at `/docs`).

## Using it

| Endpoint | Purpose |
|---|---|
| `POST /documents` | Submit a filing (`ticker`, `filing_type`, `fiscal_year`, `fiscal_period`, `period_end_date`, file). Returns immediately; review runs in the background. |
| `GET /documents` | List filings, with optional `status` / `ticker` / `filing_type` filters. |
| `GET /documents/{id}` | Poll status: `processing` → `awaiting_approval` → `complete` / `rejected` / `failed`. |
| `GET /reviews/{id}/findings` | See findings — including pending ones, visible while a run is paused. |
| `POST /reviews/{id}/decision` | `{"decision": "approve" \| "reject", "reason": ..., "reviewer": ...}` — resumes a paused run. `409` if the document isn't actually paused. |
| `GET /companies` | List tracked companies. |
| `GET /companies/{ticker}/metrics` | One company's metrics over time (quarter/year-over-year trend). |
| `GET /metrics/compare?metric_name=...&tickers=A,B` | Same metric across companies — peer comparison. |

**A typical walkthrough:** upload a 10-K through the frontend's "Upload
Filing" page (or `POST /documents` directly) — you're back on the document's
page immediately, watching its status poll from *processing* toward a
result, no manual refresh needed. If nothing in the filing needed a second
look, it lands on *complete* with its extracted metrics and findings ready
to read. If something did — a restatement, a missing disclosure, a number
that doesn't reconcile with the rest of the filing — the run stops at
*awaiting_approval* and the findings that triggered it are marked clearly.
Read them, then approve or reject with a reason; that decision resumes the
run and writes a permanent row to the audit trail. Come back later and the
company's extracted metrics are already there for a trend view or a
side-by-side comparison against another ticker — no re-reading required.

## Project layout

```
app/
├── main.py               FastAPI app + lifespan (DB pool, LangGraph checkpointer)
├── config.py               Settings (pydantic-settings, reads .env)
├── db.py                    asyncpg pool + FastAPI dependency
├── models/
│   ├── schemas.py           DB-facing Pydantic models
│   └── extraction.py        LLM structured-output models
├── routers/                  documents / reviews / companies / metrics
└── graph/
    ├── agent.py               the LangGraph pipeline
    ├── extraction.py          the two Claude Opus 5 calls
    ├── persist.py              shared Postgres writes
    ├── checkpointer.py         Postgres checkpointer lifecycle
    ├── tracing.py               Langfuse instrumentation
    └── state.py                 graph state shape
frontend/                        React + TypeScript + Vite reviewer UI
db/init/                         schema, applied automatically on first container init
scripts/                          CLI entry points for driving a review directly
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
