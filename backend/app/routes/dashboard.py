"""Dashboard-specific endpoints: stats, semantic search, blast radius queries."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.queries import (
    get_blast_radius,
    get_callers,
    get_high_risk_files,
    semantic_search,
)
from app.models.repo import PullRequest, Repository, TriageReport, TriageStatus
from app.schemas.triage import TriageStats

logger = structlog.get_logger()
router = APIRouter()


@router.get("/stats", response_model=TriageStats)
async def get_stats(db: AsyncSession = Depends(get_db)) -> TriageStats:
    """Aggregated stats for the dashboard stats bar."""
    total_repos = await db.scalar(select(func.count(Repository.id))) or 0
    open_prs = await db.scalar(
        select(func.count(PullRequest.id)).where(PullRequest.state == "open")
    ) or 0
    awaiting = await db.scalar(
        select(func.count(TriageReport.id)).where(
            TriageReport.approved.is_(None)
        )
    ) or 0
    in_progress = await db.scalar(
        select(func.count(PullRequest.id)).where(
            PullRequest.triage_status == TriageStatus.IN_PROGRESS
        )
    ) or 0
    posted_today = await db.scalar(
        select(func.count(TriageReport.id)).where(
            TriageReport.posted_to_github.is_(True)
        )
    ) or 0
    avg_ms = await db.scalar(
        select(func.avg(TriageReport.processing_time_ms)).where(
            TriageReport.processing_time_ms.is_not(None)
        )
    )

    return TriageStats(
        total_repos=total_repos,
        open_prs=open_prs,
        awaiting_approval=awaiting,
        in_progress=in_progress,
        posted_today=posted_today,
        avg_processing_time_ms=avg_ms,
    )


@router.get("/search")
async def semantic_code_search(
    repo: str = Query(..., description="Full repo name, e.g. owner/repo"),
    q: str = Query(..., description="Natural-language search query"),
    top_k: int = Query(10, ge=1, le=50),
) -> dict:
    """Run a semantic code search over an indexed repository."""
    results = await semantic_search(repo, q, top_k=top_k)
    return {"query": q, "results": results}


@router.get("/blast-radius")
async def file_blast_radius(
    repo: str = Query(...),
    file: str = Query(...),
) -> dict:
    """Return the blast radius (downstream callers) for a file."""
    affected = get_blast_radius(repo, file)
    return {"file": file, "affected": affected, "count": len(affected)}


@router.get("/high-risk-files")
async def high_risk_files(
    repo: str = Query(...),
    top_n: int = Query(10, ge=1, le=50),
) -> dict:
    """Return the top N highest-centrality files in the indexed repo."""
    files = get_high_risk_files(repo, top_n=top_n)
    return {"repo": repo, "files": files}
