"""Pulse REST API endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.github.webhooks import handle_pull_request_event, verify_webhook_signature
from app.models.repo import (
    PullRequest,
    Repository,
    TriageReport,
    TriageStatus,
)
from app.schemas.pr import (
    ApproveReportRequest,
    PRDetail,
    PRSummary,
    RejectReportRequest,
    RepoSummary,
    TriageReportDetail,
)
from app.services.triage_service import TriageService

logger = structlog.get_logger()
router = APIRouter()


# ─── GitHub App install callback ──────────────────────────────

@router.post("/github/app/install")
async def github_app_install_callback(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle the GitHub App installation callback.

    GitHub POSTs a JSON body here after the org owner clicks "Install" on
    the App install page. The body contains `installation.id` and the
    `account` that installed it. We persist a User record (audit anchor)
    and pre-warm the installation token cache.

    Body shape (relevant fields):
        {
          "installation": {"id": 12345, "account": {"id": ..., "login": ..., "type": "User"|"Organization"}},
          "repositories": [...]
        }
    """
    from app.github.app import (
        fetch_installation_token,
        upsert_installation_owner,
    )

    installation = payload.get("installation", {})
    installation_id = installation.get("id")
    account = installation.get("account", {})

    if not installation_id or not account:
        raise HTTPException(
            status_code=400,
            detail="Invalid installation callback: missing installation.id or account",
        )

    try:
        # Pre-warm the token cache
        await fetch_installation_token(installation_id)
        # Persist the owner using the request's DB session so the
        # transaction is visible to the rest of the request.
        await upsert_installation_owner(
            installation_id=installation_id,
            account_login=account.get("login", "unknown"),
            account_id=account.get("id", 0),
            account_type=account.get("type", "User"),
            session=db,
        )
        await db.commit()
    except Exception as exc:
        logger.error("App install callback failed", error=str(exc))
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Install callback failed: {exc}",
        )

    return {
        "status": "installed",
        "installation_id": installation_id,
        "account": account.get("login"),
    }


@router.get("/github/app/installations")
async def list_app_installations() -> dict:
    """List all known installations (from the in-memory token cache).

    For a fuller view (with metadata), join against the User table in your
    frontend. This endpoint exists primarily to verify the App is wired up.
    """
    from app.github.app import get_installation_token_cache

    cache = get_installation_token_cache()
    return {
        "active_installations": [
            {
                "installation_id": tid,
                "expires_at": tok.expires_at,
            }
            for tid, tok in cache._cache.items()
        ],
    }


# ─── Repositories ─────────────────────────────────────────────

@router.get("/repos", response_model=list[RepoSummary])
async def list_repos(db: AsyncSession = Depends(get_db)) -> list[RepoSummary]:
    """List all connected repositories."""
    result = await db.execute(
        select(Repository).order_by(Repository.updated_at.desc())
    )
    repos = result.scalars().all()

    summaries: list[RepoSummary] = []
    for repo in repos:
        pr_count = await db.scalar(
            select(func.count(PullRequest.id)).where(
                PullRequest.repository_id == repo.id,
                PullRequest.state == "open",
            )
        )
        triage_count = await db.scalar(
            select(func.count(TriageReport.id)).where(
                TriageReport.pull_request_id.in_(
                    select(PullRequest.id).where(
                        PullRequest.repository_id == repo.id
                    )
                ),
                TriageReport.approved.is_(None),
            )
        )
        summaries.append(
            RepoSummary(
                id=repo.id,
                full_name=repo.full_name,
                description=repo.description,
                language=repo.language,
                stars=repo.stars,
                status=repo.status.value,
                indexed_at=repo.indexed_at,
                open_prs=pr_count or 0,
                pending_triages=triage_count or 0,
            )
        )

    return summaries


@router.post("/repos/{full_name:path}/reindex")
async def reindex_repo(full_name: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Trigger re-indexing of a repository."""
    result = await db.execute(
        select(Repository).where(Repository.full_name == full_name)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")

    repo.status = "indexing"
    await db.flush()

    from app.services.index_service import IndexService

    service = IndexService(db)
    await service.index_repository(repo)

    return {"status": "indexing", "repo": full_name}


# ─── Pull Requests ────────────────────────────────────────────

@router.get("/prs", response_model=list[PRSummary])
async def list_prs(
    repo_full_name: str | None = None,
    triage_status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PRSummary]:
    """List pull requests, optionally filtered by repo and triage status."""
    query = select(PullRequest)

    if repo_full_name:
        repo_result = await db.execute(
            select(Repository).where(Repository.full_name == repo_full_name)
        )
        repo = repo_result.scalar_one_or_none()
        if repo is None:
            return []
        query = query.where(PullRequest.repository_id == repo.id)

    if triage_status:
        query = query.where(PullRequest.triage_status == TriageStatus(triage_status))

    query = query.order_by(PullRequest.created_at.desc()).limit(50)
    result = await db.execute(query)
    prs = result.scalars().all()

    summaries: list[PRSummary] = []
    for pr in prs:
        repo_result = await db.execute(
            select(Repository.full_name).where(Repository.id == pr.repository_id)
        )
        repo_name = repo_result.scalar_one_or_none()

        summaries.append(
            PRSummary(
                id=pr.id,
                number=pr.number,
                title=pr.title,
                author=pr.author,
                author_avatar=pr.author_avatar,
                files_changed=pr.files_changed,
                additions=pr.additions,
                deletions=pr.deletions,
                classification=pr.classification.value if pr.classification else None,
                classification_confidence=pr.classification_confidence,
                triage_status=pr.triage_status.value,
                created_at=pr.created_at,
                repo_full_name=repo_name or "",
            )
        )

    return summaries


@router.get("/prs/{pr_id}", response_model=PRDetail)
async def get_pr_detail(pr_id: UUID, db: AsyncSession = Depends(get_db)) -> PRDetail:
    """Get detailed information about a specific PR with all triage reports."""
    result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
    pr = result.scalar_one_or_none()
    if pr is None:
        raise HTTPException(status_code=404, detail="PR not found")

    repo_result = await db.execute(
        select(Repository.full_name).where(Repository.id == pr.repository_id)
    )
    repo_name = repo_result.scalar_one_or_none()

    reports_result = await db.execute(
        select(TriageReport)
        .where(TriageReport.pull_request_id == pr.id)
        .order_by(TriageReport.created_at.desc())
    )
    reports = reports_result.scalars().all()

    return PRDetail(
        id=pr.id,
        number=pr.number,
        title=pr.title,
        author=pr.author,
        author_avatar=pr.author_avatar,
        body=pr.body,
        files_changed=pr.files_changed,
        additions=pr.additions,
        deletions=pr.deletions,
        base_branch=pr.base_branch,
        head_branch=pr.head_branch,
        state=pr.state,
        classification=pr.classification.value if pr.classification else None,
        classification_confidence=pr.classification_confidence,
        triage_status=pr.triage_status.value,
        created_at=pr.created_at,
        updated_at=pr.updated_at,
        repo_full_name=repo_name or "",
        triage_reports=[
            TriageReportDetail(
                id=r.id,
                classification=r.classification.value,
                classification_rationale=r.classification_rationale,
                classification_confidence=r.classification_confidence,
                blast_radius_score=r.blast_radius_score,
                affected_modules=r.affected_modules or [],
                summary=r.summary,
                suggested_action=r.suggested_action,
                suggested_reviewer=r.suggested_reviewer,
                approved=r.approved,
                approved_by=r.approved_by,
                approved_at=r.approved_at,
                posted_to_github=r.posted_to_github,
                processing_time_ms=r.processing_time_ms,
                created_at=r.created_at,
            )
            for r in reports
        ],
    )


# ─── Triage Approval ──────────────────────────────────────────

@router.post("/triage/approve")
async def approve_triage(
    req: ApproveReportRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve a triage report and post it to GitHub."""
    service = TriageService(db)
    await service.approve_report(req.report_id, approved_by="user", notes=req.notes)
    return {"status": "approved", "report_id": str(req.report_id)}


@router.post("/triage/reject")
async def reject_triage(
    req: RejectReportRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reject a triage report (do not post to GitHub)."""
    service = TriageService(db)
    await service.reject_report(req.report_id, rejected_by="user", notes=req.notes)
    return {"status": "rejected", "report_id": str(req.report_id)}


# ─── Webhook Receiver ─────────────────────────────────────────

@router.post("/webhook/github")
async def github_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Receive GitHub webhook events."""
    await verify_webhook_signature(request)

    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    await handle_pull_request_event(event, payload)

    return {"status": "received"}
