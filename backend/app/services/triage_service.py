"""Service layer orchestrating the PR triage lifecycle.

This sits between the HTTP layer (routes) and the LangGraph agent,
persisting PR and report state to the database.
"""

import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.triage import TriageState, get_triage_graph
from app.engine.queries import get_indexer
from app.github.client import GitHubClient
from app.models.repo import (
    PRClassification,
    PullRequest,
    Repository,
    TriageReport,
    TriageStatus,
)

logger = structlog.get_logger()


class TriageService:
    """Manages the full PR triage lifecycle."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ─── Enqueue ──────────────────────────────────────────────

    async def enqueue_triage(self, repo_full_name: str, pr_number: int) -> None:
        """Called by webhook handler. Creates PR record and starts triage."""
        client = GitHubClient()
        gh_pr = client.get_pr(repo_full_name, pr_number)

        # Find or create the repository record
        result = await self.session.execute(
            select(Repository).where(Repository.full_name == repo_full_name)
        )
        repo = result.scalar_one_or_none()

        if repo is None:
            gh_repo = client.get_repo(repo_full_name)
            repo = Repository(
                github_id=gh_repo.id,
                full_name=repo_full_name,
                owner=gh_repo.owner.login,
                name=gh_repo.name,
                description=gh_repo.description,
                default_branch=gh_repo.default_branch,
                language=gh_repo.language,
                stars=gh_repo.stargazers_count,
                status="ready",
                indexed_at=datetime.now(timezone.utc),
            )
            self.session.add(repo)
            await self.session.flush()

        # Find or create the PR record
        result = await self.session.execute(
            select(PullRequest).where(
                PullRequest.repository_id == repo.id,
                PullRequest.github_pr_id == gh_pr.id,
            )
        )
        pr = result.scalar_one_or_none()

        if pr is None:
            pr = PullRequest(
                repository_id=repo.id,
                github_pr_id=gh_pr.id,
                number=pr_number,
                title=gh_pr.title,
                body=gh_pr.body or "",
                author=gh_pr.user.login,
                author_avatar=gh_pr.user.avatar_url,
                base_branch=gh_pr.base.ref,
                head_branch=gh_pr.head.ref,
                state=gh_pr.state,
                files_changed=gh_pr.changed_files,
                additions=gh_pr.additions,
                deletions=gh_pr.deletions,
                created_at=gh_pr.created_at,
                updated_at=gh_pr.updated_at,
                triage_status=TriageStatus.IN_PROGRESS,
            )
            self.session.add(pr)
            await self.session.flush()

        # Run the triage pipeline
        await self.run_triage_pipeline(pr, repo, gh_pr, client)

    # ─── Pipeline runner ──────────────────────────────────────

    async def run_triage_pipeline(
        self,
        pr: PullRequest,
        repo: Repository,
        gh_pr,
        client: GitHubClient,
    ) -> None:
        """Execute the LangGraph triage pipeline."""
        start_time = time.time()

        # Get diff and file list from GitHub
        files = client.get_pr_files(repo.full_name, pr.number)
        files_changed = [f.filename for f in files]
        diff_text = client.get_pr_diff(repo.full_name, pr.number)

        # Build initial state
        initial_state: TriageState = {
            "repo_full_name": repo.full_name,
            "pr_number": pr.number,
            "pr_title": pr.title,
            "pr_body": pr.body or "",
            "pr_author": pr.author,
            "diff_text": diff_text,
            "files_changed": files_changed,
            "classification": "",
            "classification_confidence": 0.0,
            "classification_rationale": "",
            "blast_radius_score": 0.0,
            "affected_modules": [],
            "affected_callers": [],
            "report_summary": "",
            "suggested_action": "",
            "suggested_reviewer": "",
            "suggested_labels": [],
            "findings": [],
            "needs_human": False,
            "approved": False,
            "moderation_notes": "",
            "error": None,
        }

        graph = get_triage_graph()
        config = {"configurable": {"thread_id": str(pr.id)}}

        try:
            # Run up to the interrupt point (before 'action')
            final_state = await graph.ainvoke(initial_state, config)

            # Persist the triage report
            report = TriageReport(
                pull_request_id=pr.id,
                classification=PRClassification(final_state["classification"]),
                classification_rationale=final_state["classification_rationale"],
                classification_confidence=final_state["classification_confidence"],
                blast_radius_score=final_state["blast_radius_score"],
                affected_modules=final_state["affected_modules"],
                affected_callers=final_state["affected_callers"],
                findings=final_state.get("findings", []),
                summary=final_state["report_summary"],
                suggested_action=final_state["suggested_action"],
                suggested_reviewer=final_state["suggested_reviewer"],
                agent_version="0.1.0",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )
            self.session.add(report)

            # Update PR status
            pr.triage_status = TriageStatus.AWAITING_APPROVAL
            pr.classification = PRClassification(final_state["classification"])
            pr.classification_confidence = final_state["classification_confidence"]
            await self.session.flush()

            logger.info(
                "Triage pipeline complete, awaiting approval",
                repo=repo.full_name,
                pr=pr.number,
                classification=final_state["classification"],
                elapsed_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("Triage pipeline failed", error=str(e))
            pr.triage_status = TriageStatus.PENDING

    # ─── Human approval ───────────────────────────────────────

    async def approve_report(
        self,
        report_id: uuid.UUID,
        approved_by: str,
        notes: str = "",
    ) -> None:
        """Human approves a triage report and posts it to GitHub."""
        result = await self.session.execute(
            select(TriageReport).where(TriageReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise ValueError(f"Report {report_id} not found")

        report.approved = True
        report.approved_by = approved_by
        report.approved_at = datetime.now(timezone.utc)
        report.moderation_notes = notes

        # Get the PR and repo
        result = await self.session.execute(
            select(PullRequest).where(PullRequest.id == report.pull_request_id)
        )
        pr = result.scalar_one_or_none()
        result = await self.session.execute(
            select(Repository).where(Repository.id == pr.repository_id)
        )
        repo = result.scalar_one_or_none()

        # Resume the LangGraph run with approved=True
        graph = get_triage_graph()
        config = {"configurable": {"thread_id": str(pr.id)}}

        try:
            await graph.ainvoke(
                None,
                config,
            )
        except Exception as e:
            logger.error("Graph resume failed", error=str(e))

        # Post the comment manually (in case graph resume was a no-op)
        try:
            client = GitHubClient()
            comment_body = self._build_comment_from_report(report, pr)
            client.post_pr_comment(repo.full_name, pr.number, comment_body)
            if report.suggested_labels if hasattr(report, "suggested_labels") else False:
                # Pull labels from the report (they live on the report we created)
                pass
            report.posted_to_github = True
            report.posted_at = datetime.now(timezone.utc)
            pr.triage_status = TriageStatus.POSTED
        except Exception as e:
            logger.error("Failed to post to GitHub", error=str(e))
            pr.triage_status = TriageStatus.APPROVED

    async def reject_report(
        self,
        report_id: uuid.UUID,
        rejected_by: str,
        notes: str = "",
    ) -> None:
        """Human rejects a triage report (do not post to GitHub)."""
        result = await self.session.execute(
            select(TriageReport).where(TriageReport.id == report_id)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise ValueError(f"Report {report_id} not found")

        report.approved = False
        report.approved_by = rejected_by
        report.approved_at = datetime.now(timezone.utc)
        report.moderation_notes = notes

        result = await self.session.execute(
            select(PullRequest).where(PullRequest.id == report.pull_request_id)
        )
        pr = result.scalar_one_or_none()
        if pr:
            pr.triage_status = TriageStatus.REJECTED

    # ─── Helpers ──────────────────────────────────────────────

    def _build_comment_from_report(self, report: TriageReport, pr: PullRequest) -> str:
        """Format a TriageReport row as a GitHub comment body."""
        labels_md = " ".join(f"`{l}`" for l in (report.affected_modules or [])[:3] if isinstance(l, str))
        return f"""{report.summary}

---
<details>
<summary>🤖 Pulse Triage Metadata</summary>

- **Classification:** `{report.classification.value}` (confidence: {report.classification_confidence:.0%})
- **Blast Radius Score:** {report.blast_radius_score or 0:.0%}
- **Suggested Action:** `{report.suggested_action or 'comment'}`
- **Suggested Reviewer:** {report.suggested_reviewer or 'Not specified'}

> This report was generated by [Pulse](https://github.com/rawdripcollective-codec/pulse).
</details>
"""
