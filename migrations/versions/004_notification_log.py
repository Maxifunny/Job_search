"""Add notification_log table for email delivery tracking."""

import sqlalchemy as sa
from alembic import op

revision = "004_notification_log"
down_revision = "003_hidden_offers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False, server_default="email"),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_offer_id"], ["job_offers.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_offer_id",
            "candidate_name",
            "channel",
            name="uq_notification_offer_candidate_channel",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_log")
