# Development History — AI Document Review Agent

A technical narrative of how this system was built: decisions, bugs, and why things are shaped the way they are. Written for interview prep and future-you.

## 1. What this is

A public, open-source version of a BMS-style internal tool: an agent that ingests **SEC financial filings (10-K/10-Q)**, extracts structured findings against a schema, flags anomalies, **pauses for human approval on consequential calls**, and **logs every decision** — for investment due-diligence and trend analysis.

Stack: **Python, FastAPI, LangGraph, Postgres + pgvector, Langfuse, Docker**, Claude Opus 5 via the raw Anthropic SDK.

---

## 2. Environment setup — the first real obstacle

Before any application code, the local Postgres install was broken: a native Windows PostgreSQL 18 install existed (`C:\Program Files\PostgreSQL\18`, `initdb` had run) but was **missing core binaries** — `pg_ctl.exe`, `initdb.exe`, `pg_config.exe`, and ~20 others gone from a 9-executable `bin\` folder that should have ~30. No Windows service was registered as a result. Most likely cause: antivirus quarantine of those specific binaries (a known false-positive pattern) or an interrupted installer.

**Decision: pivot to Docker rather than repair.** The project's own stack calls for `Postgres + pgvector`, and pgvector on native Windows Postgres means compiling from source or hunting a prebuilt DLL — much worse than `docker run pgvector/pgvector:pg18`. Repairing the native install would have just relocated the problem.

Getting Docker running had its own friction:
- **WSL2 confusion**: `wsl --status` printed *"WSL1 is not supported with your current machine configuration"* — this reads like an error but is purely informational (WSL1 isn't needed; `Default Version: 2` was already correct).
- **Docker Desktop installed per-user** under `%LOCALAPPDATA%\Programs\DockerDesktop`, not `Program Files` — so `docker` wasn't resolving via the expected path, and more importantly wasn't yet on **any** PATH.
- **PATH propagation**: added Docker's bin dir to the user's PATH (`[Environment]::SetEnvironmentVariable(...,"User")`), but this automation's own PowerShell tool doesn't persist environment variables between calls — each tool invocation starts from a snapshot taken at session start. Had to re-prime `$env:PATH` from the registry (`Machine` + `User`) at the top of every subsequent command needing `docker`.
- **`docker-credential-desktop` missing from PATH** caused image pulls to fail even for a public, unauthenticated image (`error getting credentials`) — fixed by the same PATH addition, since the credential helper binary lives alongside `docker.exe`.
- **OneDrive risk, caught before it caused damage**: Desktop/Documents were redirected into OneDrive (Known Folder Move) on this machine. Docker Desktop's WSL2 backend stores large, constantly-changing VHDX disk images — syncing those into OneDrive is a known source of corruption and sync storms. Verified Docker's actual install path stayed outside OneDrive before proceeding, and separately walked through disabling OneDrive's Desktop/Documents backup redirection.

---

## 3. Docker Compose / Postgres — real bugs in pre-existing files

The repo already had a `compose.yaml` (committed before this session) with several genuine YAML errors:
- `container-name:` — hyphen instead of underscore (not a valid Compose key)
- `environemnt:` — typo for `environment:`
- `ports:\n  -"5432:5432"` — missing space after `-`, which breaks YAML list-item parsing entirely (`services.db.ports must be a array` was the resulting Compose error)
- top-level `volumes:` used list syntax (`- postgres_data`) instead of the required map syntax (`postgres_data:`)
- plain `postgres:16-alpine` image — no pgvector

Also found `.env` using **YAML syntax** (`POSTGRES_USER: myuser`) instead of the **shell syntax** Compose actually requires (`POSTGRES_USER=myuser`) — Compose silently treated every variable as unset, substituting empty strings with no error. This is a nasty class of bug: no crash, just wrong values propagating quietly.

**Postgres 18 breaking change, hit live**: the `pgvector/pgvector:pg18` image refused to start, logging (accurately and helpfully) that images ≥18 expect their data volume mounted at `/var/lib/postgresql`, not the pre-18 convention of `/var/lib/postgresql/data`. Fixed the mount path, then had to `docker compose down -v` to discard the half-initialized volume from the failed attempt before a clean `up` would succeed.

---

## 4. Schema design — and why it changed shape mid-project

**Initial generic schema** (before the domain was specified as financial filings): `documents`, `findings`, `document_chunks` (pgvector), `audit_log`.

**Once the domain was clarified** (10-K/10-Q review for investment decisions, multi-company comparison required), the schema needed real rework:
- Added a `companies` table (`ticker` unique, `cik` for future EDGAR use, `name`)
- `documents` gained `company_id`, `filing_type`, `fiscal_year`, `fiscal_period`, `period_end_date`, `accession_number` (EDGAR-ready but unused today)
- `findings` gained `company_id` and `category` (risk_factor / legal_proceeding / accounting_policy / governance / anomaly / other)
- **New `financial_metrics` table**, deliberately *separate* from `findings`

**Why a separate metrics table is the key design decision here**: a risk-factor paragraph and a revenue figure have fundamentally different shapes. `findings` needs a citation and a severity score; a number needs a `value`/`unit`/`period` for time-series queries. Putting both in one generic table would mean parsing numbers back out of free text to answer "show AAPL's revenue over time" or "compare gross margin across AAPL and MSFT" — both of which become trivial `ORDER BY period_end_date` / `WHERE ticker = ANY(...)` queries against `financial_metrics` instead. A `UNIQUE (document_id, metric_name, period_type)` constraint makes re-extraction idempotent via `ON CONFLICT ... DO UPDATE`.

---

## 5. FastAPI application structure

```
app/
├── main.py            # FastAPI() + lifespan (DB pool + LangGraph checkpointer startup/shutdown)
├── config.py           # pydantic-settings — single source of truth for env vars
├── db.py                # asyncpg pool + get_db() FastAPI dependency
├── models/
│   ├── schemas.py       # DB-facing Pydantic models (Finding, FinancialMetric, DocumentOut...)
│   └── extraction.py    # LLM-output-only models (no id/timestamps — the model shouldn't invent those)
├── routers/
│   ├── documents.py     # ingestion, kicks off the graph in the background
│   ├── reviews.py        # findings + the approve/reject decision endpoint
│   ├── companies.py      # per-company trend queries
│   └── metrics.py         # cross-company peer comparison
└── graph/                # the LangGraph pipeline (below)
```

**Why two separate Pydantic model files** (`schemas.py` vs `extraction.py`): the LLM's structured-output schema and the DB row schema look similar but aren't identical — the LLM shouldn't be asked to produce a UUID primary key or a `created_at` timestamp. Keeping them separate means `app/graph/agent.py` explicitly maps LLM output → DB row, rather than the LLM's JSON schema silently depending on database internals.

**Dependency injection pattern**: `get_db()` acquires one connection from a shared `asyncpg.Pool` per request and yields it; FastAPI releases it back to the pool automatically when the request finishes. Background tasks (see below) can't reuse that connection — it's already released by the time a background task starts running — so they call `get_pool()` and acquire their own.

---

## 6. Extraction engine — structured outputs, not manual JSON parsing

`app/graph/extraction.py` makes **two separate LLM calls** per filing, run concurrently via `asyncio.gather`:
- `extract_metrics()` → `list[ExtractedMetric]` (revenue, margins, EPS, etc.)
- `extract_findings()` → `list[ExtractedFinding]` (risk factors, legal proceedings, anomalies)

Both use `client.messages.parse(model="claude-opus-5", output_format=PydanticModel)` — Claude's **structured outputs** feature, which validates the response against a Pydantic schema server-side and returns an already-parsed model instance (`response.parsed_output`). This eliminates a whole class of bugs (malformed JSON, wrong field names, type coercion) that manual `json.loads()` + validation would risk.

**Two calls instead of one combined call, deliberately**: metrics and findings have different shapes, land in different tables, and have independently-tunable prompts. Structured outputs also require exactly one top-level JSON object per call — a `list` isn't a valid top-level schema, hence `ExtractedMetrics{metrics: [...]}` / `ExtractedFindings{findings: [...]}` wrapper models.

**Why the raw Anthropic SDK, not `langchain_anthropic`** (which is installed but unused): direct control over `client.messages.parse()`'s structured-output contract, without going through LangChain's own `.with_structured_output()` abstraction layer whose exact interaction with Claude's newest structured-outputs feature was uncertain. This was a deliberate scope decision — get extraction correctness right first, decide later whether wrapping it in LangChain's abstractions is worth it.

---

## 7. Prompt-tuning war story #1 — the hallucination bug

First real extraction run against a synthetic AAPL 10-K excerpt: the model flagged an "anomaly" claiming *"the FY2025 net sales figure... matches Apple's previously reported FY2024 net sales, suggesting the comparative columns may be shifted or mislabeled."*

**The problem**: the model was cross-checking the filing against its own **memorized training knowledge** of real Apple financials — not against anything actually present in the document. For a compliance tool, this is dangerous: that memory could be stale, wrong, or (in this specific case) simply comparing against synthetic test data that was never real Apple data to begin with. A finding a human can't independently verify by re-reading the source document is a liability, not a feature.

**Fix**: added an explicit grounding constraint to the findings prompt — *"Ground every finding STRICTLY in this document's own internal consistency... Do NOT use your own outside/memorized knowledge of this company's actual historical financial results to judge whether a figure looks right."*

**Verified fixed**: re-ran extraction, confirmed that specific finding type stopped appearing, replaced by findings the model could actually cite from the document itself (e.g., cost of sales falling while revenue rose — an internal inconsistency, not an external comparison).

---

## 8. Prompt-tuning war story #2 — the unit-mislabeling bug (the deeper one)

The sample filing's income statement was headed `"(in millions, except per-share amounts)"`. The model would sometimes extract `revenue` with `unit="usd"` while correctly labeling `net_income`, `operating_income`, and `gross_profit` from the **same table** as `unit="usd_millions"`. Taken literally, that mislabeled row means "$391,035" instead of "$391,035 million" — off by 1,000,000×.

**Two rounds of prompting**:
1. A written rule: "find the table's reporting-scale header, apply it consistently to every value in that table."
2. A worked example with concrete numbers, since rules alone weren't reliable.

Both measurably helped but didn't eliminate the failure — reran the same prompt against the same input multiple times and got inconsistent results (roughly half correct, half not). **This is the core lesson of the whole project**: prompting reduces an error rate, it does not guarantee correctness. A financial tool needs a code-level check behind it.

**The fix — and a near-miss I caught before it shipped**: wrote `_normalize_dollar_units()` — cross-checks all dollar-denominated metrics in one extraction batch, and if one disagrees with the majority unit, corrects it. My **first version of this function did numeric unit conversion** (dividing the value by 1,000,000 to "convert" `usd` to `usd_millions`). Before ever running it against real data, I traced through the actual math by hand: the observed bug was the model copying the **correct, already-scaled digits** from the table but tagging them with the wrong unit label — not miscalculating the value. Applying a numeric conversion on top of that would have taken a **correct** number (391,035, meaning $391B) and **corrupted** it into 0.391035 — silently shrinking Apple's revenue by a factor of a million. Caught this by manually reasoning through what the digits actually represented before the code ever touched real data, and rewrote it as a **label-only correction**: relabel the unit, leave the value untouched, drop the confidence score, and append a visible note to the citation so a human reviewer can see a correction happened.

**Verified with real debugging, not assumption**: added temporary `stderr` print statements inside the function, ran the production script multiple times against real API calls to actually catch the safety net firing on a genuine mismatch (LLM non-determinism meant several runs landed on the "already consistent" no-op path before one caught a real 3-vs-1 split), confirmed the correction applied correctly, then removed the debug instrumentation.

---

## 9. LangGraph pipeline design

```
START → load_context
           │
   ┌───────┴───────┐
   │               │
extract_metrics  extract_findings      (run concurrently — LangGraph fan-out)
   │               │
   └───────┬───────┘
           │
    persist_extraction                 (fan-in: LangGraph runs this ONCE, only
           │                            after both parallel branches complete —
           │                            not once per predecessor)
      review_gate                      (interrupt() here iff any finding
           │                            has requires_approval=True)
        finalize                       (sets documents.status, writes the
           │                            human's decision to audit_log)
          END
```

**Why `persist_extraction` writes to Postgres *before* the interrupt, not after**: so a human reviewer can see the actual pending findings via `GET /reviews/{id}/findings` *while the run is paused*, not only after they've already approved something they couldn't see yet.

**The critical `interrupt()` semantic that shapes the whole node layout**: calling `interrupt()` raises a `GraphInterrupt` that pauses the run; on resume, LangGraph **re-executes the calling node's code from the top** (not the whole graph — just that one node). Any code before the `interrupt()` call within that same node therefore reruns on every resume. This is *why* `persist_extraction` is a separate node from `review_gate`, even though merging them might look cleaner: if the DB writes lived in the same node as the `interrupt()` call, they'd execute a second time on resume. `review_gate`'s pre-interrupt code is deliberately read-only (just filtering `state["findings"]` for `requires_approval` and building the payload) so replaying it is harmless.

**Resuming**: `graph.ainvoke(Command(resume=decision_dict), config={"configurable": {"thread_id": document_id}})` — no need to resupply the original input; the checkpointer reloads prior state from Postgres keyed by `thread_id`.

---

## 10. The Postgres checkpointer — three real bugs, in order

1. **`psycopg` has no `libpq` binding on Windows out of the box.** Plain `psycopg` failed with `ImportError: no pq wrapper available`. Fixed by installing the `psycopg[binary]` extra, which bundles a prebuilt `libpq` — no system PostgreSQL client install needed.

2. **Windows' default event loop is incompatible with psycopg's async mode.** `psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.` The obvious fix — `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` before starting — worked for standalone scripts but **silently failed for the FastAPI app run via `uvicorn main:app`**.

3. **Why the obvious fix didn't work under uvicorn — traced into uvicorn's actual source rather than guessing.** `uvicorn/loops/asyncio.py` explicitly returns `asyncio.ProactorEventLoop` on Windows (when not spawning subprocesses) and `uvicorn/server.py` passes that resolved factory directly to its own internal `asyncio.run(..., loop_factory=...)` — which **overrides whatever ambient policy is active**, since `loop_factory` takes precedence over the global policy. Setting the policy earlier in the same process does nothing once uvicorn's own `Server.run()` has already decided what factory to use.
   **The actual fix**: `uvicorn.run()`'s `loop=` parameter accepts *any* zero-argument callable, not just its named strings (`"asyncio"`/`"uvloop"`/`"auto"`) — confirmed by reading `uvicorn/importer.py`'s `import_from_string()`, which returns a non-string argument unchanged. So `main.py` now calls `uvicorn.run(app, loop=asyncio.SelectorEventLoop)` directly, passing the class itself.
   **Consequence**: `uvicorn main:app` (CLI) and `fastapi dev` **no longer work on this project on Windows** — the app must be started via `python main.py`, since only that path lets the process control loop construction *before* uvicorn's internals fire. Documented prominently in both `main.py`'s and `app/main.py`'s docstrings so this isn't a mystery next time.

4. **Checkpoint serializer deprecation warning.** LangGraph's `JsonPlusSerializer` (msgpack-based) logged *"Deserializing unregistered type... this will be blocked in a future version"* for every custom Pydantic model/enum flowing through the graph's checkpointed state (`FilingContext`, `ExtractedMetric`, `MetricUnit`, etc.). Harmless today, but `LANGGRAPH_STRICT_MSGPACK` will turn this into a hard failure in a future LangGraph release. Fixed by explicitly passing an allowlist of the actual classes to `JsonPlusSerializer(allowed_msgpack_modules=[...])`, threaded through the checkpointer's construction — verified fixed by re-running and confirming the warnings disappeared.

---

## 11. Wiring the FastAPI endpoints to the graph

- **`POST /documents`**: reads the uploaded file into a plain string *before* returning the response (an `UploadFile`'s handle isn't safe to rely on after the response is sent), inserts the `documents`/`companies` rows, then hands off to `BackgroundTasks` so the client gets a `202` immediately instead of blocking on the LLM. The background task acquires its own DB connection from the shared pool — the request-scoped one is already released by the time it runs.
- **`POST /reviews/{id}/decision`** (renamed from the originally-stubbed `/approve`, since the same endpoint handles both outcomes via `ReviewDecision.decision: Literal["approve", "reject"]`): checks the document is actually `awaiting_approval` (**409 Conflict** otherwise — resuming a thread that was never interrupted, or was already resumed, is a race, not a no-op), then calls `graph.ainvoke(Command(resume=...), config)`.
- `ReviewDecision.decision` was tightened from a bare `str` to a `Literal["approve", "reject"]` specifically so a typo can't silently be interpreted as a rejection by the graph's `decision.get("decision") == "approve"` check.

---

## 12. Langfuse tracing

Langfuse's Python SDK is now on v4 — a full rewrite onto **OpenTelemetry**, with a completely different API surface (`start_as_current_observation()` context managers, `@observe` decorators) from the older explicit `.generation()`/`.span()` call style. Verified the current API against the installed package's actual source rather than relying on possibly-stale training knowledge of the SDK.

**Why manual instrumentation was necessary, not just a callback handler**: `langfuse.langchain.CallbackHandler` exists and would auto-trace anything going through LangChain's `Runnable`/callback system — but extraction calls the **raw Anthropic SDK directly**, not `langchain_anthropic.ChatAnthropic`, so there's no LangChain callback chain to piggyback on for the LLM calls themselves. Wrapped each `client.messages.parse()` call in `langfuse.start_as_current_observation(as_type="generation", model=..., input=..., model_parameters=...)`, then `.update(output=..., usage_details=...)` after the response returns.

**`usage_details` key convention discovered by reading Langfuse's own source**, not guessed: `langfuse/langchain/CallbackHandler.py`'s `_parse_usage_model()` documents the exact expected keys (`"input"`, `"output"`, `"total"`) that Langfuse's cost engine matches against a model's pricing table.

**Safe-without-credentials by design**: the `Langfuse` client is explicitly constructed with `tracing_enabled=False` when no `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` are configured — verified this doesn't break the pipeline by running the full extraction → pause → resume flow both before and after real credentials were added.

**Verified success against Langfuse's own REST API**, not just "no errors locally": after adding real credentials, queried `client.api.trace.get(trace_id)` back and confirmed:
- One `review.start` trace containing exactly 3 observations: the top-level span plus two `generation` observations (`extract_metrics`, `extract_findings`)
- Correct model name (`claude-opus-5`) and accurate token counts on both
- **Langfuse's auto-computed cost matched Claude Opus 5's actual pricing exactly** ($5/$25 per 1M input/output tokens) — a strong, independently-checkable correctness signal, not just "the API call didn't throw."

---

## 13. Credential handling discipline

Followed a strict rule throughout: **never enter a credential (API key, password, token) into a file myself, even when the user pasted it directly into chat** — that's true even when explicitly asked. Every time (the Anthropic API key, the Langfuse keys), the user was walked through editing `.env` themselves. The one exception was the Anthropic **workspace ID** — not a secret, just an identifier — which was handled directly once provided.

One real credential-shaped bug along the way: the Anthropic key turned out to be an **"identity-linked" key** (tied to the user's Console account across multiple workspaces, rather than scoped to one workspace) — surfaced as `400 anthropic-workspace-id is required when authenticating with an identity-linked API key`. Diagnosed directly from the error message; fixed by passing `default_headers={"anthropic-workspace-id": ...}` on the `AsyncAnthropic` client constructor, sourced from a new optional `ANTHROPIC_WORKSPACE_ID` setting.

`.env` was gitignored from the start and verified excluded before every commit; `.env.example` carries the shape (with a matching bug fixed along the way — it briefly used the deprecated `LANGFUSE_HOST` name instead of the current `LANGFUSE_BASE_URL`).

---

## 14. Final state — what's proven vs. what's still a gap

**Proven end-to-end, not just written:**
- Postgres + pgvector running, schema applied, holding real data
- Real filings → real structured extraction, tuned through multiple iterations against actual bugs
- `interrupt()` pause verified durable: paused in one process, resumed from a **completely separate process**, proving Postgres persistence rather than an in-memory wait
- Full HTTP round trip: `POST /documents` → background graph run → `awaiting_approval` → `GET /reviews/{id}/findings` → `POST /reviews/{id}/decision` → `complete`, all through real requests, including the `409` guard against double-approval
- Langfuse traces verified against Langfuse's own API, including accurate auto-computed cost

**Known, stated gaps:**
- No auth on any endpoint
- Ingestion decodes uploads as plain UTF-8 text only — a real EDGAR filing (HTML/PDF) isn't handled
- No EDGAR pull-by-ticker path (upload-only)
- The FastAPI app itself isn't containerized (only Postgres runs in Docker)
- `document_chunks`/pgvector embeddings exist in the schema but are unused — filings fit whole in Claude Opus 5's 1M-token context, so chunking wasn't needed for extraction; would matter for a future retrieval/Q&A feature
- `langchain-anthropic` is an installed dependency that's never actually imported
- `scripts/extract_filing.py` (the pre-graph, direct-write version) is superseded by `scripts/run_review.py`/`scripts/approve_review.py` but hasn't been deleted

---

## 15. Interview-ready "why" questions

- **Why LangGraph over a hand-rolled state machine for the HITL pause?** Native `interrupt()`/checkpoint primitives are purpose-built for exactly this pattern — pausing mid-execution and resuming from durable state — rather than reinventing checkpoint serialization and resume semantics by hand.
- **Why are qualitative findings and quantitative metrics in separate tables?** Different query shapes (citation+severity vs. value+unit+period), and putting numbers in a text-shaped table would mean parsing them back out for every trend/comparison query.
- **Why two LLM calls instead of one combined extraction call?** Different schemas, independently-tunable prompts, and structured outputs require one top-level JSON object per call.
- **Why the raw Anthropic SDK instead of `langchain_anthropic`?** Direct control over `client.messages.parse()`'s structured-output contract, without depending on how LangChain's own structured-output abstraction interacts with Claude's newest feature — a deliberate scope decision to get extraction correctness right before adding an abstraction layer.
- **Why is the unit-normalization fix label-only rather than doing unit conversion?** Because the observed bug was the model mislabeling an *already correctly scaled* number, not miscalculating it — doing a numeric conversion on top would have corrupted correct data. This was caught in code review before it ever ran against real data.
- **Why is `persist_extraction` a separate node from `review_gate`?** Because `interrupt()` re-executes its calling node's code from the top on resume — writes in that node would double-fire. Persisting first, in a node that never calls `interrupt()`, keeps that side effect one-shot.
- **What happens if the process crashes while a review is paused?** Nothing is lost — the paused state is checkpointed in Postgres keyed by `thread_id`; any process, at any later time, can resume it with `Command(resume=...)`.
- **How does the audit log differ from Langfuse tracing?** `audit_log` is the compliance record — who approved what, when, permanent. Langfuse traces are the dev-facing observability layer — what did the model actually see and say at each step. Deliberately separate: losing a trace is a shrug, losing an audit row is a problem.
