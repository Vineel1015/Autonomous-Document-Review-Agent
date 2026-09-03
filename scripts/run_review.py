"""
Start a real, interruptible LangGraph review run for an already-ingested
document — the graph-based replacement for the older scripts/extract_filing.py,
which wrote extraction results directly with no actual pause/approve step.

Usage:
    1. Submit the filing first (see scripts/extract_filing.py's docstring for
       the curl command), to get a document_id.

    2. Start the graph run:
       uv run python scripts/run_review.py <document_id> <path/to/filing.txt>

If no finding needs approval, the run completes straight through. Otherwise
it prints the pending findings and pauses — genuinely paused, checkpointed to
Postgres, not just an in-memory wait. Resume it with scripts/approve_review.py,
even from a completely separate process.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# psycopg's async mode (used by the LangGraph Postgres checkpointer) can't
# run under Windows' default ProactorEventLoop — must switch to Selector.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db import connect_db, disconnect_db, get_pool
from app.graph.agent import get_compiled_graph
from app.graph.checkpointer import connect_checkpointer, disconnect_checkpointer
from app.graph.tracing import trace_review_run


async def run(document_id: str, text_path: str) -> None:
    await connect_db()
    await connect_checkpointer()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET thread_id = $1, status = 'processing', updated_at = now() WHERE id = $1",
                document_id,
            )

        text = Path(text_path).read_text(encoding="utf-8")
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": document_id}}

        print(f"Starting review for document {document_id} ...")
        async with trace_review_run(document_id, "start"):
            result = await graph.ainvoke({"document_id": document_id, "text": text}, config)

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value
            print(f"\nPAUSED — {len(payload['pending_findings'])} finding(s) need human approval:")
            for f in payload["pending_findings"]:
                print(f"  [{f['severity']}] {f['field_name']}")
                print(f"    {f['value']}")
            print(f"\nResume with:")
            print(f"  uv run python scripts/approve_review.py {document_id} approve")
            print(f"  uv run python scripts/approve_review.py {document_id} reject \"<reason>\"")
        else:
            print(f"\nCompleted without pausing. Decision: {result.get('decision')}")
    finally:
        await disconnect_checkpointer()
        await disconnect_db()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/run_review.py <document_id> <path/to/filing.txt>")
    asyncio.run(run(sys.argv[1], sys.argv[2]))
