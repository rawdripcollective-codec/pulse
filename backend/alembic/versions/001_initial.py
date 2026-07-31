"""Initial Pulse schema migration.

Creates: repositories, pull_requests, triage_reports, users, settings, approvals.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # repositories
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("github_id", sa.Integer(), unique=True, nullable=False, index=True),
        sa.Column("full_name", sa.String(length=255), unique=True, nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=255), server_default="main"),
        sa.Column("language", sa.String(length=100), nullable=True),
        sa.Column("stars", sa.Integer(), server_default="0"),
        sa.Column(
            "status",
            sa.Enum("indexing", "ready", "error", name="repostatus"),
            server_default="indexing",
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column("graph_summary", postgresql.JSONB, nullable=True),
    )

    # pull_requests
    op.create_table(
        "pull_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("github_pr_id", sa.Integer(), nullable=False, index=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("author_avatar", sa.String(length=500), nullable=True),
        sa.Column("base_branch", sa.String(length=255), nullable=False),
        sa.Column("head_branch", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=50), server_default="open"),
        sa.Column("files_changed", sa.Integer(), server_default="0"),
        sa.Column("additions", sa.Integer(), server_default="0"),
        sa.Column("deletions", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "classification",
            sa.Enum(
                "human_first",
                "ai_assisted",
                "ai_slop",
                "trivial",
                "high_risk",
                name="prclassification",
            ),
            nullable=True,
        ),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column(
            "triage_status",
            sa.Enum(
                "pending",
                "in_progress",
                "awaiting_approval",
                "approved",
                "rejected",
                "posted",
                name="triagestatus",
            ),
            server_default="pending",
        ),
        sa.UniqueConstraint("repository_id", "github_pr_id", name="uq_repo_pr"),
    )

    # triage_reports
    op.create_table(
        "triage_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pull_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pull_requests.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "classification",
            sa.Enum(
                "human_first",
                "ai_assisted",
                "ai_slop",
                "trivial",
                "high_risk",
                name="prclassification",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("classification_rationale", sa.Text(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=False),
        sa.Column("blast_radius_score", sa.Float(), nullable=True),
        sa.Column("affected_modules", postgresql.JSONB, nullable=True),
        sa.Column("affected_callers", postgresql.JSONB, nullable=True),
        sa.Column("findings", postgresql.JSONB, nullable=True),
        sa.Column("pattern_violations", postgresql.JSONB, nullable=True),
        sa.Column("test_coverage_gap", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("suggested_action", sa.String(length=100), nullable=True),
        sa.Column("suggested_reviewer", sa.String(length=255), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_notes", sa.Text(), nullable=True),
        sa.Column("posted_to_github", sa.Boolean(), server_default=sa.false()),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_version", sa.String(length=50), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("github_id", sa.Integer(), unique=True, nullable=False, index=True),
        sa.Column("github_login", sa.String(length=255), unique=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # user_settings
    op.create_table(
        "user_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("auto_approve_trivial", sa.Boolean(), server_default=sa.true()),
        sa.Column("auto_approve_human_first", sa.Boolean(), server_default=sa.false()),
        sa.Column("always_require_human_for_high_risk", sa.Boolean(), server_default=sa.true()),
        sa.Column("notify_on_ai_slop", sa.Boolean(), server_default=sa.true()),
        sa.Column("preferred_llm_model", sa.String(length=100), nullable=True),
        sa.Column("high_risk_patterns", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # approvals
    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("triage_reports.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("user_settings")
    op.drop_table("users")
    op.drop_table("triage_reports")
    op.drop_table("pull_requests")
    op.drop_table("repositories")
    sa.Enum(name="triagestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="prclassification").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="repostatus").drop(op.get_bind(), checkfirst=True)
