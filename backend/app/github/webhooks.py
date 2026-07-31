"""GitHub webhook receiver and signature verification."""

import hashlib
import hmac

import structlog
from fastapi import HTTPException, Request, status

from app.config import settings

logger = structlog.get_logger()


async def verify_webhook_signature(request: Request) -> bytes:
    """Verify the `X-Hub-Signature-256` header on a GitHub webhook.

    Returns the raw request body on success; raises 401 on failure.
    """
    if not settings.github_webhook_secret:
        logger.warning(
            "GITHUB_WEBHOOK_SECRET is not set — skipping signature verification"
        )
        return await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed signature header",
        )

    body = await request.body()
    expected = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    return body


async def handle_pull_request_event(event: str, payload: dict) -> None:
    """Dispatch a GitHub webhook event to the appropriate handler.

    Currently supports:
      - `pull_request` (opened, synchronize, reopened, edited)
      - `pull_request_review` (submitted, edited)
    """
    logger.info(
        "Received GitHub webhook",
        event=event,
        action=payload.get("action"),
    )

    if event == "pull_request":
        action = payload.get("action")
        if action not in ("opened", "synchronize", "reopened", "edited"):
            return
        await _handle_pr_opened_or_updated(payload)

    elif event == "ping":
        # GitHub sends a ping when you first set up the webhook
        logger.info("GitHub webhook ping received")

    # Other event types ignored for now (PR review, push, etc.)


async def _handle_pr_opened_or_updated(payload: dict) -> None:
    """Enqueue a new or updated PR for triage."""
    # Defer imports to avoid circular dependencies at module load time
    from app.database import async_session_factory
    from app.services.triage_service import TriageService

    repo = payload.get("repository", {})
    pr = payload.get("pull_request", {})

    full_name = repo.get("full_name")
    pr_number = pr.get("number")
    if not full_name or not pr_number:
        logger.warning("Webhook payload missing repo or PR info", payload=payload)
        return

    async with async_session_factory() as session:
        try:
            service = TriageService(session)
            await service.enqueue_triage(full_name, pr_number)
        except Exception as exc:
            logger.error(
                "Triage enqueue failed",
                repo=full_name,
                pr=pr_number,
                error=str(exc),
            )
