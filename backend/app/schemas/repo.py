"""Repository-related Pydantic schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ConnectRepoRequest(BaseModel):
    """Request to add a repository to Pulse."""

    full_name: str  # e.g. "owner/repo"


class RepoGraphSummary(BaseModel):
    """Lightweight graph summary surfaced on the dashboard."""

    node_count: int
    edge_count: int
    top_modules: list[dict]
    high_centrality_nodes: list[dict]
