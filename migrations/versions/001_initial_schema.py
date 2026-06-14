"""Initial database schema migration."""

from alembic import op

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables are created via SQLAlchemy Base.metadata.create_all in bootstrap.
    # Future migrations should use op.create_table / op.add_column here.
    pass


def downgrade() -> None:
    pass
