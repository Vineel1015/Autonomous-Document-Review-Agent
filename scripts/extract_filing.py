"""
Run structured extraction against an already-ingested filing and write the
results to Postgres. Requires ANTHROPIC_API_KEY to be set (see .env).

This is the standalone proving ground for app/graph/extraction.py — run it
against a real filing to check the prompts/schema before any of this is
wired into the LangGraph interrupt/checkpoint machinery.

Usage:
    1. Submit the filing first, to get a document_id:
       curl -X POST http://127.0.0.1:8000/documents \\
         -F "file=@aapl_10k.txt" -F "ticker=AAPL" -F "filing_type=10-K" \\
         -F "fiscal_year=2025" -F "fiscal_period=FY" -F "period_end_date=2025-09-27"

    2. Run extraction against that document's text:
       uv run python scripts/extract_filing.py <document_id> aapl_10k.txt
"""
import asyncio
import sys
from pathlib import Path

# Allow running this script directly (`python scripts/extract_filing.py`)
# without needing the repo root on PYTHONPATH already.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from app.config import get_settings
from app.graph.extraction import FilingContext, extract_filing
from app.models.schemas import FilingType, FiscalPeriod


async def run(document_id: str, text_path: str) -> None:
    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        doc = await conn.fetchrow(
            """
            SELECT d.id, d.company_id, d.filing_type, d.fiscal_year, d.fiscal_period, c.ticker
            FROM documents d
            JOIN companies c ON c.id = d.company_id
            WHERE d.id = $1
            """,
            document_id,
        )
        if doc is None:
            raise SystemExit(f"No document found with id {document_id}")

        context = FilingContext(
            ticker=doc["ticker"],
            filing_type=FilingType(doc["filing_type"]),
            fiscal_year=doc["fiscal_year"],
            fiscal_period=FiscalPeriod(doc["fiscal_period"]),
        )
        text = Path(text_path).read_text(encoding="utf-8")

        print(
            f"Extracting {context.ticker} {context.filing_type.value} "
            f"{context.fiscal_year} {context.fiscal_period.value} ..."
        )
        metrics, findings = await extract_filing(text, context)
        print(f"  {len(metrics)} metrics, {len(findings)} findings extracted")

        async with conn.transaction():
            for m in metrics:
                await conn.execute(
                    """
                    INSERT INTO financial_metrics (
                        document_id, company_id, metric_name, value, unit,
                        period_type, fiscal_year, fiscal_period, period_end_date,
                        citation, confidence
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (document_id, metric_name, period_type)
                    DO UPDATE SET value = EXCLUDED.value,
                                  citation = EXCLUDED.citation,
                                  confidence = EXCLUDED.confidence
                    """,
                    doc["id"],
                    doc["company_id"],
                    m.metric_name.value,
                    m.value,
                    m.unit.value,
                    m.period_type.value,
                    m.fiscal_year,
                    m.fiscal_period.value,
                    m.period_end_date,
                    m.citation,
                    m.confidence,
                )

            any_requires_approval = False
            for f in findings:
                await conn.execute(
                    """
                    INSERT INTO findings (
                        document_id, company_id, category, field_name, value,
                        severity, confidence, citation, requires_approval
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    doc["id"],
                    doc["company_id"],
                    f.category.value,
                    f.field_name,
                    f.value,
                    f.severity.value,
                    f.confidence,
                    f.citation,
                    f.requires_approval,
                )
                any_requires_approval = any_requires_approval or f.requires_approval

            new_status = "awaiting_approval" if any_requires_approval else "complete"
            await conn.execute(
                "UPDATE documents SET status = $1, updated_at = now() WHERE id = $2",
                new_status,
                doc["id"],
            )

        print(f"  document status -> {new_status}")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/extract_filing.py <document_id> <path/to/filing.txt>")
    asyncio.run(run(sys.argv[1], sys.argv[2]))
