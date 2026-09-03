"""
Ingestion endpoints — where a filing enters the system and a review begins.
"""
import logging
from datetime import date

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile

from app.db import get_db, get_pool
from app.graph.agent import get_compiled_graph
from app.graph.tracing import trace_review_run
from app.models.schemas import DocumentOut, FilingType, FiscalPeriod, ReviewStatus

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

# Every DocumentOut-shaped SELECT joins companies so ticker/company_name are
# populated — a bare company_id UUID isn't a usable label in a UI list/detail.
_DOCUMENT_SELECT = """
    SELECT d.id, d.filename, d.status, d.company_id, c.ticker, c.name AS company_name,
           d.filing_type, d.fiscal_year, d.fiscal_period, d.period_end_date,
           d.created_at, d.updated_at
    FROM documents d
    LEFT JOIN companies c ON c.id = d.company_id
"""


async def _run_review(document_id: str, text: str) -> None:
    """
    Runs after the response is already sent (see BackgroundTasks below), so
    it can't raise into a request — any failure here is logged and reflected
    in documents.status='failed' instead. Uses a fresh pool connection rather
    than the request's `db` dependency, which is already released back to the
    pool by the time a background task starts running.
    """
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET thread_id = $1 WHERE id = $1", document_id
            )
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": document_id}}
        async with trace_review_run(document_id, "start"):
            await graph.ainvoke({"document_id": document_id, "text": text}, config)
    except Exception:
        logger.exception("Review run failed for document %s", document_id)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE documents SET status = 'failed', updated_at = now() WHERE id = $1",
                document_id,
            )


@router.post("", response_model=DocumentOut, status_code=202)
async def submit_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ticker: str = Form(..., description="Stock ticker, e.g. AAPL"),
    filing_type: FilingType = Form(...),
    fiscal_year: int = Form(...),
    fiscal_period: FiscalPeriod = Form(...),
    period_end_date: date | None = Form(default=None),
    db: asyncpg.Connection = Depends(get_db),
):
    """
    Accepts a filing tagged with the company + reporting period it covers,
    and returns immediately with the new document's id/status — the actual
    LangGraph review (extraction, then a real interrupt() pause if anything
    needs approval — see app/graph/agent.py) runs in the background so this
    request doesn't block on the LLM.

    Looks up the company by ticker, creating a bare row (ticker only — name/
    CIK get filled in once EDGAR ingestion lands) if this is the first filing
    seen for it.

    Note: reads the upload as UTF-8 text directly. Filings are typically
    plain text or already-extracted text at this stage — HTML/PDF filings
    straight from EDGAR would need a text-extraction step first; that's a
    TODO for the EDGAR ingestion path, not this one.
    """
    ticker = ticker.upper()
    text = (await file.read()).decode("utf-8", errors="replace")

    async with db.transaction():
        company = await db.fetchrow("SELECT id FROM companies WHERE ticker = $1", ticker)
        if company is None:
            company = await db.fetchrow(
                "INSERT INTO companies (ticker) VALUES ($1) RETURNING id", ticker
            )

        row = await db.fetchrow(
            """
            INSERT INTO documents (
                filename, status, company_id, filing_type,
                fiscal_year, fiscal_period, period_end_date
            )
            VALUES ($1, 'processing', $2, $3, $4, $5, $6)
            RETURNING id, filename, status, company_id, filing_type,
                      fiscal_year, fiscal_period, period_end_date,
                      created_at, updated_at
            """,
            file.filename,
            company["id"],
            filing_type.value,
            fiscal_year,
            fiscal_period.value,
            period_end_date,
        )

    background_tasks.add_task(_run_review, str(row["id"]), text)

    enriched = await db.fetchrow(_DOCUMENT_SELECT + " WHERE d.id = $1", row["id"])
    return dict(enriched)


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    status: ReviewStatus | None = None,
    ticker: str | None = None,
    filing_type: FilingType | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: asyncpg.Connection = Depends(get_db),
):
    """The document list/dashboard's data source. Filters are all optional
    and combine with AND; unfiltered returns the most recent filings first."""
    conditions = []
    params: list = []

    if status is not None:
        params.append(status.value)
        conditions.append(f"d.status = ${len(params)}")
    if ticker is not None:
        params.append(ticker.upper())
        conditions.append(f"c.ticker = ${len(params)}")
    if filing_type is not None:
        params.append(filing_type.value)
        conditions.append(f"d.filing_type = ${len(params)}")

    query = _DOCUMENT_SELECT
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    params.append(limit)
    query += f" ORDER BY d.created_at DESC LIMIT ${len(params)}"
    params.append(offset)
    query += f" OFFSET ${len(params)}"

    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, db: asyncpg.Connection = Depends(get_db)):
    row = await db.fetchrow(_DOCUMENT_SELECT + " WHERE d.id = $1", document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return dict(row)
