"""Enforce password age, single-login identity and human-activity expiry.

Unknown existing password dates intentionally remain NULL: the next login must
change the password. Existing JWTs have no session identity and require re-login.
"""
from alembic import op
import sqlalchemy as sa
revision = "20261008_0005"
down_revision = "20260901_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("dt_password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("str_active_session_id", sa.String(64), nullable=False, server_default=""))
    op.add_column("users", sa.Column("dt_last_activity_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for name in ("dt_last_activity_at", "str_active_session_id", "dt_password_changed_at"):
        op.drop_column("users", name)
