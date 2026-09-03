"""
Company + per-company trend endpoints. Pure reads against financial_metrics —
no LLM involved, so these work as soon as data exists in the table.
"""
import asyncpg
from fastapi import APIRouter, Depends

from app.db import get_db
from app.models.schemas import Company, FinancialMetric

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[Company])
async def list_companies(db: asyncpg.Connection = Depends(get_db)):
    rows = await db.fetch("SELECT * FROM companies ORDER BY ticker")
    return [dict(r) for r in rows]


@router.get("/{ticker}/metrics", response_model=list[FinancialMetric])
async def get_company_metrics(
    ticker: str,
    metric_name: str | None = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """
    One company's metric(s) over time — quarter-over-quarter / year-over-year
    trend view. Omit metric_name to get every tracked metric, ordered so a
    client can group by metric_name itself.
    """
    ticker = ticker.upper()
    query = """
        SELECT fm.* FROM financial_metrics fm
        JOIN companies c ON c.id = fm.company_id
        WHERE c.ticker = $1
    """
    params: list = [ticker]
    if metric_name:
        query += " AND fm.metric_name = $2"
        params.append(metric_name)
    query += " ORDER BY fm.metric_name, fm.period_end_date"

    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]
