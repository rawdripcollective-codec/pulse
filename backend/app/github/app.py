"""GitHub App authentication.

This module implements the GitHub App authentication flow as an alternative
to OAuth user tokens. GitHub Apps are recommended for org-wide Pulse
installations because:

- They don't require per-user OAuth flows
- Permissions are scoped at the App level (finer-grained than OAuth)
- Installation tokens auto-expire (1 hour) — we cache and refresh
- Webhook events are signed with the App's private key (already supported)

Flow:
    1. Org owner installs the App on their org (one-time, via github.com)
    2. GitHub redirects to our callback URL with a `code` and `installation_id`
    3. We exchange the code for an installation access token via the GitHub API
    4. We persist (installation_id -> token) in the database
    5. The cached token is used for all subsequent API calls (refreshed on
       expiry, or proactively if it returns 401)

For the JWT that proves App identity to GitHub:
    - Header: { alg: RS256, typ: JWT }
    - Payload: { iat: <now - 60s>, exp: <now + 10min>, iss: <app_id> }
    - Signed with the App's private key (PEM)

Refs:
    - https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/about-authentication-with-a-github-app
    - https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
"""

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx
import jwt
import structlog
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.user import User, UserSettings

logger = structlog.get_logger()


# ─── JWT generation ───────────────────────────────────────────

# GitHub rejects JWTs with `exp` more than 10 minutes in the future, and
# recommends `iat` <= now (with a small clock-skew buffer of 60s in the past).
JWT_LIFETIME_SECONDS = 10 * 60          # 10 minutes
JWT_IAT_BACKDATE_SECONDS = 60           # 1 minute clock-skew buffer


@dataclass
class GitHubAppIdentity:
    """The identity of a registered GitHub App — the public/private keypair."""

    app_id: str
    private_key_pem: str

    def generate_jwt(self) -> str:
        """Generate a signed JWT proving this App's identity to GitHub.

        Returns a compact JWS string (header.payload.signature) ready to use
        as a Bearer token for app-level API calls.

        Raises:
            RuntimeError: If the private key is invalid or missing.
        """
        if not self.private_key_pem:
            raise RuntimeError(
                "GITHUB_APP_PRIVATE_KEY is not set. Generate a key at "
                "github.com/settings/apps/<your-app> and paste the PEM into .env."
            )

        now = int(time.time())
        payload = {
            "iat": now - JWT_IAT_BACKDATE_SECONDS,
            "exp": now + JWT_LIFETIME_SECONDS,
            "iss": self.app_id,
        }
        try:
            token = jwt.encode(
                payload,
                self.private_key_pem,
                algorithm="RS256",
            )
        except jwt.InvalidKeyError as exc:
            raise RuntimeError(
                f"GITHUB_APP_PRIVATE_KEY is not a valid RSA PEM key: {exc}"
            ) from exc
        return token

    @classmethod
    def from_settings(cls) -> Optional["GitHubAppIdentity"]:
        """Build identity from current Settings, or None if not configured."""
        if not settings.github_app_id or not settings.github_app_private_key:
            return None
        return cls(
            app_id=settings.github_app_id,
            private_key_pem=settings.github_app_private_key,
        )


# ─── Installation token cache ─────────────────────────────────

# GitHub installation tokens are valid for 1 hour. We cache them in-process
# and refresh when they expire (or when GitHub returns 401 for using an
# expired/revoked token).
INSTALLATION_TOKEN_LIFETIME_SECONDS = 50 * 60  # refresh 10 min before expiry


@dataclass
class InstallationToken:
    """A short-lived installation access token."""

    token: str
    installation_id: int
    expires_at: float  # unix timestamp

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now >= self.expires_at


class InstallationTokenCache:
    """In-memory cache for installation tokens, keyed by installation_id.

    For multi-worker deployments, swap to Redis. The interface stays the
    same: get(installation_id) -> Optional[InstallationToken] and
    put(installation_id, token).
    """

    def __init__(self) -> None:
        self._cache: dict[int, InstallationToken] = {}

    def get(self, installation_id: int) -> InstallationToken | None:
        token = self._cache.get(installation_id)
        if token is None:
            return None
        if token.is_expired():
            self._cache.pop(installation_id, None)
            return None
        return token

    def put(self, installation_id: int, token: str, expires_at: float) -> None:
        self._cache[installation_id] = InstallationToken(
            token=token,
            installation_id=installation_id,
            expires_at=expires_at,
        )

    def invalidate(self, installation_id: int) -> None:
        self._cache.pop(installation_id, None)

    def clear(self) -> None:
        self._cache.clear()


# Singleton cache (per-process)
_token_cache = InstallationTokenCache()


def get_installation_token_cache() -> InstallationTokenCache:
    """Return the process-wide installation token cache."""
    return _token_cache


# ─── Installation token acquisition ──────────────────────────

async def fetch_installation_token(
    installation_id: int,
    *,
    force_refresh: bool = False,
) -> InstallationToken:
    """Fetch (or refresh) an installation access token from GitHub.

    Caches the token in process memory until it expires. The token is good
    for 1 hour, so the cache prevents unnecessary API calls.

    Args:
        installation_id: The GitHub installation ID (assigned when the App
            is installed on a user/org).
        force_refresh: If True, bypass the cache and always re-fetch.

    Returns:
        A fresh InstallationToken.

    Raises:
        RuntimeError: If the App credentials are not configured.
        httpx.HTTPError: If the GitHub API call fails.
    """
    if not force_refresh:
        cached = _token_cache.get(installation_id)
        if cached is not None:
            return cached

    identity = GitHubAppIdentity.from_settings()
    if identity is None:
        raise RuntimeError(
            "GitHub App credentials are not configured. "
            "Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY in .env."
        )


    jwt_token = identity.generate_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    # GitHub returns ISO-8601 expiry like "2024-01-15T10:00:00Z"
    expires_at_iso = data["expires_at"]
    expires_at_dt = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))  # noqa: FURB162 (Python 3.10 compat)
    expires_at = expires_at_dt.timestamp()

    # Refresh proactively (10 min before the actual expiry)
    cached_expires_at = expires_at - (60 * 60 - INSTALLATION_TOKEN_LIFETIME_SECONDS)

    _token_cache.put(installation_id, token, cached_expires_at)

    logger.info(
        "Fetched installation token",
        installation_id=installation_id,
        expires_at=expires_at_iso,
    )
    return InstallationToken(
        token=token,
        installation_id=installation_id,
        expires_at=cached_expires_at,
    )


# ─── User persistence on install ─────────────────────────────

async def upsert_installation_owner(
    installation_id: int,
    account_login: str,
    account_id: int,
    account_type: str,  # "User" or "Organization"
    session=None,  # optional: inject a session (e.g. for tests)
) -> User:
    """Persist a User record for the account that installed the App.

    We don't get a user-level OAuth token from the App install flow, so this
    User is used as an audit anchor (who installed the App on which org) and
    a placeholder for future per-user actions. The actual API calls use
    installation tokens.

    For type="User": stores the user as a real account.
    For type="Organization": stores the org as a pseudo-user (login = org name).

    If `session` is provided, use it (and don't commit — let the caller
    decide). Otherwise create a new session and commit at the end.
    """
    if session is not None:
        return await _do_upsert(session, installation_id, account_login, account_id)

    async with async_session_factory() as new_session:
        result = await _do_upsert(
            new_session, installation_id, account_login, account_id
        )
        await new_session.commit()
        await session.refresh(result)
        return result


async def _do_upsert(session, installation_id, account_login, account_id) -> User:
    result = await session.execute(
        select(User).where(User.github_id == account_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            github_id=account_id,
            github_login=account_login,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        # Default settings row
        existing_settings = await session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        if existing_settings.scalar_one_or_none() is None:
            session.add(UserSettings(user_id=user.id))
    else:
        user.github_login = account_login
        user.is_active = True

    return user
