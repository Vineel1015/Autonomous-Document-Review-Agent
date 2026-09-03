"""
Entrypoint — kept at the repo root so `uvicorn main:app` / `fastapi dev main.py`
keep working for the `app` object itself. The real app lives in app/main.py.

On Windows, run this file directly (`python main.py` / `uv run python main.py`)
rather than the `uvicorn main:app` CLI or `fastapi dev`. Both go through
uvicorn's default loop factory, which explicitly returns ProactorEventLoop on
Windows for a normal single-process run (see uvicorn/loops/asyncio.py) — and
psycopg's async mode (used by the LangGraph Postgres checkpointer, see
app/graph/checkpointer.py) cannot run under it.

Setting the ambient asyncio event loop policy does NOT fix this — uvicorn
resolves its own loop_factory and passes it explicitly to its internal
asyncio.run(..., loop_factory=...), which overrides whatever policy is
active (confirmed by reading uvicorn/server.py and uvicorn/config.py; this
isn't a documented option, just how the internals happen to work). The
actual fix: pass our own loop factory to uvicorn.run(loop=...) below —
uvicorn accepts any non-string zero-arg callable here, not just its built-in
"asyncio"/"uvloop"/"auto" names.
"""
import asyncio
import sys

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    loop = asyncio.SelectorEventLoop if sys.platform == "win32" else "auto"
    uvicorn.run(app, host="0.0.0.0", port=8000, loop=loop)
