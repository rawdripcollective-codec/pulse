"""Unit tests for the GitHub App authentication module."""

# ─── Test fixtures: a real RSA keypair for JWT testing ────────
# We generate a real RSA keypair for the tests because JWT signing requires
# a valid PEM-encoded private key. We generate it once per session.
import time
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings
from app.github.app import (
    JWT_LIFETIME_SECONDS,
    GitHubAppIdentity,
    InstallationToken,
    InstallationTokenCache,
    fetch_installation_token,
    get_installation_token_cache,
)


@pytest.fixture(scope="session")
def rsa_keypair():
    """Generate a real RSA keypair for the test session."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


@pytest.fixture
def app_identity(rsa_keypair):
    private_pem, _ = rsa_keypair
    return GitHubAppIdentity(app_id="123456", private_key_pem=private_pem)


# ─── JWT generation ───────────────────────────────────────────

class TestGitHubAppIdentity:
    def test_generate_jwt_returns_string(self, app_identity):
        token = app_identity.generate_jwt()
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWS compact format: header.payload.sig

    def test_jwt_has_correct_payload(self, app_identity, rsa_keypair):
        _private_pem, public_pem = rsa_keypair
        token = app_identity.generate_jwt()
        # Decode without verification (we have the key, but we're testing
        # the payload shape, not the signature — that comes from GitHub).
        decoded = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        assert decoded["iss"] == "123456"
        # exp - iat = JWT_LIFETIME + JWT_IAT_BACKDATE (we backdate iat by 60s)
        from app.github.app import JWT_IAT_BACKDATE_SECONDS
        assert decoded["exp"] - decoded["iat"] == JWT_LIFETIME_SECONDS + JWT_IAT_BACKDATE_SECONDS
        # iat is backdated, so the absolute window is 10 minutes
        assert decoded["exp"] - (decoded["iat"] + JWT_IAT_BACKDATE_SECONDS) == JWT_LIFETIME_SECONDS

    def test_jwt_iat_backdates_60s(self, app_identity, rsa_keypair):
        """The iat claim should be ~60s in the past to handle clock skew."""
        _, public_pem = rsa_keypair
        before = int(time.time())
        token = app_identity.generate_jwt()
        after = int(time.time())
        decoded = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        # iat should be in [before-60, after-60] (allowing for the 60s backdate)
        assert before - 60 <= decoded["iat"] <= after - 60

    def test_empty_private_key_raises(self):
        identity = GitHubAppIdentity(app_id="123", private_key_pem="")
        with pytest.raises(RuntimeError, match="GITHUB_APP_PRIVATE_KEY"):
            identity.generate_jwt()

    def test_invalid_pem_raises(self):
        identity = GitHubAppIdentity(
            app_id="123",
            private_key_pem="not-a-valid-pem",
        )
        with pytest.raises(RuntimeError, match="not a valid RSA PEM key"):
            identity.generate_jwt()

    def test_from_settings_returns_none_when_unconfigured(self, monkeypatch):
        monkeypatch.setattr(settings, "github_app_id", "")
        monkeypatch.setattr(settings, "github_app_private_key", "")
        assert GitHubAppIdentity.from_settings() is None

    def test_from_settings_uses_settings(self, app_identity, monkeypatch):
        monkeypatch.setattr(settings, "github_app_id", "123456")
        monkeypatch.setattr(settings, "github_app_private_key", app_identity.private_key_pem)
        identity = GitHubAppIdentity.from_settings()
        assert identity is not None
        assert identity.app_id == "123456"


# ─── Installation token cache ─────────────────────────────────

class TestInstallationTokenCache:
    def test_cache_miss_returns_none(self):
        cache = InstallationTokenCache()
        assert cache.get(42) is None

    def test_put_then_get(self):
        cache = InstallationTokenCache()
        cache.put(42, "token-xyz", expires_at=time.time() + 600)
        tok = cache.get(42)
        assert tok is not None
        assert tok.token == "token-xyz"
        assert tok.installation_id == 42

    def test_expired_token_evicted_on_get(self):
        cache = InstallationTokenCache()
        cache.put(42, "stale-token", expires_at=time.time() - 1)
        # First get: evicts and returns None
        assert cache.get(42) is None
        # Second get: cache is empty
        assert cache.get(42) is None

    def test_invalidate_removes_token(self):
        cache = InstallationTokenCache()
        cache.put(42, "token-xyz", expires_at=time.time() + 600)
        cache.invalidate(42)
        assert cache.get(42) is None

    def test_clear_removes_all(self):
        cache = InstallationTokenCache()
        cache.put(1, "t1", expires_at=time.time() + 600)
        cache.put(2, "t2", expires_at=time.time() + 600)
        cache.clear()
        assert cache.get(1) is None
        assert cache.get(2) is None

    def test_separate_installations_isolated(self):
        cache = InstallationTokenCache()
        cache.put(1, "t1", expires_at=time.time() + 600)
        cache.put(2, "t2", expires_at=time.time() + 600)
        assert cache.get(1).token == "t1"
        assert cache.get(2).token == "t2"
        cache.invalidate(1)
        assert cache.get(1) is None
        assert cache.get(2).token == "t2"


class TestInstallationToken:
    def test_is_expired_past(self):
        tok = InstallationToken(token="x", installation_id=1, expires_at=time.time() - 1)
        assert tok.is_expired() is True

    def test_is_expired_future(self):
        tok = InstallationToken(token="x", installation_id=1, expires_at=time.time() + 600)
        assert tok.is_expired() is False

    def test_is_expired_with_explicit_now(self):
        tok = InstallationToken(token="x", installation_id=1, expires_at=100)
        assert tok.is_expired(now=99) is False
        assert tok.is_expired(now=100) is True
        assert tok.is_expired(now=101) is True


# ─── fetch_installation_token (with HTTP mock) ────────────────

class TestFetchInstallationToken:
    @pytest.mark.asyncio
    async def test_returns_token_on_first_call(self, app_identity, monkeypatch):
        monkeypatch.setattr(settings, "github_app_id", "123456")
        monkeypatch.setattr(settings, "github_app_private_key", app_identity.private_key_pem)

        # Reset the singleton cache
        get_installation_token_cache().clear()

        # Mock httpx response
        from datetime import datetime, timedelta

        future = datetime.now(UTC) + timedelta(hours=1)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "ghs_test_token_value",
            "expires_at": future.isoformat().replace("+00:00", "Z"),
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.github.app.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            tok = await fetch_installation_token(99999)

        assert tok.token == "ghs_test_token_value"
        assert tok.installation_id == 99999

    @pytest.mark.asyncio
    async def test_caches_token_for_subsequent_calls(self, app_identity, monkeypatch):
        monkeypatch.setattr(settings, "github_app_id", "123456")
        monkeypatch.setattr(settings, "github_app_private_key", app_identity.private_key_pem)
        get_installation_token_cache().clear()

        from datetime import datetime, timedelta

        future = datetime.now(UTC) + timedelta(hours=1)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "token": "cached_token",
            "expires_at": future.isoformat().replace("+00:00", "Z"),
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.github.app.httpx.AsyncClient") as mock_client:
            post_mock = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = post_mock

            tok1 = await fetch_installation_token(12345)
            tok2 = await fetch_installation_token(12345)
            tok3 = await fetch_installation_token(12345, force_refresh=True)

        # 3 calls total (third forced a refresh)
        assert post_mock.call_count == 2
        assert tok1.token == "cached_token"
        assert tok2.token == "cached_token"
        assert tok3.token == "cached_token"

    @pytest.mark.asyncio
    async def test_raises_when_app_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "github_app_id", "")
        monkeypatch.setattr(settings, "github_app_private_key", "")
        get_installation_token_cache().clear()

        with pytest.raises(RuntimeError, match="not configured"):
            await fetch_installation_token(12345)
