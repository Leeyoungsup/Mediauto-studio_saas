"""Backend-neutral user and refresh-session persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from sqlalchemy import delete, func, or_, select, update

from app.config import settings
from app.database import get_db, is_db_connected
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
    """Keep IDs compatible with existing MongoDB/JWT ObjectId strings."""
    return str(ObjectId())


def _object_id_or_none(str_value: str) -> ObjectId | None:
    try:
        return ObjectId(str_value)
    except Exception:
        return None


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


class MongoUserStore:
    async def find_by_id(self, str_user_id: str, bool_include_secrets: bool = True) -> dict | None:
        obj_id = _object_id_or_none(str_user_id)
        if obj_id is None:
            return None
        dict_projection = None if bool_include_secrets else {
            "str_hashed_password": 0,
            "str_totp_secret_enc": 0,
        }
        return await get_db().users.find_one({"_id": obj_id}, dict_projection)

    async def find_by_login_id(self, str_login_id: str, bool_include_secrets: bool = True) -> dict | None:
        dict_projection = None if bool_include_secrets else {
            "str_hashed_password": 0,
            "str_totp_secret_enc": 0,
        }
        return await get_db().users.find_one(
            {"str_login_id": str_login_id.strip().lower()},
            dict_projection,
        )

    async def insert(self, dict_user: dict) -> str:
        result = await get_db().users.insert_one(dict_user)
        return str(result.inserted_id)

    async def update_by_id(self, str_user_id: str, dict_values: dict) -> bool:
        obj_id = _object_id_or_none(str_user_id)
        if obj_id is None:
            return False
        result = await get_db().users.update_one({"_id": obj_id}, {"$set": dict_values})
        return bool(result.matched_count)

    async def delete_by_id(self, str_user_id: str) -> bool:
        obj_id = _object_id_or_none(str_user_id)
        if obj_id is None:
            return False
        result = await get_db().users.delete_one({"_id": obj_id})
        return bool(result.deleted_count)

    async def count(self, str_status: str | None = None, str_role: str | None = None, str_search: str | None = None) -> int:
        dict_filter = self._filter(str_status, str_role, str_search)
        return await get_db().users.count_documents(dict_filter)

    async def list(
        self,
        str_status: str | None = None,
        str_search: str | None = None,
        int_skip: int = 0,
        int_limit: int | None = None,
        bool_ascending: bool = False,
    ) -> list[dict]:
        dict_projection = {
            str_field: 1
            for str_field in _TUPLE_USER_FIELDS
            if str_field not in {"str_hashed_password", "str_totp_secret_enc", "int_failed_login_attempts"}
        }
        cursor = get_db().users.find(
            self._filter(str_status, None, str_search),
            dict_projection,
        ).sort("dt_created_at", 1 if bool_ascending else -1).skip(int_skip)
        if int_limit is not None:
            cursor = cursor.limit(int_limit)
        list_users = []
        async for dict_user in cursor:
            dict_user["_id"] = str(dict_user["_id"])
            list_users.append(dict_user)
        return list_users

    async def list_by_ids(self, list_user_ids: list[str]) -> list[dict]:
        list_object_ids = [obj_id for str_id in list_user_ids if (obj_id := _object_id_or_none(str_id))]
        if not list_object_ids:
            return []
        cursor = get_db().users.find(
            {"_id": {"$in": list_object_ids}},
            {"str_login_id": 1, "str_name": 1, "str_role": 1, "str_department": 1},
        )
        list_users = []
        async for dict_user in cursor:
            dict_user["_id"] = str(dict_user["_id"])
            list_users.append(dict_user)
        return list_users

    @staticmethod
    def _filter(str_status: str | None, str_role: str | None, str_search: str | None) -> dict:
        dict_filter: dict[str, Any] = {}
        if str_status:
            dict_filter["str_approval_status"] = str_status
        if str_role:
            dict_filter["str_role"] = str_role
        if str_search:
            import re

            str_pattern = re.escape(str_search.strip())
            dict_filter["$or"] = [
                {"str_login_id": {"$regex": str_pattern, "$options": "i"}},
                {"str_name": {"$regex": str_pattern, "$options": "i"}},
                {"str_department": {"$regex": str_pattern, "$options": "i"}},
            ]
        return dict_filter


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


class MongoSessionStore:
    async def insert(self, dict_session: dict) -> str:
        result = await get_db().sessions.insert_one(dict_session)
        return str(result.inserted_id)

    async def claim_rotation(self, str_refresh_token: str, str_replacement: str, dt_rotated_at: datetime) -> dict | None:
        from pymongo import ReturnDocument

        return await get_db().sessions.find_one_and_update(
            {"str_refresh_token": str_refresh_token, "bool_is_revoked": False},
            {"$set": {
                "bool_is_revoked": True,
                "dt_rotated_at": dt_rotated_at,
                "str_replaced_by": str_replacement,
            }},
            return_document=ReturnDocument.AFTER,
        )

    async def find_by_token(self, str_refresh_token: str, bool_only_active: bool = False) -> dict | None:
        dict_filter: dict[str, Any] = {"str_refresh_token": str_refresh_token}
        if bool_only_active:
            dict_filter["bool_is_revoked"] = False
        return await get_db().sessions.find_one(dict_filter)

    async def revoke_for_user(self, str_user_id: str, bool_only_active: bool = True) -> int:
        dict_filter: dict[str, Any] = {"str_user_id": str_user_id}
        if bool_only_active:
            dict_filter["bool_is_revoked"] = False
        result = await get_db().sessions.update_many(dict_filter, {"$set": {"bool_is_revoked": True}})
        return int(result.modified_count)

    async def count(self) -> int:
        return await get_db().sessions.count_documents({})


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


_OBJ_MONGO_USERS = MongoUserStore()
_OBJ_POSTGRES_USERS = PostgresUserStore()
_OBJ_MONGO_SESSIONS = MongoSessionStore()
_OBJ_POSTGRES_SESSIONS = PostgresSessionStore()


def get_user_store() -> MongoUserStore | PostgresUserStore:
    return _OBJ_POSTGRES_USERS if settings.DATABASE_BACKEND == "postgresql" else _OBJ_MONGO_USERS


def get_session_store() -> MongoSessionStore | PostgresSessionStore:
    return _OBJ_POSTGRES_SESSIONS if settings.DATABASE_BACKEND == "postgresql" else _OBJ_MONGO_SESSIONS


def is_auth_store_connected() -> bool:
    return is_postgres_connected() if settings.DATABASE_BACKEND == "postgresql" else is_db_connected()
