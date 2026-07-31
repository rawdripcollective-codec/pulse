"""Triage-specific Pydantic schemas (separate file to keep concerns split)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TriageFinding(BaseModel):
    """Single review finding emitted by the deep review node."""

    severity: str  # BLOCKER | CRITICAL | WARNING | INFO
    category: str  # pattern | contract | integration | coverage | dead_code | security | performance
    file: str
    line: int
    description: str
    remediation: str


class TriageSummary(BaseModel):
    """Compact summary used by the dashboard header."""

    report_id: UUID
    pr_id: UUID
    classification: str
    blast_radius_score: float | None = None
    suggested_action: str | None = None
    needs_human: bool
    created_at: datetime


class TriageStats(BaseModel):
    """Aggregated stats for the dashboard stats bar."""

    total_repos: int
    open_prs: int
    awaiting_approval: int
    in_progress: int
    posted_today: int
    avg_processing_time_ms: float | None = None
