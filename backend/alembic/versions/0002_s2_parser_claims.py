"""Allow result-only interviews and durable parser processing claims."""

import sqlalchemy as sa

from alembic import op

revision = "0002_s2"
down_revision = "0001_s1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ingestion_jobs", sa.Column("processing_token", sa.String(36), nullable=True))
    op.add_column(
        "ingestion_jobs", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    with op.batch_alter_table("interviews") as batch:
        batch.alter_column("scheduled_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch.alter_column("interviewer", existing_type=sa.String(100), nullable=True)


def downgrade():
    # Result-only records cannot safely regain invented scheduling data.
    connection = op.get_bind()
    count = connection.execute(
        sa.text("SELECT count(*) FROM interviews WHERE scheduled_at IS NULL OR interviewer IS NULL")
    ).scalar()
    if count:
        raise RuntimeError(
            "Cannot downgrade result-only interviews; export/correct their missing plans first"
        )
    with op.batch_alter_table("interviews") as batch:
        batch.alter_column("scheduled_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("interviewer", existing_type=sa.String(100), nullable=False)
    op.drop_column("ingestion_jobs", "processing_started_at")
    op.drop_column("ingestion_jobs", "processing_token")
