"""
Async Postgres connection pool (asyncpg) + a FastAPI dependency to borrow a
connection per request.

Lifecycle: connect_db() is called once in app.main's lifespan on startup,
disconnect_db() on shutdown. Don't call these from request handlers.
"""
import asyncpg

from app.config import get_settings

_pool: asyncpg.Pool | None = None


async def connect_db() -> asyncpg.Pool:
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)
    return _pool


async def disconnect_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — is the app lifespan running?")
    return _pool


async def get_db():
    """FastAPI dependency: `db: asyncpg.Connection = Depends(get_db)`."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
