"""Add legacy audit verification metadata and migration snapshot seals."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260901_0003"
down_revision: str | None = "20260901_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("dt_hmac_created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column(
            "str_hmac_verification_status",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_table(
        "audit_integrity_seals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_scope", sa.String(length=100), nullable=False),
        sa.Column("int_record_count", sa.Integer(), nullable=False),
        sa.Column("str_first_record_id", sa.String(length=36), nullable=False),
        sa.Column("str_last_record_id", sa.String(length=36), nullable=False),
        sa.Column("str_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("str_hmac", sa.String(length=64), nullable=False),
        sa.Column("str_key_fingerprint", sa.String(length=16), nullable=False),
        sa.Column("dict_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("str_scope"),
    )


def downgrade() -> None:
    op.drop_table("audit_integrity_seals")
    op.drop_column("audit_logs", "str_hmac_verification_status")
    op.drop_column("audit_logs", "dt_hmac_created_at")
