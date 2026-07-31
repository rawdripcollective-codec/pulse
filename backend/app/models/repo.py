"""SQLAlchemy models for repositories, PRs, and triage reports."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

# JSONB on Postgres, JSON on SQLite/MySQL — used wherever we want structured
# metadata storage. The .with_variant() call lets the same model work for tests.
JSONType = JSON().with_variant(JSONB(), "postgresql")


class RepoStatus(str, enum.Enum):
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class PRClassification(str, enum.Enum):
    HUMAN_FIRST = "human_first"
    AI_ASSISTED = "ai_assisted"
    AI_SLOP = "ai_slop"
    TRIVIAL = "trivial"
    HIGH_RISK = "high_risk"


class TriageStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id = Column(Integer, unique=True, nullable=False, index=True)
    full_name = Column(String(255), unique=True, nullable=False)  # e.g., "owner/repo"
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    default_branch = Column(String(255), default="main")
    language = Column(String(100), nullable=True)
    stars = Column(Integer, default=0)
    status = Column(SAEnum(RepoStatus), default=RepoStatus.INDEXING)
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    index_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Graph metadata stored as JSONB
    graph_summary = Column(JSONType, nullable=True)  # node/edge counts, top modules

    # Relations
    prs = relationship(
        "PullRequest",
        back_populates="repository",
        cascade="all, delete-orphan",
    )


class PullRequest(Base):
    __tablename__ = "pull_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id"),
        nullable=False,
        index=True,
    )
    github_pr_id = Column(Integer, nullable=False, index=True)
    number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    body = Column(Text, nullable=True)
    author = Column(String(255), nullable=False)
    author_avatar = Column(String(500), nullable=True)
    base_branch = Column(String(255), nullable=False)
    head_branch = Column(String(255), nullable=False)
    state = Column(String(50), default="open")
    files_changed = Column(Integer, default=0)
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # Triage
    classification = Column(SAEnum(PRClassification), nullable=True)
    classification_confidence = Column(Float, nullable=True)
    triage_status = Column(SAEnum(TriageStatus), default=TriageStatus.PENDING)

    # Relations
    repository = relationship("Repository", back_populates="prs")
    triage_reports = relationship(
        "TriageReport",
        back_populates="pull_request",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("repository_id", "github_pr_id", name="uq_repo_pr"),
    )


class TriageReport(Base):
    __tablename__ = "triage_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pull_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pull_requests.id"),
        nullable=False,
        index=True,
    )

    # Classification
    classification = Column(SAEnum(PRClassification), nullable=False)
    classification_rationale = Column(Text, nullable=True)
    classification_confidence = Column(Float, nullable=False)

    # Blast radius
    blast_radius_score = Column(Float, nullable=True)  # 0.0 - 1.0
    affected_modules = Column(JSONType, nullable=True)  # [{module, path, risk_level, reason}]
    affected_callers = Column(JSONType, nullable=True)

    # Review findings
    findings = Column(JSONType, nullable=True)
    pattern_violations = Column(JSONType, nullable=True)
    test_coverage_gap = Column(Float, nullable=True)

    # Summary
    summary = Column(Text, nullable=False)
    suggested_action = Column(String(100), nullable=True)
    suggested_reviewer = Column(String(255), nullable=True)

    # Human approval
    approved = Column(Boolean, nullable=True)
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    moderation_notes = Column(Text, nullable=True)

    # GitHub delivery
    posted_to_github = Column(Boolean, default=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)

    # Agent metadata
    agent_version = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relations
    pull_request = relationship("PullRequest", back_populates="triage_reports")
