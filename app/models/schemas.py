"""
Pydantic models — the API-facing shapes. These mirror db/init/002-schema.sql
and db/init/003-financial-schema.sql, and double as the "structured findings"
schema the LLM's output is validated against (see app/graph/agent.py).

Two kinds of extracted data, kept in separate tables/models:
  - Finding: qualitative — risk factors, anomalies, legal proceedings, policy
    changes. Free-text value, severity-scored, may require human approval.
  - FinancialMetric: quantitative — revenue, margins, EPS, etc. One row per
    (document, metric, period); this is what trend/comparison queries read.
"""
from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    anomaly = "anomaly"
    critical = "critical"


class ReviewStatus(str, Enum):
    processing = "processing"
    awaiting_approval = "awaiting_approval"
    complete = "complete"
    rejected = "rejected"
    failed = "failed"


class FilingType(str, Enum):
    ten_k = "10-K"
    ten_q = "10-Q"
    eight_k = "8-K"
    def_14a = "DEF 14A"
    other = "other"


class FiscalPeriod(str, Enum):
    q1 = "Q1"
    q2 = "Q2"
    q3 = "Q3"
    q4 = "Q4"
    fy = "FY"


class FindingCategory(str, Enum):
    risk_factor = "risk_factor"
    legal_proceeding = "legal_proceeding"
    accounting_policy = "accounting_policy"
    governance = "governance"
    anomaly = "anomaly"
    other = "other"


class MetricUnit(str, Enum):
    usd = "usd"
    usd_thousands = "usd_thousands"
    usd_millions = "usd_millions"
    percent = "percent"
    ratio = "ratio"
    shares = "shares"


class MetricPeriodType(str, Enum):
    annual = "annual"
    quarterly = "quarterly"
    ttm = "ttm"


class MetricName(str, Enum):
    """
    Curated starter set for the extraction prompt's target list. The DB
    column is free-text (not a hard constraint) so new metrics can be added
    without a migration — extend this enum when the prompt should target them.
    """
    revenue = "revenue"
    gross_profit = "gross_profit"
    operating_income = "operating_income"
    net_income = "net_income"
    eps_basic = "eps_basic"
    eps_diluted = "eps_diluted"
    total_assets = "total_assets"
    total_liabilities = "total_liabilities"
    total_debt = "total_debt"
    cash_and_equivalents = "cash_and_equivalents"
    operating_cash_flow = "operating_cash_flow"
    free_cash_flow = "free_cash_flow"
    gross_margin = "gross_margin"
    operating_margin = "operating_margin"
    net_margin = "net_margin"


class Company(BaseModel):
    id: UUID
    ticker: str
    cik: str | None = None
    name: str | None = None
    created_at: datetime


class Finding(BaseModel):
    id: UUID
    document_id: UUID
    company_id: UUID | None = None
    category: FindingCategory = FindingCategory.other
    field_name: str
    value: str | None = None
    severity: Severity = Severity.info
    confidence: float | None = Field(default=None, ge=0, le=1)
    citation: str | None = None
    requires_approval: bool = False
    created_at: datetime


class FinancialMetric(BaseModel):
    id: UUID
    document_id: UUID
    company_id: UUID
    metric_name: str  # validated against MetricName by the extraction node; free text at the DB layer
    value: float
    unit: MetricUnit
    period_type: MetricPeriodType
    fiscal_year: int
    fiscal_period: FiscalPeriod
    period_end_date: date | None = None
    citation: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    status: ReviewStatus
    company_id: UUID | None = None
    ticker: str | None = None
    company_name: str | None = None
    filing_type: FilingType | None = None
    fiscal_year: int | None = None
    fiscal_period: FiscalPeriod | None = None
    period_end_date: date | None = None
    created_at: datetime
    updated_at: datetime


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str | None = None
    reviewer: str | None = None  # the human's identity, for the audit trail
