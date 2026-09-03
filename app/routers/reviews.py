"""
Review endpoints — reading findings, and the human-in-the-loop decision flow
that resumes a paused LangGraph run (see app/graph/agent.py's review_gate_node,
which is where the interrupt() actually happens).
"""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from app.db import get_db
from app.graph.agent import get_compiled_graph
from app.graph.tracing import trace_review_run
from app.models.schemas import Finding, ReviewDecision

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/{document_id}/findings", response_model=list[Finding])
async def list_findings(document_id: str, db: asyncpg.Connection = Depends(get_db)):
    rows = await db.fetch(
        "SELECT * FROM findings WHERE document_id = $1 ORDER BY created_at",
        document_id,
    )
    return [dict(r) for r in rows]


@router.post("/{document_id}/decision")
async def submit_decision(
    document_id: str,
    decision: ReviewDecision,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Resumes a paused review with a human's approve/reject decision. Named
    "decision" rather than "approve" since ReviewDecision.decision covers
    both outcomes in one body.

    Rejects with 409 if the document isn't actually paused — resuming a
    thread that was never interrupted (or was already resumed) is a no-op at
    best and a race at worst, so this fails loudly instead.
    """
    doc = await db.fetchrow(
        "SELECT status, thread_id FROM documents WHERE id = $1", document_id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc["status"] != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not awaiting approval (status={doc['status']!r})",
        )

    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": doc["thread_id"] or document_id}}
    async with trace_review_run(document_id, "resume"):
        result = await graph.ainvoke(Command(resume=decision.model_dump()), config)

    return {"document_id": document_id, "decision": result.get("decision")}
