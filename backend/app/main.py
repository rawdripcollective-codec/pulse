"""Pulse FastAPI application entry point.

Wires the lifespan handler, CORS middleware, and all routers.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routes import api, dashboard, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle.

    On startup: ensure all tables exist (production uses Alembic, but
    create_all is a safe no-op if tables already exist).
    On shutdown: dispose the async engine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Agentic PR Triage & Review for Open-Source Maintainers",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow the Vite dev server (5173) and the docker-compose mapped port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(api.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api/dashboard")
app.include_router(ws.router, prefix="/ws")


@app.get("/health")
async def health() -> dict:
    """Liveness probe — used by Docker HEALTHCHECK and uptime monitors."""
    return {"status": "ok", "version": settings.app_version, "app": settings.app_name}


@app.get("/")
async def root() -> dict:
    """Root endpoint — quick sanity check."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
