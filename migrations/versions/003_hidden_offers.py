"""Add hidden_offers table for candidate-level opt-out."""

import sqlalchemy as sa
from alembic import op

revision = "003_hidden_offers"
down_revision = "002_sector_string"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hidden_offers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_offer_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "hidden_at",
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
            name="uq_hidden_offer_candidate",
        ),
    )


def downgrade() -> None:
    op.drop_table("hidden_offers")
