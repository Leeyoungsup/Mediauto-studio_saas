"""Create PostgreSQL users and sessions tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260901_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_login_id", sa.String(length=100), nullable=False),
        sa.Column("str_hashed_password", sa.Text(), nullable=False),
        sa.Column("str_name", sa.String(length=200), nullable=False),
        sa.Column("str_role", sa.String(length=32), nullable=False),
        sa.Column("str_department", sa.String(length=200), nullable=False),
        sa.Column("str_approval_status", sa.String(length=32), nullable=False),
        sa.Column("str_approved_by", sa.String(length=100), nullable=False),
        sa.Column("dt_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bool_is_active", sa.Boolean(), nullable=False),
        sa.Column("bool_is_locked", sa.Boolean(), nullable=False),
        sa.Column("int_failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("dict_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dt_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bool_mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("str_totp_secret_enc", sa.Text(), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("str_login_id"),
    )
    op.create_index("ix_users_approval_status", "users", ["str_approval_status"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_user_id", sa.String(length=36), nullable=False),
        sa.Column("str_refresh_token", sa.Text(), nullable=False),
        sa.Column("str_ip_address", sa.String(length=64), nullable=False),
        sa.Column("str_user_agent", sa.Text(), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bool_is_revoked", sa.Boolean(), nullable=False),
        sa.Column("dt_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("str_replaced_by", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["str_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("str_refresh_token"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["str_user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["dt_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_users_approval_status", table_name="users")
    op.drop_table("users")
