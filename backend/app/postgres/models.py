"""PostgreSQL schema for the staged MongoDB migration."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.postgres.base import Base


TYPE_JSON = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_login_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    str_hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    str_name: Mapped[str] = mapped_column(String(200), nullable=False)
    str_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    str_department: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    str_approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    str_approved_by: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    dt_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bool_is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bool_is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    int_failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dict_preferences: Mapped[dict] = mapped_column(TYPE_JSON, nullable=False, default=dict)
    dt_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bool_mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    str_totp_secret_enc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dt_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    list_sessions: Mapped[list["Session"]] = relationship(
        back_populates="obj_user",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_users_approval_status", "str_approval_status"),
    )


class Session(Base):
    __tablename__ = "sessions"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    str_refresh_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    str_ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    str_user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dt_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bool_is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dt_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    str_replaced_by: Mapped[str] = mapped_column(Text, nullable=False, default="")

    obj_user: Mapped[User] = relationship(back_populates="list_sessions")

    __table_args__ = (
        Index("ix_sessions_user_id", "str_user_id"),
        Index("ix_sessions_expires_at", "dt_expires_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_action: Mapped[str] = mapped_column(String(160), nullable=False)
    str_user_id: Mapped[str | None] = mapped_column(String(36))
    str_user_email: Mapped[str | None] = mapped_column(String(200))
    str_resource_type: Mapped[str | None] = mapped_column(String(100))
    str_resource_id: Mapped[str | None] = mapped_column(String(200))
    str_detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    str_ip_address: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    str_user_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dt_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_hmac_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    str_hmac_verification_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unknown",
    )
    str_prev_hmac: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    str_hmac: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dict_before: Mapped[dict | None] = mapped_column(TYPE_JSON)
    dict_after: Mapped[dict | None] = mapped_column(TYPE_JSON)
    dict_extra: Mapped[dict] = mapped_column(TYPE_JSON, nullable=False, default=dict)
    str_country: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    str_country_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    str_city: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    str_region: Mapped[str] = mapped_column(String(160), nullable=False, default="")

    __table_args__ = (
        Index("ix_audit_logs_created_at", "dt_created_at"),
        Index("ix_audit_logs_user_id", "str_user_id"),
        Index("ix_audit_logs_action", "str_action"),
        Index("ix_audit_logs_hmac", "str_hmac"),
        Index("ix_audit_logs_user_action_created", "str_user_id", "str_action", "dt_created_at"),
    )


class IpGeoCache(Base):
    __tablename__ = "ip_geo_cache"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_ip: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    str_country: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    str_country_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    str_city: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    str_region: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    dt_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dt_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_ip_geo_cache_expires_at", "dt_expires_at"),
    )


class CaseClinicalInfo(Base):
    __tablename__ = "case_clinical_info"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_case_name: Mapped[str] = mapped_column(String(240), unique=True, nullable=False)
    dict_clinical_info: Mapped[dict] = mapped_column(TYPE_JSON, nullable=False, default=dict)
    dt_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_case_clinical_info_updated_at", "dt_updated_at"),
    )


class AuditIntegritySeal(Base):
    __tablename__ = "audit_integrity_seals"

    str_id: Mapped[str] = mapped_column("id", String(36), primary_key=True)
    str_scope: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    int_record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    str_first_record_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    str_last_record_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    str_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    str_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    str_key_fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    dict_summary: Mapped[dict] = mapped_column(TYPE_JSON, nullable=False, default=dict)
    dt_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    dt_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
