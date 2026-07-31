"""Seed the Pulse database with demo data.

Run from the backend directory:
    python -m scripts.seed_data

This is intended for local development and demo purposes only.
"""

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session_factory
from app.models.repo import (
    PRClassification,
    PullRequest,
    RepoStatus,
    Repository,
    TriageReport,
    TriageStatus,
)


DEMO_REPO = {
    "github_id": 999999,
    "full_name": "demo/example",
    "owner": "demo",
    "name": "example",
    "description": "Demo repository for Pulse testing",
    "default_branch": "main",
    "language": "python",
    "stars": 42,
    "status": RepoStatus.READY,
    "indexed_at": datetime.now(timezone.utc),
}

DEMO_PRS = [
    {
        "github_pr_id": 101,
        "number": 42,
        "title": "Add retry logic to webhook handler",
        "body": "Implements exponential backoff for failed webhook deliveries.",
        "author": "alice",
        "author_avatar": "https://github.com/alice.png",
        "base_branch": "main",
        "head_branch": "feature/retry",
        "state": "open",
        "files_changed": 3,
        "additions": 87,
        "deletions": 12,
        "classification": PRClassification.HUMAN_FIRST,
        "classification_confidence": 0.92,
        "triage_status": TriageStatus.AWAITING_APPROVAL,
    },
    {
        "github_pr_id": 102,
        "number": 43,
        "title": "fix typo in README",
        "body": "",
        "author": "bob",
        "author_avatar": None,
        "base_branch": "main",
        "head_branch": "fix-readme",
        "state": "open",
        "files_changed": 1,
        "additions": 2,
        "deletions": 2,
        "classification": PRClassification.TRIVIAL,
        "classification_confidence": 0.98,
        "triage_status": TriageStatus.AWAITING_APPROVAL,
    },
    {
        "github_pr_id": 103,
        "number": 44,
        "title": "Here's an implementation of auth refactor",
        "body": "I have created a comprehensive refactor...",
        "author": "carol",
        "author_avatar": None,
        "base_branch": "main",
        "head_branch": "ai-attempt",
        "state": "open",
        "files_changed": 12,
        "additions": 540,
        "deletions": 320,
        "classification": PRClassification.AI_SLOP,
        "classification_confidence": 0.78,
        "triage_status": TriageStatus.AWAITING_APPROVAL,
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        # Create or update demo repo
        result = await session.execute(
            select(Repository).where(Repository.full_name == DEMO_REPO["full_name"])
        )
        repo = result.scalar_one_or_none()
        if repo is None:
            repo = Repository(**DEMO_REPO)
            session.add(repo)
            await session.flush()
            print(f"✓ Created demo repo: {repo.full_name}")
        else:
            print(f"→ Demo repo exists: {repo.full_name}")

        # Create demo PRs
        for pr_data in DEMO_PRS:
            result = await session.execute(
                select(PullRequest).where(
                    PullRequest.repository_id == repo.id,
                    PullRequest.github_pr_id == pr_data["github_pr_id"],
                )
            )
            pr = result.scalar_one_or_none()
            if pr is None:
                pr = PullRequest(
                    repository_id=repo.id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    **pr_data,
                )
                session.add(pr)
                await session.flush()
                print(f"  ✓ Created PR #{pr.number}: {pr.title}")
            else:
                print(f"  → PR #{pr.number} exists")

        await session.commit()
        print("\n✓ Seed complete")


if __name__ == "__main__":
    asyncio.run(seed())
