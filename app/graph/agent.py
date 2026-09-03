"""
The real LangGraph review pipeline — replaces the earlier stand-in where
scripts/extract_filing.py wrote results directly and just flipped a status
column. Here, a genuine interrupt() pause happens inside review_gate_node,
checkpointed to Postgres by app/graph/checkpointer.py, and only resumes when
a human calls scripts/approve_review.py (or, once wired up, POST
/reviews/{id}/approve) with a real Command(resume=...).

Graph shape:

    START -> load_context
               |
       +-------+-------+
       |               |
  extract_metrics  extract_findings      (run concurrently)
       |               |
       +-------+-------+
               |
      persist_extraction                 (writes metrics + findings to
               |                          Postgres immediately, so a human
               |                          reviewer can see them while paused)
          review_gate                    (interrupt() here iff any finding
               |                          has requires_approval=True)
           finalize                      (sets documents.status, writes the
               |                          human's decision to audit_log)
              END

Two extraction nodes run concurrently off the same load_context node (a
standard LangGraph fan-out/fan-in: both edges from load_context land the
graph in the same superstep, and persist_extraction — reached from both —
only fires once both have completed).
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.db import get_pool
from app.graph.checkpointer import get_checkpointer
from app.graph.extraction import FilingContext, extract_findings, extract_metrics
from app.graph.persist import persist_findings, persist_metrics, write_audit_log
from app.graph.state import ReviewState
from app.models.schemas import FilingType, FiscalPeriod


async def load_context_node(state: ReviewState) -> dict:
    """
    Look up the filing's company/period metadata (set at ingestion — see
    app/routers/documents.py) once, so the two parallel extraction nodes
    below don't each need their own DB round trip.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT d.company_id, d.filing_type, d.fiscal_year, d.fiscal_period, c.ticker
            FROM documents d
            JOIN companies c ON c.id = d.company_id
            WHERE d.id = $1
            """,
            state["document_id"],
        )
    if row is None:
        raise ValueError(f"No document found with id {state['document_id']}")

    context = FilingContext(
        ticker=row["ticker"],
        filing_type=FilingType(row["filing_type"]),
        fiscal_year=row["fiscal_year"],
        fiscal_period=FiscalPeriod(row["fiscal_period"]),
    )
    return {"company_id": str(row["company_id"]), "context": context}


async def extract_metrics_node(state: ReviewState) -> dict:
    metrics = await extract_metrics(state["text"], state["context"])
    return {"metrics": metrics}


async def extract_findings_node(state: ReviewState) -> dict:
    findings = await extract_findings(state["text"], state["context"])
    return {"findings": findings}


async def persist_extraction_node(state: ReviewState) -> dict:
    """
    Writes results as soon as they exist, so GET /reviews/{id}/findings shows
    them to a human reviewer while the run is paused at review_gate below —
    not only after the run fully completes.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await persist_metrics(conn, state["document_id"], state["company_id"], state["metrics"])
            await persist_findings(conn, state["document_id"], state["company_id"], state["findings"])
            await write_audit_log(
                conn,
                state["document_id"],
                actor="agent",
                action="extracted",
                detail={"metrics": len(state["metrics"]), "findings": len(state["findings"])},
            )
    return {}


async def review_gate_node(state: ReviewState) -> dict:
    """
    Pauses the run iff any finding needs a human sign-off. interrupt()
    re-executes THIS node's code from the top on resume (LangGraph replays a
    node from its start, not the whole graph), so everything before the
    interrupt() call here is read-only/idempotent by design — the actual
    writes already happened in persist_extraction_node, which only runs once.
    """
    pending = [f for f in state["findings"] if f.requires_approval]
    if not pending:
        return {"decision": {"decision": "approve", "reason": "no findings required approval"}}

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE documents SET status = 'awaiting_approval', updated_at = now() WHERE id = $1",
            state["document_id"],
        )

    decision = interrupt({
        "document_id": state["document_id"],
        "pending_findings": [f.model_dump(mode="json") for f in pending],
    })
    return {"decision": decision}


async def finalize_node(state: ReviewState) -> dict:
    decision = state.get("decision") or {}
    approved = decision.get("decision") == "approve"
    new_status = "complete" if approved else "rejected"

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE documents SET status = $1, updated_at = now() WHERE id = $2",
            new_status,
            state["document_id"],
        )
        await write_audit_log(
            conn,
            state["document_id"],
            actor=decision.get("reviewer") or "system",
            action=new_status,
            detail=decision,
        )
    return {"decision": decision}


def build_graph(checkpointer: AsyncPostgresSaver) -> CompiledStateGraph:
    builder = StateGraph(ReviewState)
    builder.add_node("load_context", load_context_node)
    builder.add_node("extract_metrics", extract_metrics_node)
    builder.add_node("extract_findings", extract_findings_node)
    builder.add_node("persist_extraction", persist_extraction_node)
    builder.add_node("review_gate", review_gate_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "extract_metrics")
    builder.add_edge("load_context", "extract_findings")
    builder.add_edge("extract_metrics", "persist_extraction")
    builder.add_edge("extract_findings", "persist_extraction")
    builder.add_edge("persist_extraction", "review_gate")
    builder.add_edge("review_gate", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer)


_compiled_graph: CompiledStateGraph | None = None


def get_compiled_graph() -> CompiledStateGraph:
    """
    Lazily builds the graph against the shared checkpointer (see
    app/graph/checkpointer.py — connect_checkpointer() must have run first,
    same as app/db.py's connect_db()).
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph(get_checkpointer())
    return _compiled_graph
