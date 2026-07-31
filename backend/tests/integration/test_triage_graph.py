"""Integration test for the full PR triage LangGraph pipeline.

This exercises the real LangGraph state machine with:
- a stubbed `acompletion` (LLM)
- a stubbed `embedding` (no real API call)
- a fake GitHub client
- the real `TreeSitter` parser and the real `PropertyGraph`

It verifies the end-to-end flow:
    classify -> blast_radius -> generate_report -> (interrupts before action)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.triage import TriageState, build_triage_graph, get_triage_graph
from app.engine.queries import _indexers
from app.models.repo import (
    PRClassification,
    RepoStatus,
    Repository,
    TriageStatus,
)
from datetime import datetime, timezone
import uuid


def make_acompletion_mock(content: str):
    """Build a coroutine function that, when awaited, returns a MagicMock
    mimicking a litellm acompletion response with the given content.
    """
    async def _fake_acompletion(*args, **kwargs):
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = content
        return response
    return _fake_acompletion


def make_embedding_side_effect(dim: int = 8):
    """Create an async stub mimicking litellm.embedding() — returns zero vectors."""
    async def _fake(*args, **kwargs):
        inputs = kwargs.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = [{"embedding": [0.0] * dim} for _ in inputs]
        response = MagicMock()
        response.data = data
        return response
    return _fake


@pytest.mark.asyncio
class TestTriageGraphEndToEnd:
    """Drive the full graph and verify the final state shape."""

    async def test_runs_through_classify_to_report(self, tmp_path, monkeypatch):
        # 1) Set up an in-memory indexer with a tiny repo
        from app.engine.indexer import SemanticIndexer
        from app.engine.parser import CodeParser
        from app.engine.graph import PropertyGraph

        # Create a small Python file to index
        repo_dir = tmp_path / "acme_widget"
        repo_dir.mkdir()
        (repo_dir / "auth.py").write_text(
            "def check_password(user, pwd):\n    return user == 'admin' and pwd == 'secret'\n"
        )
        (repo_dir / "main.py").write_text(
            "from auth import check_password\n\ndef login(u, p):\n    return check_password(u, p)\n"
        )

        # 2) Build the indexer against this directory
        indexer = SemanticIndexer("acme/widget", repo_dir)
        # Patch embedding so we don't hit any real API
        monkeypatch.setattr("litellm.embedding", make_embedding_side_effect())
        await indexer.index_repository()

        # 3) Register the indexer in the queries module cache
        _indexers["acme/widget"] = indexer

        # 4) Stub the LLM to return a clean human_first verdict and a report
        responses = [
            json.dumps({
                "classification": "human_first",
                "confidence": 0.91,
                "rationale": "Clean targeted change",
            }),
            "# Triage Report\n\n**Suggested action:** approve\n**Recommended reviewer:** Backend\n**Suggested labels:** `enhancement`",
        ]
        call_count = {"n": 0}

        async def fake_acompletion(*args, **kwargs):
            content = responses[call_count["n"]]
            call_count["n"] += 1
            return await make_acompletion_mock(content)(*args, **kwargs)

        # Patch BOTH module-level refs — the classifier and the triage agent
        # each have their own `from litellm import acompletion` import.
        monkeypatch.setattr("app.agents.classifier.acompletion", fake_acompletion)
        monkeypatch.setattr("app.agents.triage.acompletion", fake_acompletion)

        # 5) Build the graph and run it
        graph = build_triage_graph().compile(
            checkpointer=None,  # disable for the unit test
        )

        initial: TriageState = {
            "repo_full_name": "acme/widget",
            "pr_number": 7,
            "pr_title": "Add login helper",
            "pr_body": "Adds a thin wrapper around check_password.",
            "pr_author": "alice",
            "diff_text": ("+def login(u, p):\n" * 100),  # 100 lines so trivial fast path doesn't fire
            "files_changed": ["main.py", "tests/test_widget.py"],
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

        final = await graph.ainvoke(initial)

        # 6) Verify the final state
        assert final["classification"] == "human_first"
        assert final["classification_confidence"] == 0.91
        assert "Clean targeted" in final["classification_rationale"]
        # Blast radius may be 0 (the new function isn't called from anywhere yet)
        # or small (login -> check_password)
        assert final["blast_radius_score"] >= 0.0
        # The report should be populated
        assert "Triage Report" in final["report_summary"]
        assert final["suggested_action"] == "approve"
        # Labels were extracted from the report
        assert "enhancement" in final["suggested_labels"]
        # The LLM was called exactly twice (classify + generate_report)
        assert call_count["n"] == 2

    async def test_trivial_pr_skips_llm_classify(self, monkeypatch, tmp_path):
        """A single-file, minimal-diff PR should be classified as 'trivial'
        by the heuristic fast path WITHOUT calling the LLM."""
        from app.engine.indexer import SemanticIndexer

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "README.md").write_text("hello")
        # Won't be parsed (not a supported extension), but we still need the
        # indexer to exist for the queries module to return it.
        indexer = SemanticIndexer("demo/repo", repo_dir)
        monkeypatch.setattr("litellm.embedding", make_embedding_side_effect())
        await indexer.index_repository()
        _indexers["demo/repo"] = indexer

        # The LLM should NOT be called for a trivial PR
        async def fail_if_called(*args, **kwargs):
            raise AssertionError("LLM should not be called for trivial PRs")

        monkeypatch.setattr("app.agents.classifier.acompletion", fail_if_called)
        monkeypatch.setattr("app.agents.triage.acompletion", fail_if_called)

        graph = build_triage_graph().compile(checkpointer=None)
        initial: TriageState = {
            "repo_full_name": "demo/repo",
            "pr_number": 1,
            "pr_title": "fix typo",
            "pr_body": "",
            "pr_author": "bob",
            "diff_text": "+x",
            "files_changed": ["README.md"],
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
        final = await graph.ainvoke(initial)
        assert final["classification"] == "trivial"

    async def test_high_risk_file_forces_human_review(self, monkeypatch, tmp_path):
        """Touching an auth file should be classified high_risk and require
        human approval before posting."""
        from app.engine.indexer import SemanticIndexer

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "auth.py").write_text("def login(): pass")
        indexer = SemanticIndexer("demo/repo", repo_dir)
        monkeypatch.setattr("litellm.embedding", make_embedding_side_effect())
        await indexer.index_repository()
        _indexers["demo/repo"] = indexer

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("LLM should not be called for high_risk fast path")

        monkeypatch.setattr("app.agents.classifier.acompletion", fail_if_called)
        monkeypatch.setattr("app.agents.triage.acompletion", fail_if_called)

        graph = build_triage_graph().compile(checkpointer=None)
        initial: TriageState = {
            "repo_full_name": "demo/repo",
            "pr_number": 1,
            "pr_title": "Refactor auth",
            "pr_body": "",
            "pr_author": "eve",
            "diff_text": "+x" * 100,
            "files_changed": ["auth.py"],
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
        final = await graph.ainvoke(initial)
        assert final["classification"] == "high_risk"
        assert final["needs_human"] is True


class TestGetTriageGraph:
    """The singleton graph should be interrupt-paused before the action node."""

    def test_graph_has_interrupt_before_action(self):
        graph = get_triage_graph()
        # The compiled graph has an `interrupt_before_nodes` attribute
        assert "action" in (graph.interrupt_before_nodes or set())


@pytest.mark.asyncio
class TestTriageServiceApproveFlow:
    """The approve flow should mark the report as approved and post to GitHub."""

    async def test_approve_marks_report(
        self, db_session, sample_pr, fake_github
    ):
        from app.models.repo import TriageReport
        from app.services.triage_service import TriageService

        report = TriageReport(
            pull_request_id=sample_pr.id,
            classification=PRClassification.HUMAN_FIRST,
            classification_rationale="Clean PR",
            classification_confidence=0.92,
            blast_radius_score=0.0,
            affected_modules=[],
            affected_callers=[],
            summary="Looks good.",
            suggested_action="approve",
            suggested_reviewer="backend",
        )
        db_session.add(report)
        await db_session.flush()

        with patch("app.services.triage_service.GitHubClient", return_value=fake_github):
            service = TriageService(db_session)
            await service.approve_report(report.id, approved_by="alice", notes="LGTM")

        await db_session.refresh(report)
        assert report.approved is True
        assert report.approved_by == "alice"
        assert report.moderation_notes == "LGTM"
        # The fake GitHub client recorded a comment post
        assert len(fake_github.commented) == 1
        # PR status updated
        await db_session.refresh(sample_pr)
        assert sample_pr.triage_status in (
            TriageStatus.POSTED,
            TriageStatus.APPROVED,
        )

    async def test_reject_does_not_post_to_github(
        self, db_session, sample_pr, fake_github
    ):
        from app.models.repo import TriageReport
        from app.services.triage_service import TriageService

        report = TriageReport(
            pull_request_id=sample_pr.id,
            classification=PRClassification.AI_SLOP,
            classification_rationale="AI-generated low-quality",
            classification_confidence=0.85,
            summary="Reject this.",
            suggested_action="close",
        )
        db_session.add(report)
        await db_session.flush()

        with patch("app.services.triage_service.GitHubClient", return_value=fake_github):
            service = TriageService(db_session)
            await service.reject_report(
                report.id, rejected_by="bob", notes="Not worth merging"
            )

        await db_session.refresh(report)
        assert report.approved is False
        assert report.approved_by == "bob"
        # No comment was posted
        assert len(fake_github.commented) == 0
        # PR status = rejected
        await db_session.refresh(sample_pr)
        assert sample_pr.triage_status == TriageStatus.REJECTED
