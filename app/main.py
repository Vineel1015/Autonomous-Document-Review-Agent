"""
FastAPI app assembly: lifespan (DB pool + LangGraph checkpointer
startup/shutdown) + routers.

Windows note: on Windows, run the app via `python main.py` (root entrypoint),
not `uvicorn main:app` / `fastapi dev`. Those create uvicorn's event loop
(ProactorEventLoop) before this module is even imported, which is too late
to switch to the Selector loop psycopg's async mode needs — see main.py's
docstring for the full explanation. Setting the policy here wouldn't help,
so this module doesn't try.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import connect_db, disconnect_db
from app.graph.checkpointer import connect_checkpointer, disconnect_checkpointer
from app.routers import companies, documents, metrics, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await connect_checkpointer()
    yield
    await disconnect_checkpointer()
    await disconnect_db()


app = FastAPI(title="AI Document Review Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(reviews.router)
app.include_router(companies.router)
app.include_router(metrics.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
