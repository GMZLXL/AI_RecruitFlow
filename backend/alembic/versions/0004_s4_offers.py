"""Independent manually recorded Offer lifecycle; never infer acceptance from hire."""

import sqlalchemy as sa

from alembic import op

revision = "0004_s4"
down_revision = "0003_s3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "offers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False, unique=True
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('sent','accepted','declined')", name="ck_offer_status"),
    )


def downgrade():
    op.drop_table("offers")
