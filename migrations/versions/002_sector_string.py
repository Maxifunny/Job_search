"""Change sector columns from enum to string for configurable sectors."""

from alembic import op
import sqlalchemy as sa

revision = "002_sector_string"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None

job_sector_enum = sa.Enum("data", "automation", name="jobsectorenum")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE job_offers ALTER COLUMN sector TYPE VARCHAR(64) "
            "USING sector::text"
        )
        op.execute(
            "ALTER TABLE scrape_runs ALTER COLUMN sector TYPE VARCHAR(64) "
            "USING sector::text"
        )
        op.execute("DROP TYPE IF EXISTS jobsectorenum")
        return

    with op.batch_alter_table("job_offers") as batch_op:
        batch_op.alter_column(
            "sector",
            existing_type=job_sector_enum,
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    with op.batch_alter_table("scrape_runs") as batch_op:
        batch_op.alter_column(
            "sector",
            existing_type=job_sector_enum,
            type_=sa.String(length=64),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        job_sector_enum.create(bind, checkfirst=True)
        op.execute(
            "ALTER TABLE job_offers ALTER COLUMN sector TYPE jobsectorenum "
            "USING sector::jobsectorenum"
        )
        op.execute(
            "ALTER TABLE scrape_runs ALTER COLUMN sector TYPE jobsectorenum "
            "USING sector::jobsectorenum"
        )
        return

    with op.batch_alter_table("job_offers") as batch_op:
        batch_op.alter_column(
            "sector",
            existing_type=sa.String(length=64),
            type_=job_sector_enum,
            existing_nullable=False,
        )
    with op.batch_alter_table("scrape_runs") as batch_op:
        batch_op.alter_column(
            "sector",
            existing_type=sa.String(length=64),
            type_=job_sector_enum,
            existing_nullable=False,
        )
