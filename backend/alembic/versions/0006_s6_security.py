"""Explicit SSO identity mapping and single-instance task supervision metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0006_s6"
down_revision = "0005_s5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_settings", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("provider", sa.String(20)), sa.Column("model", sa.String(120)),
        sa.Column("api_key_ciphertext", sa.Text()), sa.Column("key_override", sa.Boolean(), nullable=False))
    op.create_table("auth_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(150), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("issuer", "subject", name="uq_auth_issuer_subject"))
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])
    op.create_table("worker_states", sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("owner_token", sa.String(36)), sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)), sa.Column("last_cycle_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)), sa.Column("last_error", sa.String(80)))


def downgrade():
    op.drop_table("ai_settings")
    op.drop_table("worker_states")
    op.drop_table("auth_identities")
