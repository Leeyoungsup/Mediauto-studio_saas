"""Backend-neutral user and refresh-session persistence."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select, update

from app.postgres.database import get_postgres_session, is_postgres_connected
from app.postgres.models import Session, User


_TUPLE_USER_FIELDS = (
    "str_login_id",
    "str_hashed_password",
    "str_name",
    "str_role",
    "str_department",
    "str_approval_status",
    "str_approved_by",
    "dt_approved_at",
    "bool_is_active",
    "bool_is_locked",
    "int_failed_login_attempts",
    "dict_preferences",
    "dt_locked_until",
    "bool_mfa_enabled",
    "str_totp_secret_enc",
    "dt_created_at",
    "dt_updated_at",
    "dt_last_login",
)
_TUPLE_SESSION_FIELDS = (
    "str_user_id",
    "str_refresh_token",
    "str_ip_address",
    "str_user_agent",
    "dt_created_at",
    "dt_expires_at",
    "bool_is_revoked",
    "dt_rotated_at",
    "str_replaced_by",
)


def _new_id() -> str:
    """Generate a URL-safe 24-character identifier compatible with legacy IDs."""
    return secrets.token_hex(12)


def _user_model_to_dict(obj_user: User, bool_include_secrets: bool) -> dict:
    dict_user = {"_id": obj_user.str_id}
    for str_field in _TUPLE_USER_FIELDS:
        if not bool_include_secrets and str_field in {
            "str_hashed_password",
            "str_totp_secret_enc",
            "int_failed_login_attempts",
        }:
            continue
        dict_user[str_field] = getattr(obj_user, str_field)
    return dict_user


def _session_model_to_dict(obj_session: Session) -> dict:
    dict_session = {"_id": obj_session.str_id}
    for str_field in _TUPLE_SESSION_FIELDS:
        dict_session[str_field] = getattr(obj_session, str_field)
    return dict_session


class PostgresUserStore:
    async def find_by_id(self, str_user_id: str, bool_include_secrets: bool = True) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_user = await obj_session.get(User, str_user_id)
            return _user_model_to_dict(obj_user, bool_include_secrets) if obj_user else None

    async def find_by_login_id(self, str_login_id: str, bool_include_secrets: bool = True) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_user = await obj_session.scalar(
                select(User).where(User.str_login_id == str_login_id.strip().lower())
            )
            return _user_model_to_dict(obj_user, bool_include_secrets) if obj_user else None

    async def insert(self, dict_user: dict) -> str:
        str_user_id = str(dict_user.get("_id") or _new_id())
        dict_values = {
            str_field: dict_user[str_field]
            for str_field in _TUPLE_USER_FIELDS
            if str_field in dict_user
        }
        async with get_postgres_session() as obj_session:
            obj_session.add(User(str_id=str_user_id, **dict_values))
        return str_user_id

    async def update_by_id(self, str_user_id: str, dict_values: dict) -> bool:
        dict_allowed = {str_key: obj_value for str_key, obj_value in dict_values.items() if str_key in _TUPLE_USER_FIELDS}
        if not dict_allowed:
            return False
        async with get_postgres_session() as obj_session:
            result = await obj_session.execute(
                update(User).where(User.str_id == str_user_id).values(**dict_allowed)
            )
            return bool(result.rowcount)

    async def delete_by_id(self, str_user_id: str) -> bool:
        async with get_postgres_session() as obj_session:
            result = await obj_session.execute(delete(User).where(User.str_id == str_user_id))
            return bool(result.rowcount)

    async def count(self, str_status: str | None = None, str_role: str | None = None, str_search: str | None = None) -> int:
        obj_query = select(func.count()).select_from(User)
        obj_query = self._where(obj_query, str_status, str_role, str_search)
        async with get_postgres_session() as obj_session:
            return int(await obj_session.scalar(obj_query) or 0)

    async def list(
        self,
        str_status: str | None = None,
        str_search: str | None = None,
        int_skip: int = 0,
        int_limit: int | None = None,
        bool_ascending: bool = False,
    ) -> list[dict]:
        obj_query = self._where(select(User), str_status, None, str_search)
        obj_query = obj_query.order_by(User.dt_created_at.asc() if bool_ascending else User.dt_created_at.desc())
        obj_query = obj_query.offset(int_skip)
        if int_limit is not None:
            obj_query = obj_query.limit(int_limit)
        async with get_postgres_session() as obj_session:
            list_models = list((await obj_session.scalars(obj_query)).all())
        return [_user_model_to_dict(obj_user, False) for obj_user in list_models]

    async def list_by_ids(self, list_user_ids: list[str]) -> list[dict]:
        if not list_user_ids:
            return []
        async with get_postgres_session() as obj_session:
            list_models = list((await obj_session.scalars(
                select(User).where(User.str_id.in_(list_user_ids))
            )).all())
        return [_user_model_to_dict(obj_user, False) for obj_user in list_models]

    @staticmethod
    def _where(obj_query, str_status: str | None, str_role: str | None, str_search: str | None):
        if str_status:
            obj_query = obj_query.where(User.str_approval_status == str_status)
        if str_role:
            obj_query = obj_query.where(User.str_role == str_role)
        if str_search:
            str_value = (
                str_search.strip()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            str_pattern = f"%{str_value}%"
            obj_query = obj_query.where(or_(
                User.str_login_id.ilike(str_pattern, escape="\\"),
                User.str_name.ilike(str_pattern, escape="\\"),
                User.str_department.ilike(str_pattern, escape="\\"),
            ))
        return obj_query


class PostgresSessionStore:
    async def insert(self, dict_session: dict) -> str:
        str_session_id = str(dict_session.get("_id") or _new_id())
        dict_values = {
            str_field: dict_session[str_field]
            for str_field in _TUPLE_SESSION_FIELDS
            if str_field in dict_session
        }
        async with get_postgres_session() as obj_session:
            await obj_session.execute(
                delete(Session).where(Session.dt_expires_at <= datetime.now(timezone.utc))
            )
            obj_session.add(Session(str_id=str_session_id, **dict_values))
        return str_session_id

    async def claim_rotation(self, str_refresh_token: str, str_replacement: str, dt_rotated_at: datetime) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_session_model = await obj_session.scalar(
                update(Session)
                .where(
                    Session.str_refresh_token == str_refresh_token,
                    Session.bool_is_revoked.is_(False),
                )
                .values(
                    bool_is_revoked=True,
                    dt_rotated_at=dt_rotated_at,
                    str_replaced_by=str_replacement,
                )
                .returning(Session)
            )
            return _session_model_to_dict(obj_session_model) if obj_session_model else None

    async def find_by_token(self, str_refresh_token: str, bool_only_active: bool = False) -> dict | None:
        obj_query = select(Session).where(Session.str_refresh_token == str_refresh_token)
        if bool_only_active:
            obj_query = obj_query.where(Session.bool_is_revoked.is_(False))
        async with get_postgres_session() as obj_session:
            obj_model = await obj_session.scalar(obj_query)
            return _session_model_to_dict(obj_model) if obj_model else None

    async def revoke_for_user(self, str_user_id: str, bool_only_active: bool = True) -> int:
        obj_query = update(Session).where(Session.str_user_id == str_user_id)
        if bool_only_active:
            obj_query = obj_query.where(Session.bool_is_revoked.is_(False))
        async with get_postgres_session() as obj_session:
            result = await obj_session.execute(obj_query.values(bool_is_revoked=True))
            return int(result.rowcount or 0)

    async def count(self) -> int:
        async with get_postgres_session() as obj_session:
            return int(await obj_session.scalar(select(func.count()).select_from(Session)) or 0)


_OBJ_POSTGRES_USERS = PostgresUserStore()
_OBJ_POSTGRES_SESSIONS = PostgresSessionStore()


def get_user_store() -> PostgresUserStore:
    return _OBJ_POSTGRES_USERS


def get_session_store() -> PostgresSessionStore:
    return _OBJ_POSTGRES_SESSIONS


def is_auth_store_connected() -> bool:
    return is_postgres_connected()
