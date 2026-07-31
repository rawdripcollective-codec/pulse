"""Service layer for repository indexing.

Coordinates between the GitHub client, the file system clone, and the
SemanticIndexer. Triggered when a repo is first connected and on
re-index requests.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.indexer import SemanticIndexer
from app.engine.queries import invalidate_indexer
from app.github.client import GitHubClient
from app.models.repo import Repository, RepoStatus

logger = structlog.get_logger()


class IndexService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def index_repository(self, repo: Repository) -> dict:
        """Clone the repo to a temp dir, index it, then persist the summary."""
        client = GitHubClient()
        gh_repo = client.get_repo(repo.full_name)

        clone_dir = Path(tempfile.mkdtemp(prefix="pulse-index-"))
        try:
            logger.info("Cloning repo", repo=repo.full_name, path=str(clone_dir))
            # Use git CLI for simplicity and to avoid embedding a git library
            import subprocess

            clone_url = gh_repo.clone_url
            # Inject auth if available
            if settings.github_app_private_key and settings.github_app_id:
                # App installation token would go here in production
                pass
            # subprocess.run is blocking — we use it in a thread to avoid
            # blocking the event loop during the clone.
            await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", "--depth=1", clone_url, str(clone_dir)],
                check=True,
                capture_output=True,
                timeout=300,
            )

            # Run the indexer
            indexer = SemanticIndexer(repo.full_name, clone_dir)
            summary = await indexer.index_repository()

            # Persist the graph summary
            repo.status = RepoStatus.READY
            repo.indexed_at = repo.indexed_at or __import__("datetime").datetime.utcnow()
            repo.graph_summary = indexer.graph.to_dict()
            await self.session.flush()

            return summary
        except Exception as e:
            logger.error("Indexing failed", repo=repo.full_name, error=str(e))
            repo.status = RepoStatus.ERROR
            repo.index_error = str(e)
            await self.session.flush()
            raise
        finally:
            # Clean up the cloned directory
            invalidate_indexer(repo.full_name)
            shutil.rmtree(clone_dir, ignore_errors=True)
