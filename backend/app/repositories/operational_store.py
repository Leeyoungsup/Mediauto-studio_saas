"""Backend-neutral persistence for audit, IP geo cache, and clinical data."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from app.postgres.database import get_postgres_session, is_postgres_connected
from app.postgres.models import AuditIntegritySeal, AuditLog, CaseClinicalInfo, IpGeoCache


_AUDIT_FIELDS = (
    "str_action", "str_user_id", "str_user_email", "str_resource_type",
    "str_resource_id", "str_detail", "str_ip_address", "str_user_agent",
    "dt_created_at", "str_prev_hmac", "str_hmac", "dict_before", "dict_after",
    "dt_hmac_created_at", "str_hmac_verification_status",
    "str_country", "str_country_name", "str_city", "str_region",
)
_AUDIT_DEFAULTS = {
    "str_action": "", "str_detail": "", "str_ip_address": "",
    "str_user_agent": "", "str_prev_hmac": "", "str_hmac": "",
    "str_country": "", "str_country_name": "", "str_city": "", "str_region": "",
}
_GEO_FIELDS = (
    "str_ip", "str_country", "str_country_name", "str_city", "str_region",
    "dt_expires_at", "dt_updated_at",
)
_CLINICAL_FIELDS = (
    "str_case_name", "dict_clinical_info", "dt_created_at", "dt_updated_at",
)
_SEAL_FIELDS = (
    "str_scope", "int_record_count", "str_first_record_id", "str_last_record_id",
    "str_payload_sha256", "str_hmac", "str_key_fingerprint", "dict_summary",
    "dt_created_at", "dt_updated_at",
)


def _new_id() -> str:
    return secrets.token_hex(12)


def _json_safe(obj_value):
    if obj_value is None or isinstance(obj_value, (str, int, float, bool)):
        return obj_value
    if isinstance(obj_value, datetime):
        return obj_value.isoformat()
    if isinstance(obj_value, dict):
        return {str(str_key): _json_safe(obj_item) for str_key, obj_item in obj_value.items()}
    if isinstance(obj_value, (list, tuple)):
        return [_json_safe(obj_item) for obj_item in obj_value]
    # Decimal-like values, UUID, bytes, and other custom scalar types cannot be
    # serialized by SQLAlchemy's JSON encoder directly.
    return str(obj_value)


def _audit_values(dict_log: dict) -> tuple[str, dict]:
    str_id = str(dict_log.get("_id") or _new_id())
    dict_values = {
        str_field: dict_log[str_field]
        for str_field in _AUDIT_FIELDS
        if str_field in dict_log
    }
    for str_field, obj_default in _AUDIT_DEFAULTS.items():
        dict_values.setdefault(str_field, obj_default)
    dict_values.setdefault("dt_created_at", datetime.now(timezone.utc))
    for str_field in ("dict_before", "dict_after"):
        if str_field in dict_values:
            dict_values[str_field] = _json_safe(dict_values[str_field])
    dict_values["dict_extra"] = {
        str_key: _json_safe(obj_value)
        for str_key, obj_value in dict_log.items()
        if str_key not in _AUDIT_FIELDS and str_key not in {"_id", "dict_extra"}
    }
    dict_values["dict_extra"].update(_json_safe(dict_log.get("dict_extra") or {}))
    return str_id, dict_values


def _audit_model_to_dict(obj_log: AuditLog) -> dict:
    dict_log = {"_id": obj_log.str_id}
    for str_field in _AUDIT_FIELDS:
        obj_value = getattr(obj_log, str_field)
        # Nullable HMAC input fields must remain explicit None values.  The
        # The original imported document hashes str(None), not an absent key's "".
        if obj_value is not None or str_field in {
            "str_user_id", "str_user_email", "str_resource_type", "str_resource_id",
        }:
            dict_log[str_field] = obj_value
    for str_key, obj_value in (obj_log.dict_extra or {}).items():
        dict_log.setdefault(str_key, obj_value)
    return dict_log


def _geo_model_to_dict(obj_geo: IpGeoCache) -> dict:
    dict_geo = {"_id": obj_geo.str_id}
    for str_field in _GEO_FIELDS:
        dict_geo[str_field] = getattr(obj_geo, str_field)
    return dict_geo


def _clinical_model_to_dict(obj_info: CaseClinicalInfo) -> dict:
    dict_info = {"_id": obj_info.str_id}
    for str_field in _CLINICAL_FIELDS:
        dict_info[str_field] = getattr(obj_info, str_field)
    return dict_info


def _seal_model_to_dict(obj_seal: AuditIntegritySeal) -> dict:
    dict_seal = {"_id": obj_seal.str_id}
    for str_field in _SEAL_FIELDS:
        dict_seal[str_field] = getattr(obj_seal, str_field)
    return dict_seal


class PostgresAuditStore:
    @staticmethod
    def _where(obj_query, str_user_id=None, str_action_exact=None, str_action_search=None,
               str_action_prefix=None, list_actions=None, dt_start=None, dt_end=None):
        if str_user_id:
            obj_query = obj_query.where(AuditLog.str_user_id == str_user_id)
        if str_action_exact:
            obj_query = obj_query.where(AuditLog.str_action == str_action_exact)
        elif str_action_search:
            str_value = str_action_search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            obj_query = obj_query.where(AuditLog.str_action.ilike(f"%{str_value}%", escape="\\"))
        elif str_action_prefix:
            str_value = str_action_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            obj_query = obj_query.where(AuditLog.str_action.like(f"{str_value}%", escape="\\"))
        elif list_actions:
            obj_query = obj_query.where(AuditLog.str_action.in_(list_actions))
        if dt_start:
            obj_query = obj_query.where(AuditLog.dt_created_at >= dt_start)
        if dt_end:
            obj_query = obj_query.where(AuditLog.dt_created_at < dt_end)
        return obj_query

    async def latest_hmac(self) -> str:
        async with get_postgres_session() as obj_session:
            obj_value = await obj_session.scalar(
                select(AuditLog.str_hmac).order_by(AuditLog.dt_created_at.desc(), AuditLog.str_id.desc()).limit(1)
            )
            return obj_value or ""

    async def find_by_id(self, str_id: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_log = await obj_session.get(AuditLog, str_id)
            return _audit_model_to_dict(obj_log) if obj_log else None

    async def insert(self, dict_log: dict) -> str:
        str_id, dict_values = _audit_values(dict_log)
        async with get_postgres_session() as obj_session:
            obj_session.add(AuditLog(str_id=str_id, **dict_values))
        return str_id

    async def update_geo(self, str_id: str, dict_geo: dict) -> bool:
        async with get_postgres_session() as obj_session:
            result = await obj_session.execute(update(AuditLog).where(AuditLog.str_id == str_id).values(
                str_country=dict_geo.get("country", ""),
                str_country_name=dict_geo.get("country_name", ""),
                str_city=dict_geo.get("city", ""),
                str_region=dict_geo.get("region", ""),
            ))
            return bool(result.rowcount)

    async def update_verification_metadata(
        self,
        str_id: str,
        str_status: str,
        dt_hmac_created_at: datetime | None,
    ) -> bool:
        async with get_postgres_session() as obj_session:
            result = await obj_session.execute(
                update(AuditLog).where(AuditLog.str_id == str_id).values(
                    str_hmac_verification_status=str_status,
                    dt_hmac_created_at=dt_hmac_created_at,
                )
            )
            return bool(result.rowcount)

    async def list(self, int_skip=0, int_limit=None, bool_ascending=False, **kwargs) -> list[dict]:
        obj_query = self._where(select(AuditLog), **kwargs)
        obj_query = obj_query.order_by(
            AuditLog.dt_created_at.asc() if bool_ascending else AuditLog.dt_created_at.desc(),
            AuditLog.str_id.asc() if bool_ascending else AuditLog.str_id.desc(),
        ).offset(int_skip)
        if int_limit is not None:
            obj_query = obj_query.limit(int_limit)
        async with get_postgres_session() as obj_session:
            list_logs = list((await obj_session.scalars(obj_query)).all())
        return [_audit_model_to_dict(obj_log) for obj_log in list_logs]

    async def count(self, **kwargs) -> int:
        obj_query = self._where(select(func.count()).select_from(AuditLog), **kwargs)
        async with get_postgres_session() as obj_session:
            return int(await obj_session.scalar(obj_query) or 0)


class PostgresIpGeoStore:
    async def find(self, str_ip: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_geo = await obj_session.scalar(select(IpGeoCache).where(IpGeoCache.str_ip == str_ip))
            return _geo_model_to_dict(obj_geo) if obj_geo else None

    async def find_by_id(self, str_id: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_geo = await obj_session.get(IpGeoCache, str_id)
            return _geo_model_to_dict(obj_geo) if obj_geo else None

    async def insert(self, dict_geo: dict) -> str:
        str_id = str(dict_geo.get("_id") or _new_id())
        dict_values = {str_field: dict_geo[str_field] for str_field in _GEO_FIELDS if str_field in dict_geo}
        async with get_postgres_session() as obj_session:
            obj_session.add(IpGeoCache(str_id=str_id, **dict_values))
        return str_id

    async def upsert(self, str_ip: str, dict_values: dict) -> None:
        dict_row = {str_field: dict_values[str_field] for str_field in _GEO_FIELDS if str_field in dict_values}
        dict_row.update({"id": _new_id(), "str_ip": str_ip})
        obj_statement = postgres_insert(IpGeoCache).values(**dict_row)
        dict_update = {str_field: getattr(obj_statement.excluded, str_field) for str_field in _GEO_FIELDS if str_field != "str_ip"}
        async with get_postgres_session() as obj_session:
            await obj_session.execute(obj_statement.on_conflict_do_update(index_elements=[IpGeoCache.str_ip], set_=dict_update))

    async def count(self) -> int:
        async with get_postgres_session() as obj_session:
            return int(await obj_session.scalar(select(func.count()).select_from(IpGeoCache)) or 0)


class PostgresClinicalInfoStore:
    async def find(self, str_case_name: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_info = await obj_session.scalar(select(CaseClinicalInfo).where(CaseClinicalInfo.str_case_name == str_case_name))
            return _clinical_model_to_dict(obj_info) if obj_info else None

    async def find_by_id(self, str_id: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_info = await obj_session.get(CaseClinicalInfo, str_id)
            return _clinical_model_to_dict(obj_info) if obj_info else None

    async def find_many(self, list_case_names: list[str]) -> list[dict]:
        if not list_case_names:
            return []
        async with get_postgres_session() as obj_session:
            list_info = list((await obj_session.scalars(select(CaseClinicalInfo).where(CaseClinicalInfo.str_case_name.in_(list_case_names)))).all())
        return [_clinical_model_to_dict(obj_info) for obj_info in list_info]

    async def list_all(self) -> list[dict]:
        async with get_postgres_session() as obj_session:
            list_info = list((await obj_session.scalars(select(CaseClinicalInfo))).all())
        return [_clinical_model_to_dict(obj_info) for obj_info in list_info]

    async def insert(self, dict_info: dict) -> str:
        str_id = str(dict_info.get("_id") or _new_id())
        dict_values = {str_field: dict_info[str_field] for str_field in _CLINICAL_FIELDS if str_field in dict_info}
        async with get_postgres_session() as obj_session:
            obj_session.add(CaseClinicalInfo(str_id=str_id, **dict_values))
        return str_id

    async def upsert(self, str_case_name: str, dict_clinical_info: dict, dt_now: datetime) -> None:
        obj_statement = postgres_insert(CaseClinicalInfo).values(
            id=_new_id(), str_case_name=str_case_name, dict_clinical_info=dict_clinical_info,
            dt_created_at=dt_now, dt_updated_at=dt_now,
        )
        async with get_postgres_session() as obj_session:
            await obj_session.execute(obj_statement.on_conflict_do_update(
                index_elements=[CaseClinicalInfo.str_case_name],
                set_={"dict_clinical_info": obj_statement.excluded.dict_clinical_info, "dt_updated_at": dt_now},
            ))

    async def count(self) -> int:
        async with get_postgres_session() as obj_session:
            return int(await obj_session.scalar(select(func.count()).select_from(CaseClinicalInfo)) or 0)


class PostgresAuditIntegritySealStore:
    async def get(self, str_scope: str) -> dict | None:
        async with get_postgres_session() as obj_session:
            obj_seal = await obj_session.scalar(
                select(AuditIntegritySeal).where(AuditIntegritySeal.str_scope == str_scope)
            )
            return _seal_model_to_dict(obj_seal) if obj_seal else None

    async def upsert(self, dict_seal: dict) -> str:
        str_id = str(dict_seal.get("_id") or _new_id())
        dict_values = {
            str_field: dict_seal[str_field]
            for str_field in _SEAL_FIELDS
            if str_field in dict_seal
        }
        obj_statement = postgres_insert(AuditIntegritySeal).values(id=str_id, **dict_values)
        set_values = {
            str_field: getattr(obj_statement.excluded, str_field)
            for str_field in _SEAL_FIELDS
            if str_field not in {"str_scope", "dt_created_at"}
        }
        async with get_postgres_session() as obj_session:
            await obj_session.execute(obj_statement.on_conflict_do_update(
                index_elements=[AuditIntegritySeal.str_scope],
                set_=set_values,
            ))
        return str_id


_POSTGRES_AUDIT = PostgresAuditStore()
_POSTGRES_GEO = PostgresIpGeoStore()
_POSTGRES_CLINICAL = PostgresClinicalInfoStore()
_POSTGRES_AUDIT_SEALS = PostgresAuditIntegritySealStore()


def get_audit_store() -> PostgresAuditStore:
    return _POSTGRES_AUDIT


def get_ip_geo_store() -> PostgresIpGeoStore:
    return _POSTGRES_GEO


def get_clinical_info_store() -> PostgresClinicalInfoStore:
    return _POSTGRES_CLINICAL


def get_audit_integrity_seal_store() -> PostgresAuditIntegritySealStore:
    return _POSTGRES_AUDIT_SEALS


def is_operational_store_connected() -> bool:
    return is_postgres_connected()
