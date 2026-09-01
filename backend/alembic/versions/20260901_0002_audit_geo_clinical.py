"""Create audit, IP geolocation cache, and case clinical-info tables."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260901_0002"
down_revision: str | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_action", sa.String(length=160), nullable=False),
        sa.Column("str_user_id", sa.String(length=36), nullable=True),
        sa.Column("str_user_email", sa.String(length=200), nullable=True),
        sa.Column("str_resource_type", sa.String(length=100), nullable=True),
        sa.Column("str_resource_id", sa.String(length=200), nullable=True),
        sa.Column("str_detail", sa.Text(), nullable=False),
        sa.Column("str_ip_address", sa.String(length=64), nullable=False),
        sa.Column("str_user_agent", sa.Text(), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("str_prev_hmac", sa.String(length=64), nullable=False),
        sa.Column("str_hmac", sa.String(length=64), nullable=False),
        sa.Column("dict_before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dict_after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dict_extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("str_country", sa.String(length=8), nullable=False),
        sa.Column("str_country_name", sa.String(length=160), nullable=False),
        sa.Column("str_city", sa.String(length=160), nullable=False),
        sa.Column("str_region", sa.String(length=160), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["dt_created_at"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["str_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["str_action"])
    op.create_index("ix_audit_logs_hmac", "audit_logs", ["str_hmac"])
    op.create_index(
        "ix_audit_logs_user_action_created",
        "audit_logs",
        ["str_user_id", "str_action", "dt_created_at"],
    )

    op.create_table(
        "ip_geo_cache",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_ip", sa.String(length=64), nullable=False),
        sa.Column("str_country", sa.String(length=8), nullable=False),
        sa.Column("str_country_name", sa.String(length=160), nullable=False),
        sa.Column("str_city", sa.String(length=160), nullable=False),
        sa.Column("str_region", sa.String(length=160), nullable=False),
        sa.Column("dt_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("str_ip"),
    )
    op.create_index("ix_ip_geo_cache_expires_at", "ip_geo_cache", ["dt_expires_at"])

    op.create_table(
        "case_clinical_info",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("str_case_name", sa.String(length=240), nullable=False),
        sa.Column("dict_clinical_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("str_case_name"),
    )
    op.create_index("ix_case_clinical_info_updated_at", "case_clinical_info", ["dt_updated_at"])


def downgrade() -> None:
    op.drop_index("ix_case_clinical_info_updated_at", table_name="case_clinical_info")
    op.drop_table("case_clinical_info")
    op.drop_index("ix_ip_geo_cache_expires_at", table_name="ip_geo_cache")
    op.drop_table("ip_geo_cache")
    op.drop_index("ix_audit_logs_user_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_hmac", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
