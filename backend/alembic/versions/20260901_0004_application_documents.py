"""Add PostgreSQL storage for projects, slides, AI state, and annotations."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260901_0004"
down_revision: str | None = "20260901_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_documents",
        sa.Column("str_collection", sa.String(length=80), nullable=False),
        sa.Column("str_id", sa.String(length=64), nullable=False),
        sa.Column("str_natural_key", sa.Text(), nullable=False),
        sa.Column("str_secondary_key", sa.Text(), nullable=False),
        sa.Column("dict_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dt_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dt_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("str_collection", "str_id"),
        sa.UniqueConstraint(
            "str_collection", "str_natural_key", "str_secondary_key",
            name="uq_application_documents_natural_key",
        ),
    )
    op.create_index(
        "ix_application_documents_collection",
        "application_documents",
        ["str_collection"],
    )
    op.create_index(
        "ix_application_documents_lookup",
        "application_documents",
        ["str_collection", "str_natural_key", "str_secondary_key"],
    )
    op.create_index(
        "ix_application_documents_json_gin",
        "application_documents",
        ["dict_document"],
        postgresql_using="gin",
    )

    op.create_table(
        "application_data_migrations",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("dict_source_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dict_target_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("str_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("dt_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("application_data_migrations")
    op.drop_index("ix_application_documents_json_gin", table_name="application_documents")
    op.drop_index("ix_application_documents_lookup", table_name="application_documents")
    op.drop_index("ix_application_documents_collection", table_name="application_documents")
    op.drop_table("application_documents")
