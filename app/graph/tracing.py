"""
Langfuse tracing for the review pipeline. This is the dev-facing observability
layer — "what did the agent actually do at each step" — kept deliberately
separate from app/graph/persist.py's audit_log, which is the compliance
record ("who approved what, when"). Losing a trace is a shrug; losing an
audit_log row is a problem.

The extraction functions in app/graph/extraction.py call the raw Anthropic
SDK directly (not langchain_anthropic), so there's no LangChain callback
chain to piggyback on for the LLM calls themselves — those get explicit
"generation" observations at each call site (see usage_details() below,
used there). The graph as a whole (a CompiledStateGraph) IS a LangChain
Runnable, so a broader alternative would be handing it
langfuse.langchain.CallbackHandler via config={"callbacks": [...]}; the
explicit span used here (trace_review_run, wrapping each graph.ainvoke call)
gives one trace per run without depending on that.

Safe by design: with no LANGFUSE_PUBLIC_KEY/SECRET_KEY configured, the client
is constructed with tracing_enabled=False and every span/generation call
below becomes a no-op — nothing here can break a run that has no Langfuse
credentials. Explicitly constructed from app.config.get_settings() rather
than Langfuse's own env-var auto-detection, since values living only in our
.env (via pydantic-settings) never reach real os.environ for another library
to read independently.
"""
from contextlib import asynccontextmanager
from typing import Any

from langfuse import Langfuse

from app.config import get_settings

_client: Langfuse | None = None


def get_langfuse_client() -> Langfuse:
    """Lazily builds one shared client for the process — constructing a
    Langfuse client opens background exporter threads, so this must not be
    called fresh on every request/generation."""
    global _client
    if _client is None:
        settings = get_settings()
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            _client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                base_url=settings.langfuse_base_url,
            )
        else:
            _client = Langfuse(tracing_enabled=False)
    return _client


@asynccontextmanager
async def trace_review_run(document_id: str, run_kind: str):
    """
    Wraps one graph.ainvoke() call (a fresh start or a resume) in a single
    top-level Langfuse trace, so every node's work — and the generation spans
    created inside app/graph/extraction.py — nests under one reviewable run.

    run_kind: "start" | "resume" — which kind of invocation this is, purely
    for readability in the Langfuse UI.
    """
    client = get_langfuse_client()
    with client.start_as_current_observation(
        as_type="span",
        name=f"review.{run_kind}",
        metadata={"document_id": document_id},
    ) as span:
        try:
            yield span
        finally:
            client.flush()


def usage_details(response_usage: Any) -> dict[str, int]:
    """
    Maps an Anthropic Usage object to the input/output/total keys Langfuse's
    usage_details expects (the same convention Langfuse's own LangChain
    integration uses — see langfuse.langchain.CallbackHandler._parse_usage_model).
    """
    input_tokens = getattr(response_usage, "input_tokens", 0) or 0
    output_tokens = getattr(response_usage, "output_tokens", 0) or 0
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": input_tokens + output_tokens,
    }
