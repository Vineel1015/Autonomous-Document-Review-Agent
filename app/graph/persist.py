"""
Shared Postgres writes for extraction results. Used by the LangGraph nodes
(app/graph/agent.py) so there's exactly one place that knows the
financial_metrics/findings/audit_log write shape.
"""
import json

import asyncpg

from app.models.extraction import ExtractedFinding, ExtractedMetric


async def persist_metrics(
    conn: asyncpg.Connection,
    document_id: str,
    company_id: str,
    metrics: list[ExtractedMetric],
) -> None:
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
            document_id,
            company_id,
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


async def persist_findings(
    conn: asyncpg.Connection,
    document_id: str,
    company_id: str,
    findings: list[ExtractedFinding],
) -> None:
    for f in findings:
        await conn.execute(
            """
            INSERT INTO findings (
                document_id, company_id, category, field_name, value,
                severity, confidence, citation, requires_approval
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            document_id,
            company_id,
            f.category.value,
            f.field_name,
            f.value,
            f.severity.value,
            f.confidence,
            f.citation,
            f.requires_approval,
        )


async def write_audit_log(
    conn: asyncpg.Connection,
    document_id: str,
    actor: str,
    action: str,
    detail: dict | None = None,
) -> None:
    """
    The compliance trail — separate from Langfuse's dev-facing traces.
    Every consequential step in a review's lifecycle writes one row here:
    extraction happening, a pause starting, a human's decision.
    """
    await conn.execute(
        "INSERT INTO audit_log (document_id, actor, action, detail) VALUES ($1, $2, $3, $4::jsonb)",
        document_id,
        actor,
        action,
        json.dumps(detail) if detail is not None else None,
    )
