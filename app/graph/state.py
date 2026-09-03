"""
The LangGraph state object — what flows between nodes. This is checkpointed
to Postgres after every node (see app/graph/checkpointer.py), which is what
lets a run pause on interrupt() in app/graph/agent.py and resume later, even
across a process restart — the pause isn't a Python function sleeping, it's
this state sitting in Postgres.
"""
from typing import TypedDict

from app.graph.extraction import FilingContext
from app.models.extraction import ExtractedFinding, ExtractedMetric


class ReviewState(TypedDict, total=False):
    document_id: str
    company_id: str
    text: str
    context: FilingContext
    metrics: list[ExtractedMetric]
    findings: list[ExtractedFinding]
    decision: dict | None
