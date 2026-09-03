"""
Lifecycle for the shared Postgres checkpointer that makes interrupt()/resume
durable across process restarts, not just an in-memory wait.

AsyncPostgresSaver.from_conn_string is an async context manager; this module
keeps one open for the life of the process (an app or a script) via
AsyncExitStack, mirroring app/db.py's connect/disconnect pattern for the
asyncpg pool. connect_checkpointer()/disconnect_checkpointer() are called
once at startup/shutdown (see app/main.py's lifespan, or a script's own
main()) — don't call these from request handlers or node functions.
"""
from contextlib import AsyncExitStack

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.config import get_settings
from app.graph.extraction import FilingContext
from app.models.extraction import ExtractedFinding, ExtractedMetric
from app.models.schemas import (
    FilingType,
    FindingCategory,
    FiscalPeriod,
    MetricName,
    MetricPeriodType,
    MetricUnit,
    Severity,
)

# Every custom (non-builtin) type that can end up inside ReviewState (see
# app/graph/state.py) — the checkpointer serializes state to Postgres on
# every step, and without this explicit allowlist it falls back to a
# permissive-with-warning mode that a future langgraph-checkpoint release
# will turn into a hard block (LANGGRAPH_STRICT_MSGPACK). Passing classes
# directly here is fine — JsonPlusSerializer normalizes them to
# (module, name) pairs itself.
_ALLOWED_STATE_TYPES = [
    FilingContext,
    ExtractedMetric,
    ExtractedFinding,
    FilingType,
    FiscalPeriod,
    FindingCategory,
    MetricName,
    MetricUnit,
    MetricPeriodType,
    Severity,
]

_stack: AsyncExitStack | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def connect_checkpointer(run_setup: bool = True) -> AsyncPostgresSaver:
    global _stack, _checkpointer
    settings = get_settings()
    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_STATE_TYPES)
    _stack = AsyncExitStack()
    _checkpointer = await _stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(settings.database_url, serde=serde)
    )
    if run_setup:
        # Idempotent (CREATE TABLE IF NOT EXISTS-style) — creates the
        # checkpoints/checkpoint_blobs/checkpoint_writes tables on first run.
        await _checkpointer.setup()
    return _checkpointer


async def disconnect_checkpointer() -> None:
    global _stack, _checkpointer
    if _stack is not None:
        await _stack.aclose()
        _stack = None
        _checkpointer = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized — call connect_checkpointer() first")
    return _checkpointer
