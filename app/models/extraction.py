"""
LLM output shapes for the extraction step. These mirror the DB-facing models
in app/models/schemas.py but omit fields the model shouldn't produce (id,
document_id, company_id, created_at) — app/graph/extraction.py fills those in
from the filing's context before writing to Postgres.

Structured outputs require a single top-level JSON object per call, so each
extraction target gets a root wrapper (ExtractedMetrics / ExtractedFindings)
around its list.
"""
from datetime import date

from pydantic import BaseModel, Field

from app.models.schemas import (
    FindingCategory,
    FiscalPeriod,
    MetricName,
    MetricPeriodType,
    MetricUnit,
    Severity,
)


class ExtractedMetric(BaseModel):
    metric_name: MetricName
    value: float
    unit: MetricUnit
    period_type: MetricPeriodType
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_end_date: date | None = None
    citation: str = Field(description="Verbatim snippet or table reference this figure came from")
    confidence: float = Field(ge=0, le=1)


class ExtractedMetrics(BaseModel):
    metrics: list[ExtractedMetric]


class ExtractedFinding(BaseModel):
    category: FindingCategory
    field_name: str = Field(description="Short label for what this finding is about")
    value: str = Field(description="The finding itself, in plain language")
    severity: Severity
    citation: str = Field(description="Verbatim snippet this finding is grounded in")
    confidence: float = Field(ge=0, le=1)
    requires_approval: bool = Field(
        default=False,
        description=(
            "True for anything consequential enough to need a human sign-off "
            "before being treated as final — anomaly/critical severity should "
            "generally set this."
        ),
    )


class ExtractedFindings(BaseModel):
    findings: list[ExtractedFinding]
