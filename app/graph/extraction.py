"""
Standalone LLM extraction — takes filing text plus its company/period context
and returns structured metrics and findings via Claude's structured outputs
(client.messages.parse). Deliberately not wired into LangGraph yet: this is
the fastest way to iterate on the prompts/schema before adding the
interrupt/checkpoint machinery in app/graph/agent.py. Once this is solid,
agent.py's nodes call these exact same functions.

Two separate calls rather than one combined call: metrics and findings have
different shapes and land in different tables (financial_metrics vs
findings), and structured outputs expect a single top-level JSON object per
call — a combined schema would work but blurs two independently-tunable
prompts into one.

Filings comfortably fit Claude Opus 5's 1M-token context window (a 10-K is
typically 20-50K tokens), so v1 passes the full filing text directly rather
than chunking. The pgvector chunk/embedding table (document_chunks) stays
useful for future retrieval-style features (e.g. "ask a question about this
filing") — it's not required for extraction itself.
"""
import asyncio
from collections import Counter

import anthropic
from pydantic import BaseModel

from app.config import get_settings
from app.graph.tracing import get_langfuse_client, usage_details
from app.models.extraction import (
    ExtractedFinding,
    ExtractedFindings,
    ExtractedMetric,
    ExtractedMetrics,
)
from app.models.schemas import FilingType, FiscalPeriod, MetricName

MODEL = "claude-opus-5"

# Absolute-dollar metrics that should always share one unit within a single
# extraction batch (excludes EPS — always per-share usd — and margins/ratios).
_DOLLAR_METRIC_NAMES = {
    MetricName.revenue,
    MetricName.gross_profit,
    MetricName.operating_income,
    MetricName.net_income,
    MetricName.total_assets,
    MetricName.total_liabilities,
    MetricName.total_debt,
    MetricName.cash_and_equivalents,
    MetricName.operating_cash_flow,
    MetricName.free_cash_flow,
}


def _normalize_dollar_units(metrics: list[ExtractedMetric]) -> list[ExtractedMetric]:
    """
    Safety net for an observed failure mode: the model sometimes copies the
    correct digits from a scaled table (e.g. "in millions") but mislabels the
    unit on one line — e.g. tagging revenue as usd while net_income/
    operating_income from the same statement correctly say usd_millions.
    Prompting alone didn't reliably fix this (tested — two rounds, same
    outlier both times).

    This corrects the LABEL only — it deliberately does NOT rescale the
    value. The observed failure is a mislabel, not a miscalculation: the
    digits already match what's printed in the table, which is already
    scaled. Multiplying/dividing them again on top of a relabel would treat
    a correct number as if it were wrong and corrupt it — e.g. turning
    Apple's ~$391B revenue into ~$0.39, a far worse error than the one being
    fixed. If a future case turns out to need real unit conversion (not just
    relabeling), that's a different bug and should be diagnosed on its own
    evidence, not assumed here.
    """
    dollar_metrics = [m for m in metrics if m.metric_name in _DOLLAR_METRIC_NAMES]
    if len(dollar_metrics) < 2:
        return metrics

    counts = Counter(m.unit for m in dollar_metrics)
    majority_unit, majority_count = counts.most_common(1)[0]
    if majority_count == len(dollar_metrics):
        return metrics  # already consistent — nothing to do

    for m in dollar_metrics:
        if m.unit == majority_unit:
            continue
        old_unit = m.unit
        m.unit = majority_unit
        m.confidence = min(m.confidence, 0.5)
        m.citation = (
            f"{m.citation} [unit auto-corrected: model labeled this {old_unit.value} "
            f"while other dollar figures in this filing used {majority_unit.value}; "
            f"value left unchanged, only the unit label was corrected — verify against source]"
        )
    return metrics


def _client() -> anthropic.AsyncAnthropic:
    """
    api_key=None falls back to the SDK's normal resolution (ANTHROPIC_API_KEY
    env var, then an `ant auth login` profile), so this works whether the key
    comes from .env (via Settings) or is exported directly in the shell.

    ANTHROPIC_WORKSPACE_ID is only needed for an "identity-linked" API key
    (tied to a Console account rather than scoped to one workspace) — such a
    key requires every request to state which workspace it acts in.
    """
    settings = get_settings()
    headers = {}
    if settings.anthropic_workspace_id:
        headers["anthropic-workspace-id"] = settings.anthropic_workspace_id
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, default_headers=headers)


class FilingContext(BaseModel):
    """
    Metadata captured at ingestion (see app/routers/documents.py) that grounds
    the extraction — without it the model has to guess the reporting period
    and ticker from the document text alone.
    """
    ticker: str
    filing_type: FilingType
    fiscal_year: int
    fiscal_period: FiscalPeriod


_METRICS_SYSTEM_PROMPT = """\
You are a financial analyst extracting quantitative metrics from SEC filings \
for a due-diligence and trend-analysis tool. For every metric you can find \
with high confidence, extract its name, value, unit, the fiscal period it \
applies to, a citation, and your confidence.

Rules:
- Only extract the CURRENT reporting period's figures, not prior-year \
  comparatives shown alongside them, unless the filing gives no current-period \
  figure for that metric.
- If a margin (gross/operating/net) isn't stated directly, you may compute it \
  from reported figures, but lower your confidence and note that it's derived \
  in the citation.
- Never invent a number. If you're not confident a figure is correct, omit it \
  rather than guess.
- Before extracting any figures from a statement or table, first find its \
  reporting-scale header (e.g. "in millions", "in thousands", "except \
  per-share amounts") and decide the unit for every line in that table up \
  front. Then apply that SAME unit to every value you take from that table —
  never mix usd and usd_millions within figures pulled from one table.
  Per-share figures (EPS) are the one exception: they always use unit=usd,
  even inside a table stated "in millions".

  Worked example — given a table headed "(in millions, except per-share
  amounts)" containing "Net sales $391,035" and "Diluted EPS $6.75", the
  correct extraction is:
    {"metric_name": "revenue", "value": 391035, "unit": "usd_millions", ...}
    {"metric_name": "eps_diluted", "value": 6.75, "unit": "usd", ...}
  Extracting revenue with unit="usd" here would be WRONG — it must match
  gross_profit/net_income/operating_income from the same table, which also
  use usd_millions.
"""

_FINDINGS_SYSTEM_PROMPT = """\
You are a financial analyst reviewing an SEC filing for a due-diligence tool. \
Extract qualitative findings a human reviewer needs to see before relying on \
this filing for an investment decision — material risk factors, legal \
proceedings, accounting policy changes or restatements, governance changes \
(executive/board changes, related-party transactions, auditor changes), and \
anomalies (anything that looks inconsistent, understated, or out of place \
relative to the rest of the filing).

For each finding, set severity based on how much it could affect an \
investment decision, and set requires_approval = true for anything at \
anomaly/critical severity — those need a human sign-off before being treated \
as final. Always include a citation (verbatim snippet) grounding the finding \
in the actual text — never report something you can't point to.

Ground every finding STRICTLY in this document's own internal consistency —
numbers that don't reconcile with other numbers reported elsewhere in this
same filing, disclosures that are missing, contradictory, or in the wrong
section, and language that is evasive or unusual for a filing of this type.
Do NOT use your own outside/memorized knowledge of this company's actual
historical financial results to judge whether a figure looks right — that
knowledge may be stale or wrong, and a comparison against it is not something
you can cite from the filing itself. If a number merely looks surprising
relative to what you recall about the company, that is not grounds for an
anomaly finding on its own.
"""


def _filing_header(context: FilingContext) -> str:
    return (
        f"Company: {context.ticker}\n"
        f"Filing type: {context.filing_type.value}\n"
        f"Fiscal year: {context.fiscal_year}\n"
        f"Fiscal period: {context.fiscal_period.value}\n\n"
    )


async def extract_metrics(text: str, context: FilingContext) -> list[ExtractedMetric]:
    client = _client()
    user_content = _filing_header(context) + "Filing text:\n\n" + text
    langfuse = get_langfuse_client()

    with langfuse.start_as_current_observation(
        as_type="generation",
        name="extract_metrics",
        model=MODEL,
        input=[{"role": "system", "content": _METRICS_SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        model_parameters={"max_tokens": 16000},
    ) as generation:
        response = await client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=_METRICS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_format=ExtractedMetrics,
        )
        raw_metrics = response.parsed_output.metrics
        generation.update(
            output=[m.model_dump(mode="json") for m in raw_metrics],
            usage_details=usage_details(response.usage),
        )

    return _normalize_dollar_units(raw_metrics)


async def extract_findings(text: str, context: FilingContext) -> list[ExtractedFinding]:
    client = _client()
    user_content = _filing_header(context) + "Filing text:\n\n" + text
    langfuse = get_langfuse_client()

    with langfuse.start_as_current_observation(
        as_type="generation",
        name="extract_findings",
        model=MODEL,
        input=[{"role": "system", "content": _FINDINGS_SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        model_parameters={"max_tokens": 16000},
    ) as generation:
        response = await client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=_FINDINGS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_format=ExtractedFindings,
        )
        findings = response.parsed_output.findings
        generation.update(
            output=[f.model_dump(mode="json") for f in findings],
            usage_details=usage_details(response.usage),
        )

    return findings


async def extract_filing(
    text: str, context: FilingContext
) -> tuple[list[ExtractedMetric], list[ExtractedFinding]]:
    """Run both extractions concurrently — they're independent LLM calls."""
    return await asyncio.gather(
        extract_metrics(text, context),
        extract_findings(text, context),
    )
