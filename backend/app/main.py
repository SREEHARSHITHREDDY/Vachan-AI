"""
FastAPI application entry point.

CORS is wide open (allow_origins=["*"]) — acceptable ONLY for the demo
scope, where the frontend is a static HTML file opened locally and there's
no real user data at stake beyond the demo database. This is explicitly
NOT production-appropriate and must be locked down before any real
deployment — flagged here rather than silently shipped, consistent with
how every other demo-scope shortcut in this project has been documented.

init_db() runs on startup so the SQLite file/tables exist before the
first request — acceptable for a single-instance demo; a real deployment
would use a proper migration tool instead (per Database Design doc,
Section 4.7's "full migration tooling" deferred item).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db
from app.routers.commitments import router as commitments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="VachanAI (Demo Scope)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo scope only — see module docstring
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(commitments_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
