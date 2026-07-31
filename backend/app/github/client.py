"""GitHub REST API client wrapper with token management.

Supports three auth modes (resolved in order):
1. User OAuth token (`user_token`) — most common, for maintainer actions
2. GitHub App installation token (`installation_id`) — for org-wide reads
3. Anonymous (rate-limited, unauthenticated) — only for public reads
"""

from typing import Optional

import requests
import structlog
from github import Github, GithubIntegration
from github.PullRequest import PullRequest as GhPullRequest

from app.config import settings

logger = structlog.get_logger()


class GitHubClient:
    """Wraps PyGithub with app-installation token and OAuth token support."""

    def __init__(
        self,
        installation_id: Optional[int] = None,
        user_token: Optional[str] = None,
    ):
        self._installation_id = installation_id
        self._user_token = user_token
        self._client: Optional[Github] = None

    # ─── Client factory ───────────────────────────────────────

    @property
    def client(self) -> Github:
        if self._client is not None:
            return self._client

        if self._user_token:
            self._client = Github(self._user_token)
        elif self._installation_id and settings.github_app_id:
            integration = GithubIntegration(
                settings.github_app_id,
                settings.github_app_private_key,
            )
            token = integration.get_access_token(self._installation_id)
            self._client = Github(token.token)
        else:
            # Anonymous — rate-limited, public reads only
            self._client = Github()

        return self._client

    # ─── Repository operations ────────────────────────────────

    def get_repo(self, full_name: str):
        """Get a repository by full name (owner/repo)."""
        return self.client.get_repo(full_name)

    # ─── Pull request operations ──────────────────────────────

    def get_pr(self, full_name: str, pr_number: int) -> GhPullRequest:
        """Get a specific pull request."""
        return self.get_repo(full_name).get_pull(pr_number)

    def get_open_prs(self, full_name: str, limit: int = 50):
        """Get open pull requests for a repository."""
        return list(
            self.get_repo(full_name)
            .get_pulls(state="open", sort="created", direction="desc")[:limit]
        )

    def get_pr_files(self, full_name: str, pr_number: int):
        """Get the list of files changed in a PR."""
        return list(self.get_pr(full_name, pr_number).get_files())

    def get_pr_diff(self, full_name: str, pr_number: int) -> str:
        """Get the unified diff for a PR.

        PyGithub does not expose `diff` directly, so we fetch from the
        raw diff URL with proper auth.
        """
        pr = self.get_pr(full_name, pr_number)
        headers = {}
        if self._user_token:
            headers["Authorization"] = f"token {self._user_token}"
        resp = requests.get(pr.diff_url, headers=headers)
        resp.raise_for_status()
        return resp.text

    def post_pr_comment(self, full_name: str, pr_number: int, body: str) -> None:
        """Post a comment on a pull request."""
        pr = self.get_pr(full_name, pr_number)
        pr.create_issue_comment(body)
        logger.info("Posted PR comment", repo=full_name, pr=pr_number)

    def add_labels(
        self, full_name: str, pr_number: int, labels: list[str]
    ) -> None:
        """Add labels to a pull request (creates labels if they don't exist)."""
        if not labels:
            return
        pr = self.get_pr(full_name, pr_number)
        repo = self.get_repo(full_name)
        # Ensure each label exists on the repo
        existing = {l.name for l in repo.get_labels()}
        for label in labels:
            if label not in existing:
                try:
                    repo.create_label(name=label, color="ededed")
                except Exception:
                    pass  # Label may have been created concurrently
        pr.add_to_labels(*labels)
        logger.info(
            "Added labels to PR", repo=full_name, pr=pr_number, labels=labels
        )

    def get_user(self, login: str):
        """Get a GitHub user by login."""
        return self.client.get_user(login)
