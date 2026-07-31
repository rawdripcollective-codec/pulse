"""GitHub OAuth flow: authorization URL builder, code exchange, token refresh."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import structlog

from app.config import settings
from app.database import async_session_factory
from app.models.user import User, UserSettings
from sqlalchemy import select

logger = structlog.get_logger()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def build_authorize_url(redirect_uri: str, state: str, scope: str = "repo,read:user") -> str:
    """Build the GitHub OAuth authorization URL for the user to visit."""
    return (
        f"{GITHUB_AUTHORIZE_URL}"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
        f"&scope={scope}"
    )


async def exchange_code_for_token(code: str, redirect_uri: str) -> Optional[dict]:
    """Exchange an OAuth authorization code for an access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_github_user(access_token: str) -> dict:
    """Fetch the authenticated GitHub user profile."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def upsert_user_from_oauth(token_response: dict) -> Optional[User]:
    """Persist a User record (or update it) from a successful OAuth exchange."""
    access_token = token_response.get("access_token")
    refresh_token = token_response.get("refresh_token")
    expires_in = token_response.get("expires_in")  # seconds, may be absent
    if not access_token:
        logger.error("OAuth response missing access_token", response=token_response)
        return None

    profile = await fetch_github_user(access_token)
    github_id = profile.get("id")
    if not github_id:
        logger.error("GitHub user profile missing id", profile=profile)
        return None

    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.github_id == github_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                github_id=github_id,
                github_login=profile["login"],
                email=profile.get("email"),
                avatar_url=profile.get("avatar_url"),
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=expires_at,
            )
            session.add(user)
            await session.flush()
            # Create default settings
            session.add(UserSettings(user_id=user.id))
        else:
            user.access_token = access_token
            user.refresh_token = refresh_token or user.refresh_token
            user.token_expires_at = expires_at
            user.avatar_url = profile.get("avatar_url") or user.avatar_url
            user.email = profile.get("email") or user.email
        await session.commit()
        await session.refresh(user)
        return user
