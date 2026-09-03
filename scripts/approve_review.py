"""
Resume a paused LangGraph review run with a human decision — deliberately a
separate process from scripts/run_review.py, to prove the pause is real
(state loaded back from Postgres via the checkpointer) and not just an
in-memory wait inside one still-running script.

Usage:
    uv run python scripts/approve_review.py <document_id> approve
    uv run python scripts/approve_review.py <document_id> reject "<reason>"
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# psycopg's async mode (used by the LangGraph Postgres checkpointer) can't
# run under Windows' default ProactorEventLoop — must switch to Selector.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from langgraph.types import Command

from app.db import connect_db, disconnect_db
from app.graph.agent import get_compiled_graph
from app.graph.checkpointer import connect_checkpointer, disconnect_checkpointer
from app.graph.tracing import trace_review_run


async def run(document_id: str, decision: str, reason: str | None) -> None:
    if decision not in ("approve", "reject"):
        raise SystemExit("decision must be 'approve' or 'reject'")

    await connect_db()
    await connect_checkpointer()
    try:
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": document_id}}

        print(f"Resuming document {document_id} with decision={decision} ...")
        async with trace_review_run(document_id, "resume"):
            result = await graph.ainvoke(
                Command(resume={"decision": decision, "reason": reason, "reviewer": "cli-test"}),
                config,
            )
        print(f"Done. Final decision: {result.get('decision')}")
    finally:
        await disconnect_checkpointer()
        await disconnect_db()


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit('Usage: python scripts/approve_review.py <document_id> <approve|reject> ["reason"]')
    asyncio.run(run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None))
