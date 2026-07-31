"""Pydantic schemas for pull requests, triage reports, and approval requests.

These mirror the API surface consumed by the React dashboard and provide
the validation boundary between HTTP and the database.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# ─── Pull Request Schemas ──────────────────────────────────────

class PRSummary(BaseModel):
    """Lightweight PR representation for the dashboard list view."""

    id: UUID
    number: int
    title: str
    author: str
    author_avatar: str | None = None
    files_changed: int
    additions: int
    deletions: int
    classification: str | None = None
    classification_confidence: float | None = None
    triage_status: str
    created_at: datetime
    repo_full_name: str = ""

    class Config:
        from_attributes = True


class PRDetail(PRSummary):
    """Full PR detail with body, branches, and embedded triage reports."""

    body: str | None = None
    base_branch: str
    head_branch: str
    state: str
    updated_at: datetime
    triage_reports: list["TriageReportDetail"] = []


class TriageReportDetail(BaseModel):
    """Structured triage output for a single PR."""

    id: UUID
    classification: str
    classification_rationale: str | None = None
    classification_confidence: float
    blast_radius_score: float | None = None
    affected_modules: list[dict] | None = None
    summary: str
    suggested_action: str | None = None
    suggested_reviewer: str | None = None
    approved: bool | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    posted_to_github: bool = False
    processing_time_ms: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Approval / Rejection Requests ─────────────────────────────

class ApproveReportRequest(BaseModel):
    report_id: UUID
    notes: str = ""


class RejectReportRequest(BaseModel):
    report_id: UUID
    notes: str = ""


# ─── Repository Schemas ────────────────────────────────────────

class RepoSummary(BaseModel):
    id: UUID
    full_name: str
    description: str | None = None
    language: str | None = None
    stars: int
    status: str
    indexed_at: datetime | None = None
    open_prs: int = 0
    pending_triages: int = 0

    class Config:
        from_attributes = True


PRDetail.model_rebuild()
