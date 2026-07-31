"""Integration tests for the REST API routes.

These exercise the FastAPI app end-to-end through httpx + ASGITransport,
so the route handlers, dependency injection, and Pydantic validation are
all under test. The database is the in-memory SQLite session, with the
test's get_db override wired in by the `api_client` fixture.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.models.repo import (
    PRClassification,
    PullRequest,
    Repository,
    RepoStatus,
    TriageReport,
    TriageStatus,
)
from app.models.user import User

# ─── /health & / (basic smoke) ───────────────────────────────

class TestHealthRoutes:
    async def test_health_returns_ok(self, api_client):
        resp = await api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_root_returns_app_metadata(self, api_client):
        resp = await api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"] == settings.app_name
        assert data["docs"] == "/docs"


# ─── /api/repos ───────────────────────────────────────────────

class TestRepoRoutes:
    async def test_list_repos_empty(self, api_client):
        resp = await api_client.get("/api/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_repos_with_data(self, api_client, sample_repo):
        resp = await api_client.get("/api/repos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "acme/widget"
        assert data[0]["status"] == "ready"
        assert data[0]["stars"] == 42
        assert data[0]["open_prs"] == 0  # no PRs yet

    async def test_list_repos_counts_open_prs(self, api_client, sample_repo, sample_pr):
        resp = await api_client.get("/api/repos")
        data = resp.json()
        assert data[0]["open_prs"] == 1
        # The sample_pr fixture sets triage_status=AWAITING_APPROVAL
        # which is "approved IS NULL" — counted as pending triage
        assert data[0]["pending_triages"] == 0  # report doesn't exist yet

    async def test_reindex_unknown_repo_returns_404(self, api_client):
        resp = await api_client.post("/api/repos/does-not-exist/reindex")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ─── /api/prs ─────────────────────────────────────────────────

class TestPullRequestRoutes:
    async def test_list_prs_empty(self, api_client):
        resp = await api_client.get("/api/prs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_prs_with_data(self, api_client, sample_pr):
        resp = await api_client.get("/api/prs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Add retry logic"
        assert data[0]["number"] == 7
        assert data[0]["classification"] == "human_first"
        assert data[0]["triage_status"] == "awaiting_approval"
        assert data[0]["repo_full_name"] == "acme/widget"

    async def test_list_prs_filtered_by_repo(self, api_client, sample_pr, db_session):
        # Insert a second repo + PR to verify the filter
        other_repo = Repository(
            github_id=99,
            full_name="other/place",
            owner="other",
            name="place",
            status=RepoStatus.READY,
        )
        db_session.add(other_repo)
        await db_session.flush()

        resp = await api_client.get(f"/api/prs?repo_full_name={sample_pr.repository.full_name}")
        assert len(resp.json()) == 1

        resp = await api_client.get("/api/prs?repo_full_name=other/place")
        assert resp.json() == []

        resp = await api_client.get("/api/prs?repo_full_name=acme/widget")
        assert len(resp.json()) == 1

    async def test_list_prs_filtered_by_status(self, api_client, sample_pr):
        resp = await api_client.get("/api/prs?triage_status=awaiting_approval")
        assert len(resp.json()) == 1

        resp = await api_client.get("/api/prs?triage_status=rejected")
        assert resp.json() == []

    async def test_get_pr_detail(self, api_client, sample_pr, db_session):
        # Add a triage report to the PR
        report = TriageReport(
            pull_request_id=sample_pr.id,
            classification=PRClassification.HUMAN_FIRST,
            classification_rationale="Looks good",
            classification_confidence=0.9,
            summary="Triage report body",
            suggested_action="approve",
        )
        db_session.add(report)
        await db_session.flush()

        resp = await api_client.get(f"/api/prs/{sample_pr.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(sample_pr.id)
        assert data["body"] == "This PR adds exponential backoff to the webhook handler."
        assert data["base_branch"] == "main"
        assert data["head_branch"] == "feature/retry"
        assert len(data["triage_reports"]) == 1
        assert data["triage_reports"][0]["summary"] == "Triage report body"

    async def test_get_pr_detail_unknown_returns_404(self, api_client):
        fake_id = uuid.uuid4()
        resp = await api_client.get(f"/api/prs/{fake_id}")
        assert resp.status_code == 404


# ─── /api/triage/* ────────────────────────────────────────────

class TestTriageApprovalRoutes:
    async def _make_report(self, db_session, sample_pr) -> TriageReport:
        report = TriageReport(
            pull_request_id=sample_pr.id,
            classification=PRClassification.HUMAN_FIRST,
            classification_rationale="Clean PR",
            classification_confidence=0.92,
            summary="Looks good.",
            suggested_action="approve",
        )
        db_session.add(report)
        await db_session.flush()
        return report

    async def test_approve_records_decision(
        self, api_client, db_session, sample_pr, fake_github
    ):
        report = await self._make_report(db_session, sample_pr)

        with patch("app.services.triage_service.GitHubClient", return_value=fake_github):
            resp = await api_client.post(
                "/api/triage/approve",
                json={"report_id": str(report.id), "notes": "LGTM"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["report_id"] == str(report.id)

        # Side effects: comment posted, status updated
        assert len(fake_github.commented) == 1
        await db_session.refresh(sample_pr)
        assert sample_pr.triage_status in (
            TriageStatus.POSTED,
            TriageStatus.APPROVED,
        )

    async def test_reject_does_not_post_to_github(
        self, api_client, db_session, sample_pr, fake_github
    ):
        report = await self._make_report(db_session, sample_pr)

        with patch("app.services.triage_service.GitHubClient", return_value=fake_github):
            resp = await api_client.post(
                "/api/triage/reject",
                json={"report_id": str(report.id), "notes": "Not worth it"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"

        # No comment was posted
        assert len(fake_github.commented) == 0
        await db_session.refresh(sample_pr)
        assert sample_pr.triage_status == TriageStatus.REJECTED

    async def test_approve_unknown_report_returns_500(self, api_client, sample_pr):
        # The service raises ValueError; FastAPI turns unhandled exceptions
        # into 500. (In production, a global handler would catch this.)
        fake_id = uuid.uuid4()
        resp = await api_client.post(
            "/api/triage/approve",
            json={"report_id": str(fake_id), "notes": ""},
        )
        # The endpoint will raise; FastAPI returns 500
        assert resp.status_code in (500, 404)

    async def test_approve_validates_payload(self, api_client):
        # Missing required 'report_id' field
        resp = await api_client.post(
            "/api/triage/approve",
            json={"notes": "no report id"},
        )
        assert resp.status_code == 422  # Pydantic validation


# ─── /api/webhook/github ──────────────────────────────────────

class TestWebhookRoute:
    def _sign(self, body: bytes) -> str:
        """Compute the X-Hub-Signature-256 header for a body."""
        return "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

    async def test_webhook_without_secret_skips_verification(
        self, api_client, monkeypatch
    ):
        # The conftest sets GITHUB_WEBHOOK_SECRET="" effectively via env, but
        # settings may have loaded the default. We patch settings here.
        monkeypatch.setattr(settings, "github_webhook_secret", "")
        # Use 'ping' event — the handler treats it as a no-op, so the route
        # accepts the request without trying to call GitHub.
        body = json.dumps({"zen": "Speak like a human"}).encode()
        resp = await api_client.post(
            "/api/webhook/github",
            content=body,
            headers={"X-GitHub-Event": "ping", "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "received"}

    async def test_webhook_with_valid_signature_is_accepted(
        self, api_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "github_webhook_secret", "test-secret")
        body = json.dumps({
            "action": "opened",
            "pull_request": {"number": 1, "id": 100},
            "repository": {"full_name": "test/repo"},
        }).encode()
        sig = self._sign(body)

        # The handler will try to enqueue triage for test/repo which doesn't
        # exist in our test DB; we expect an internal error or a 200 (if the
        # handler swallows the error). Either way, the auth layer accepted it.
        # Patch where the route uses it (api.py imports it).
        async def fake_handler(event, payload):
            return None
        with patch("app.routes.api.handle_pull_request_event", side_effect=fake_handler):
            resp = await api_client.post(
                "/api/webhook/github",
                content=body,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": sig,
                    "Content-Type": "application/json",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "received"}

    async def test_webhook_with_bad_signature_is_rejected(
        self, api_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "github_webhook_secret", "test-secret")
        body = b'{"action": "opened"}'
        # Use a wrong signature
        bad_sig = "sha256=" + "0" * 64

        resp = await api_client.post(
            "/api/webhook/github",
            content=body,
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": bad_sig,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 401
        assert "signature" in resp.json()["detail"].lower()

    async def test_webhook_with_missing_signature_header_is_rejected(
        self, api_client, monkeypatch
    ):
        monkeypatch.setattr(settings, "github_webhook_secret", "test-secret")
        body = b'{"action": "opened"}'

        resp = await api_client.post(
            "/api/webhook/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "Content-Type": "application/json"},
        )
        assert resp.status_code == 401


# ─── GitHub App endpoints ─────────────────────────────────────

class TestGitHubAppRoutes:
    @pytest.fixture(autouse=True)
    def _reset_token_cache(self):
        """The installation token cache is a process-wide singleton.
        Clear it before each test so state doesn't leak between cases.
        """
        from app.github.app import get_installation_token_cache

        get_installation_token_cache().clear()
        yield
        get_installation_token_cache().clear()

    async def test_install_callback_persists_user(
        self, api_client, db_session, monkeypatch
    ):
        # Configure the App so fetch_installation_token can run.
        from cryptography.hazmat.primitives import serialization

        # Use a real RSA keypair so JWT generation works
        from cryptography.hazmat.primitives.asymmetric import rsa

        from app.github import app as app_module

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        monkeypatch.setattr(settings, "github_app_id", "12345")
        monkeypatch.setattr(settings, "github_app_private_key", private_pem)

        # Mock the GitHub HTTP response for token fetch
        from datetime import datetime, timedelta, timezone

        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        mock_response = MagicMock()
        mock_response.json.return_value = {"token": "ghs_test", "expires_at": future}
        mock_response.raise_for_status = MagicMock()

        with patch("app.github.app.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            # Reset the token cache
            app_module.get_installation_token_cache().clear()

            resp = await api_client.post(
                "/api/github/app/install",
                json={
                    "installation": {
                        "id": 99999,
                        "account": {
                            "id": 555,
                            "login": "test-org",
                            "type": "Organization",
                        },
                    },
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "installed"
        assert body["installation_id"] == 99999
        assert body["account"] == "test-org"

        # User record was created
        from sqlalchemy import select

        result = await db_session.execute(select(User).where(User.github_id == 555))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.github_login == "test-org"

    async def test_install_callback_400_on_missing_fields(self, api_client):
        resp = await api_client.post(
            "/api/github/app/install",
            json={"installation": {}, "account": {}},
        )
        assert resp.status_code == 400

    async def test_list_installations_empty(self, api_client):
        resp = await api_client.get("/api/github/app/installations")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"active_installations": []}


# ─── /api/dashboard/* ────────────────────────────────────────

class TestDashboardRoutes:
    async def test_stats_empty(self, api_client):
        resp = await api_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_repos"] == 0
        assert data["open_prs"] == 0
        assert data["awaiting_approval"] == 0
        assert data["in_progress"] == 0
        assert data["posted_today"] == 0
        assert data["avg_processing_time_ms"] is None

    async def test_stats_with_data(
        self, api_client, sample_repo, sample_pr, db_session
    ):
        # Add a triage report so stats are non-zero
        report = TriageReport(
            pull_request_id=sample_pr.id,
            classification=PRClassification.HUMAN_FIRST,
            classification_confidence=0.9,
            summary="ok",
            processing_time_ms=1500,
        )
        db_session.add(report)
        await db_session.flush()

        resp = await api_client.get("/api/dashboard/stats")
        data = resp.json()
        assert data["total_repos"] == 1
        assert data["open_prs"] == 1
        # 1 report exists, approved is None -> counted as awaiting
        assert data["awaiting_approval"] == 1
        assert data["avg_processing_time_ms"] == 1500.0

    async def test_semantic_search_empty_indexer_returns_empty(self, api_client):
        # The conftest doesn't register an indexer for "acme/widget" in the
        # queries cache, so the search returns [].
        resp = await api_client.get(
            "/api/dashboard/search",
            params={"repo": "acme/widget", "q": "authenticate"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["query"] == "authenticate"
        assert data["results"] == []

    async def test_blast_radius_empty_indexer_returns_empty(self, api_client):
        resp = await api_client.get(
            "/api/dashboard/blast-radius",
            params={"repo": "acme/widget", "file": "auth.py"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file"] == "auth.py"
        assert data["affected"] == []
        assert data["count"] == 0

    async def test_high_risk_files_empty_indexer_returns_empty(self, api_client):
        resp = await api_client.get(
            "/api/dashboard/high-risk-files",
            params={"repo": "acme/widget", "top_n": "5"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo"] == "acme/widget"
        assert data["files"] == []
