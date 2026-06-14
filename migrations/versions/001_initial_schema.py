"""Initial database schema migration."""

from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

job_sector_enum = sa.Enum("data", "automation", name="jobsectorenum")
match_decision_enum = sa.Enum(
    "pending", "accepted", "rejected", "skipped", name="matchdecisionenum"
)


def upgrade() -> None:
    job_sector_enum.create(op.get_bind(), checkfirst=True)
    match_decision_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "job_offers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("sector", job_sector_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("skills_json", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("employment_type", sa.String(length=64), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=True),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_offer_source_external_id"),
    )
    op.create_index("ix_job_offers_content_hash", "job_offers", ["content_hash"])
    op.create_index("ix_job_offers_sector_active", "job_offers", ["sector", "is_active"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("sector", job_sector_enum, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offers_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_name"),
    )

    op.create_table(
        "embedding_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("text_hash", "model", name="uq_embedding_cache_text_model"),
    )

    op.create_table(
        "match_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("semantic_score", sa.Float(), nullable=True),
        sa.Column("llm_score", sa.Float(), nullable=True),
        sa.Column("llm_confidence", sa.Float(), nullable=True),
        sa.Column(
            "decision",
            match_decision_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("matched_skills_json", sa.Text(), nullable=True),
        sa.Column("missing_skills_json", sa.Text(), nullable=True),
        sa.Column("llm_explanation", sa.Text(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_offer_id"], ["job_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_offer_id", "candidate_name", name="uq_match_offer_candidate"),
    )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column(
            "recommended_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=64), nullable=True),
        sa.Column("user_action", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["job_offer_id"], ["job_offers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_offer_id", "candidate_name", name="uq_recommendation_offer_candidate"
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("match_results")
    op.drop_table("embedding_cache")
    op.drop_table("user_preferences")
    op.drop_table("scrape_runs")
    op.drop_index("ix_job_offers_sector_active", table_name="job_offers")
    op.drop_index("ix_job_offers_content_hash", table_name="job_offers")
    op.drop_table("job_offers")
    match_decision_enum.drop(op.get_bind(), checkfirst=True)
    job_sector_enum.drop(op.get_bind(), checkfirst=True)
