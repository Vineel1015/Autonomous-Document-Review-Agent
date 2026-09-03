"""
Cross-company metric comparison (peer benchmarking) — kept separate from
app/routers/companies.py's per-company trend view to avoid path ambiguity
and because the query shape is genuinely different (one metric, many
companies, vs. one company, many metrics).
"""
import asyncpg
from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.models.schemas import FinancialMetric

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/compare", response_model=list[FinancialMetric])
async def compare_metric(
    metric_name: str,
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT"),
    period_type: str | None = None,
    db: asyncpg.Connection = Depends(get_db),
):
    """Same metric across multiple companies — for peer comparison."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

    query = """
        SELECT fm.* FROM financial_metrics fm
        JOIN companies c ON c.id = fm.company_id
        WHERE fm.metric_name = $1 AND c.ticker = ANY($2::text[])
    """
    params: list = [metric_name, ticker_list]
    if period_type:
        query += " AND fm.period_type = $3"
        params.append(period_type)
    query += " ORDER BY c.ticker, fm.period_end_date"

    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]
