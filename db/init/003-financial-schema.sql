-- Financial-filing-specific schema: companies, filing metadata, and the
-- time-series metrics table that trend analysis / peer comparison read from.

CREATE TABLE IF NOT EXISTS companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      TEXT NOT NULL UNIQUE,
    cik         TEXT UNIQUE,                             -- SEC Central Index Key; populated once EDGAR ingestion lands
    name        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tag each filing with the company + reporting period it covers.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS company_id        UUID REFERENCES companies(id),
    ADD COLUMN IF NOT EXISTS filing_type       TEXT,      -- '10-K' | '10-Q' | '8-K' | 'DEF 14A' | 'other'
    ADD COLUMN IF NOT EXISTS fiscal_year       INT,
    ADD COLUMN IF NOT EXISTS fiscal_period     TEXT,      -- 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'FY'
    ADD COLUMN IF NOT EXISTS period_end_date   DATE,
    ADD COLUMN IF NOT EXISTS accession_number  TEXT;      -- EDGAR filing id, populated once EDGAR ingestion lands

CREATE INDEX IF NOT EXISTS documents_company_id_idx ON documents(company_id);

-- Qualitative findings get a category (risk factors, legal proceedings, etc.)
-- and are tied to a company for company-wide anomaly queries.
ALTER TABLE findings
    ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id),
    ADD COLUMN IF NOT EXISTS category   TEXT NOT NULL DEFAULT 'other';
    -- category: 'risk_factor' | 'legal_proceeding' | 'accounting_policy' | 'governance' | 'anomaly' | 'other'

-- Numeric metrics extracted from filings — the trend-analysis core.
-- One row per (document, metric, period). Keyed by company_id directly
-- (not just document_id) so cross-filing and cross-company queries stay simple.
CREATE TABLE IF NOT EXISTS financial_metrics (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    company_id        UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    metric_name       TEXT NOT NULL,       -- 'revenue' | 'net_income' | 'eps_diluted' | 'gross_margin' | ...
    value             NUMERIC NOT NULL,
    unit              TEXT NOT NULL,       -- 'usd' | 'usd_thousands' | 'usd_millions' | 'percent' | 'ratio' | 'shares'
    period_type       TEXT NOT NULL,       -- 'annual' | 'quarterly' | 'ttm'
    fiscal_year       INT NOT NULL,
    fiscal_period     TEXT NOT NULL,       -- 'Q1' | 'Q2' | 'Q3' | 'Q4' | 'FY'
    period_end_date   DATE,
    citation          TEXT,                -- source text / page reference backing this figure
    confidence        REAL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, metric_name, period_type)
);

-- The query this whole table exists for: one company's metric over time,
-- or one metric across several companies (peer comparison).
CREATE INDEX IF NOT EXISTS financial_metrics_trend_idx
    ON financial_metrics (company_id, metric_name, period_end_date);
