"""PostgreSQL-backed document API for application state.

This adapter implements the document operations used by slide, project,
AI-state, runtime-setting, and cell-annotation code while retaining their
established document shape and dotted-field update behaviour.
"""

from __future__ import annotations

import asyncio
import copy
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import JSONB

from app.postgres.database import get_postgres_session
from app.postgres.models import ApplicationDocument


APPLICATION_COLLECTIONS = (
    "slides",
    "folder_ai_configs",
    "project_infos",
    "annotation_required_regions",
    "patch_annotation_status",
    "patch_cell_annotations",
    "user_ai_edits",
    "app_settings",
)

_TYPE_KEY = "__mediauto_pg_type__"
_VALUE_KEY = "value"
_MISSING = object()
_DICT_LOCKS = {str_name: asyncio.Lock() for str_name in APPLICATION_COLLECTIONS}


def encode_document_value(obj_value: Any) -> Any:
    """Convert Python-only values to lossless JSONB values."""
    if isinstance(obj_value, datetime):
        obj_dt = obj_value
        if obj_dt.tzinfo is None:
            obj_dt = obj_dt.replace(tzinfo=timezone.utc)
        return {_TYPE_KEY: "datetime", _VALUE_KEY: obj_dt.isoformat()}
    if isinstance(obj_value, dict):
        return {str(k): encode_document_value(v) for k, v in obj_value.items()}
    if isinstance(obj_value, (list, tuple)):
        return [encode_document_value(v) for v in obj_value]
    return obj_value


def decode_document_value(obj_value: Any) -> Any:
    """Restore datetimes and legacy tagged identifiers read from JSONB."""
    if isinstance(obj_value, dict):
        if obj_value.get(_TYPE_KEY) == "datetime" and _VALUE_KEY in obj_value:
            return datetime.fromisoformat(str(obj_value[_VALUE_KEY]))
        if obj_value.get(_TYPE_KEY) == "object_id" and _VALUE_KEY in obj_value:
            # Compatibility with documents imported during the datastore
            # cutover. PostgreSQL IDs are plain strings after that migration.
            return str(obj_value[_VALUE_KEY])
        return {k: decode_document_value(v) for k, v in obj_value.items()}
    if isinstance(obj_value, list):
        return [decode_document_value(v) for v in obj_value]
    return obj_value


def _get_path(dict_doc: dict, str_path: str) -> Any:
    obj_value: Any = dict_doc
    for str_part in str_path.split("."):
        if not isinstance(obj_value, dict) or str_part not in obj_value:
            return _MISSING
        obj_value = obj_value[str_part]
    return obj_value


def _set_path(dict_doc: dict, str_path: str, obj_value: Any) -> None:
    list_parts = str_path.split(".")
    dict_target = dict_doc
    for str_part in list_parts[:-1]:
        obj_next = dict_target.get(str_part)
        if not isinstance(obj_next, dict):
            obj_next = {}
            dict_target[str_part] = obj_next
        dict_target = obj_next
    dict_target[list_parts[-1]] = copy.deepcopy(obj_value)


def _values_equal(obj_actual: Any, obj_expected: Any) -> bool:
    if isinstance(obj_actual, list) and not isinstance(obj_expected, list):
        return any(_values_equal(obj_item, obj_expected) for obj_item in obj_actual)
    return obj_actual == obj_expected


def _regex_matches(obj_actual: Any, obj_pattern: Any, str_options: str = "") -> bool:
    if obj_actual is _MISSING or obj_actual is None:
        return False
    int_flags = re.IGNORECASE if "i" in str_options else 0
    if hasattr(obj_pattern, "search"):
        return bool(obj_pattern.search(str(obj_actual)))
    return bool(re.search(str(obj_pattern), str(obj_actual), flags=int_flags))


def _match_condition(obj_actual: Any, obj_condition: Any) -> bool:
    if not isinstance(obj_condition, dict) or not any(
        str(key).startswith("$") for key in obj_condition
    ):
        return obj_actual is not _MISSING and _values_equal(obj_actual, obj_condition)

    str_options = str(obj_condition.get("$options", ""))
    for str_operator, obj_expected in obj_condition.items():
        if str_operator == "$options":
            continue
        if str_operator == "$exists":
            if (obj_actual is not _MISSING) != bool(obj_expected):
                return False
        elif str_operator == "$ne":
            if obj_actual is not _MISSING and _values_equal(obj_actual, obj_expected):
                return False
        elif str_operator == "$in":
            if obj_actual is _MISSING or not any(
                _values_equal(obj_actual, obj_candidate) for obj_candidate in obj_expected
            ):
                return False
        elif str_operator == "$nin":
            if obj_actual is not _MISSING and any(
                _values_equal(obj_actual, obj_candidate) for obj_candidate in obj_expected
            ):
                return False
        elif str_operator == "$regex":
            if not _regex_matches(obj_actual, obj_expected, str_options):
                return False
        elif str_operator == "$not":
            if _match_condition(obj_actual, obj_expected):
                return False
        elif str_operator in {"$gt", "$gte", "$lt", "$lte"}:
            if obj_actual is _MISSING or obj_actual is None:
                return False
            try:
                if str_operator == "$gt" and not obj_actual > obj_expected:
                    return False
                if str_operator == "$gte" and not obj_actual >= obj_expected:
                    return False
                if str_operator == "$lt" and not obj_actual < obj_expected:
                    return False
                if str_operator == "$lte" and not obj_actual <= obj_expected:
                    return False
            except TypeError:
                return False
        else:
            raise NotImplementedError(f"Unsupported document query operator: {str_operator}")
    return True


def document_matches(dict_doc: dict, dict_filter: dict | None) -> bool:
    dict_filter = dict_filter or {}
    for str_key, obj_condition in dict_filter.items():
        if str_key == "$or":
            if not any(document_matches(dict_doc, d) for d in obj_condition):
                return False
        elif str_key == "$and":
            if not all(document_matches(dict_doc, d) for d in obj_condition):
                return False
        elif not _match_condition(_get_path(dict_doc, str_key), obj_condition):
            return False
    return True


def apply_projection(dict_doc: dict, dict_projection: dict | None) -> dict:
    if not dict_projection:
        return copy.deepcopy(dict_doc)
    bool_include = any(bool(v) for k, v in dict_projection.items() if k != "_id")
    if bool_include:
        dict_result = {}
        if dict_projection.get("_id", 1) and "_id" in dict_doc:
            dict_result["_id"] = copy.deepcopy(dict_doc["_id"])
        for str_key, obj_enabled in dict_projection.items():
            if str_key == "_id" or not obj_enabled:
                continue
            obj_value = _get_path(dict_doc, str_key)
            if obj_value is not _MISSING:
                _set_path(dict_result, str_key, obj_value)
        return dict_result
    dict_result = copy.deepcopy(dict_doc)
    for str_key, obj_enabled in dict_projection.items():
        if obj_enabled:
            continue
        list_parts = str_key.split(".")
        dict_target = dict_result
        for str_part in list_parts[:-1]:
            dict_target = dict_target.get(str_part)
            if not isinstance(dict_target, dict):
                break
        else:
            dict_target.pop(list_parts[-1], None)
    return dict_result


def _natural_keys(str_collection: str, dict_doc: dict) -> tuple[str, str]:
    if str_collection == "slides":
        return str(dict_doc.get("str_rel_path", "")), str(dict_doc.get("str_filename", ""))
    if str_collection == "folder_ai_configs":
        return str(dict_doc.get("str_rel_path", "")), ""
    if str_collection == "project_infos":
        return str(dict_doc.get("str_project_path", "")), ""
    if str_collection == "annotation_required_regions":
        return str(dict_doc.get("str_slide_id", "")), ""
    if str_collection in {"patch_annotation_status", "patch_cell_annotations"}:
        return str(dict_doc.get("str_slide_id", "")), str(dict_doc.get("str_patch_id", ""))
    if str_collection == "user_ai_edits":
        str_key = "\x1f".join([
            str(dict_doc.get("str_slide_id", "")),
            str(dict_doc.get("str_ai_mode", "")),
            str(dict_doc.get("str_variant", "")),
        ])
        return str_key, str(dict_doc.get("str_user_id", ""))
    return str(dict_doc.get("_id", "")), ""


def _new_document_from_upsert(dict_filter: dict, dict_update: dict) -> dict:
    dict_doc: dict[str, Any] = {}
    for str_key, obj_value in (dict_filter or {}).items():
        if not str_key.startswith("$") and not (
            isinstance(obj_value, dict) and any(str(k).startswith("$") for k in obj_value)
        ):
            _set_path(dict_doc, str_key, obj_value)
    for str_key, obj_value in dict_update.get("$setOnInsert", {}).items():
        _set_path(dict_doc, str_key, obj_value)
    _apply_update(dict_doc, dict_update)
    dict_doc.setdefault("_id", secrets.token_hex(12))
    return dict_doc


def _apply_update(dict_doc: dict, dict_update: dict) -> None:
    if not any(str(k).startswith("$") for k in dict_update):
        obj_id = dict_doc.get("_id") or secrets.token_hex(12)
        dict_doc.clear()
        dict_doc.update(copy.deepcopy(dict_update))
        dict_doc.setdefault("_id", obj_id)
        return
    for str_key, obj_value in dict_update.get("$set", {}).items():
        _set_path(dict_doc, str_key, obj_value)
    for str_key, obj_value in dict_update.get("$addToSet", {}).items():
        obj_list = _get_path(dict_doc, str_key)
        if not isinstance(obj_list, list):
            obj_list = []
            _set_path(dict_doc, str_key, obj_list)
        if obj_value not in obj_list:
            obj_list.append(copy.deepcopy(obj_value))


def _sort_value(obj_value: Any) -> tuple[int, Any]:
    if obj_value is _MISSING or obj_value is None:
        return (0, "")
    if isinstance(obj_value, datetime):
        obj_dt = obj_value if obj_value.tzinfo else obj_value.replace(tzinfo=timezone.utc)
        return (1, obj_dt.timestamp())
    if isinstance(obj_value, (int, float, bool, str)):
        return (1, obj_value)
    return (1, str(obj_value))


@dataclass
class DocumentWriteResult:
    matched_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    inserted_id: Any = None
    upserted_id: Any = None


class PostgresDocumentCursor:
    def __init__(self, obj_collection: "PostgresDocumentCollection", dict_filter: dict, dict_projection: dict | None):
        self._collection = obj_collection
        self._filter = dict_filter
        self._projection = dict_projection
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit: int | None = None

    def sort(self, obj_key, int_direction: int | None = None):
        self._sort = list(obj_key) if isinstance(obj_key, list) else [(str(obj_key), int_direction or 1)]
        return self

    def skip(self, int_count: int):
        self._skip = max(0, int(int_count))
        return self

    def limit(self, int_count: int):
        self._limit = max(0, int(int_count))
        return self

    async def _load(self, length: int | None = None) -> list[dict]:
        limit = self._limit
        if length is not None:
            limit = min(limit, max(0, length)) if limit is not None else max(0, length)
        if limit == 0:
            return []
        # Empty filters and ID lookups are exact SQL predicates. Push their
        # projection/pagination down without changing document matcher semantics.
        if not self._sort and (not self._filter or set(self._filter) == {"_id"}
                               and isinstance(self._filter["_id"], str)):
            return await self._collection._read_page(
                self._filter, self._projection, self._skip, limit)
        if not self._sort:
            return await self._collection._read_matching_page(
                self._filter, self._projection, self._skip, limit)
        list_docs = await self._collection._find_documents(self._filter)
        for str_key, int_direction in reversed(self._sort):
            list_docs.sort(
                key=lambda d: _sort_value(_get_path(d, str_key)),
                reverse=int_direction < 0,
            )
        list_docs = list_docs[self._skip:]
        if limit is not None:
            list_docs = list_docs[:limit]
        return [apply_projection(d, self._projection) for d in list_docs]

    async def to_list(self, length: int | None = None) -> list[dict]:
        return await self._load(None if length is None else int(length))

    def __aiter__(self) -> AsyncIterator[dict]:
        async def _iterate():
            for dict_doc in await self._load():
                yield dict_doc
        return _iterate()


class PostgresDocumentCollection:
    def __init__(self, str_name: str):
        if str_name not in APPLICATION_COLLECTIONS:
            raise AttributeError(f"Unsupported PostgreSQL application collection: {str_name}")
        self.name = str_name

    def _page_statement(self, dict_filter, projection, skip, limit):
        document = ApplicationDocument.dict_document
        # Top-level inclusion is common for dashboards. Select only requested
        # keys, preserving missing keys and explicit JSON null values.
        if projection and all("." not in key for key in projection):
            keys = [key for key, enabled in projection.items() if enabled and key != "_id"]
            if keys:
                if projection.get("_id", 1):
                    keys.append("_id")
                fields = func.jsonb_each(document).table_valued("key", "value")
                document = func.coalesce(
                    select(func.jsonb_object_agg(fields.c.key, fields.c.value))
                    .select_from(fields).where(fields.c.key.in_(keys))
                    .correlate(ApplicationDocument).scalar_subquery(), cast({}, JSONB))
        statement = self._candidate_statement(dict_filter).with_only_columns(document)
        if skip:
            statement = statement.offset(skip)
        if limit is not None:
            statement = statement.limit(limit)
        return statement

    async def _read_page(self, dict_filter, projection, skip, limit):
        async with get_postgres_session() as session:
            rows = await session.scalars(self._page_statement(dict_filter, projection, skip, limit))
            return [apply_projection(decode_document_value(row), projection) for row in rows]

    async def _read_matching_page(self, dict_filter, projection, skip, limit):
        # Complex predicates still use the exact Python matcher, but a small
        # page no longer materializes every candidate document in memory.
        result = []
        async with get_postgres_session() as session:
            rows = await session.stream_scalars(
                self._candidate_statement(dict_filter)
                .with_only_columns(ApplicationDocument.dict_document)
                .execution_options(yield_per=128))
            try:
                async for row in rows:
                    document = decode_document_value(row)
                    if not document_matches(document, dict_filter):
                        continue
                    if skip:
                        skip -= 1
                        continue
                    result.append(apply_projection(document, projection))
                    if limit is not None and len(result) >= limit:
                        break
            finally:
                await rows.close()
        return result

    def _candidate_statement(self, dict_filter: dict | None):
        """Build a narrow indexed candidate query before exact Python matching."""
        dict_filter = dict_filter or {}
        obj_statement = select(ApplicationDocument).where(
            ApplicationDocument.str_collection == self.name
        )
        obj_id = dict_filter.get("_id", _MISSING)
        if obj_id is not _MISSING and not isinstance(obj_id, dict):
            return obj_statement.where(ApplicationDocument.str_id == str(obj_id))

        dict_natural_fields = {
            "slides": ("str_rel_path", "str_filename"),
            "folder_ai_configs": ("str_rel_path",),
            "project_infos": ("str_project_path",),
            "annotation_required_regions": ("str_slide_id",),
            "patch_annotation_status": ("str_slide_id", "str_patch_id"),
            "patch_cell_annotations": ("str_slide_id", "str_patch_id"),
        }
        tuple_fields = dict_natural_fields.get(self.name, ())
        if tuple_fields and all(
            str_field in dict_filter and not isinstance(dict_filter[str_field], dict)
            for str_field in tuple_fields
        ):
            obj_statement = obj_statement.where(
                ApplicationDocument.str_natural_key == str(dict_filter[tuple_fields[0]])
            )
            if len(tuple_fields) > 1:
                obj_statement = obj_statement.where(
                    ApplicationDocument.str_secondary_key == str(dict_filter[tuple_fields[1]])
                )
            return obj_statement

        # GIN containment efficiently narrows common slide/status queries while
        # document_matches below remains the source of truth for document-query semantics.
        for str_key, obj_value in dict_filter.items():
            if str_key.startswith("$") or "." in str_key or isinstance(obj_value, dict):
                continue
            obj_statement = obj_statement.where(
                ApplicationDocument.dict_document.op("@>")(
                    cast(encode_document_value({str_key: obj_value}), JSONB)
                )
            )
        return obj_statement

    async def _find_documents(self, dict_filter: dict | None, *, bool_for_update: bool = False) -> list[dict]:
        async with get_postgres_session() as obj_session:
            obj_statement = self._candidate_statement(dict_filter)
            if bool_for_update:
                obj_statement = obj_statement.with_for_update()
            list_rows = list((await obj_session.scalars(obj_statement)).all())
            list_docs = [decode_document_value(row.dict_document) for row in list_rows]
            return [d for d in list_docs if document_matches(d, dict_filter)]

    def find(self, dict_filter: dict | None = None, dict_projection: dict | None = None) -> PostgresDocumentCursor:
        return PostgresDocumentCursor(self, dict_filter or {}, dict_projection)

    async def find_one(self, dict_filter: dict | None = None, dict_projection: dict | None = None) -> dict | None:
        list_docs = await self.find(dict_filter, dict_projection).limit(1).to_list(length=1)
        return list_docs[0] if list_docs else None

    async def count_documents(self, dict_filter: dict | None = None) -> int:
        if not dict_filter:
            async with get_postgres_session() as obj_session:
                return int(await obj_session.scalar(select(func.count()).select_from(ApplicationDocument).where(
                    ApplicationDocument.str_collection == self.name
                )) or 0)
        return len(await self._find_documents(dict_filter))

    async def insert_one(self, dict_document: dict) -> DocumentWriteResult:
        dict_doc = copy.deepcopy(dict_document)
        dict_doc.setdefault("_id", secrets.token_hex(12))
        str_id = str(dict_doc["_id"])
        str_natural, str_secondary = _natural_keys(self.name, dict_doc)
        dt_now = datetime.now(timezone.utc)
        async with _DICT_LOCKS[self.name]:
            async with get_postgres_session() as obj_session:
                obj_session.add(ApplicationDocument(
                    str_collection=self.name,
                    str_id=str_id,
                    str_natural_key=str_natural,
                    str_secondary_key=str_secondary,
                    dict_document=encode_document_value(dict_doc),
                    dt_created_at=dt_now,
                    dt_updated_at=dt_now,
                ))
        return DocumentWriteResult(inserted_id=dict_doc["_id"])

    async def update_one(self, dict_filter: dict, dict_update: dict, upsert: bool = False) -> DocumentWriteResult:
        return await self._update(dict_filter, dict_update, upsert=upsert, bool_many=False)

    async def update_many(self, dict_filter: dict, dict_update: dict, upsert: bool = False) -> DocumentWriteResult:
        return await self._update(dict_filter, dict_update, upsert=upsert, bool_many=True)

    async def _update(self, dict_filter: dict, dict_update: dict, *, upsert: bool, bool_many: bool) -> DocumentWriteResult:
        int_matched = 0
        int_modified = 0
        obj_upserted_id = None
        async with _DICT_LOCKS[self.name]:
            async with get_postgres_session() as obj_session:
                list_rows = list((await obj_session.scalars(
                    self._candidate_statement(dict_filter).with_for_update()
                )).all())
                for obj_row in list_rows:
                    dict_doc = decode_document_value(obj_row.dict_document)
                    if not document_matches(dict_doc, dict_filter):
                        continue
                    int_matched += 1
                    dict_before = copy.deepcopy(dict_doc)
                    _apply_update(dict_doc, dict_update)
                    if dict_doc != dict_before:
                        str_natural, str_secondary = _natural_keys(self.name, dict_doc)
                        obj_row.str_natural_key = str_natural
                        obj_row.str_secondary_key = str_secondary
                        obj_row.dict_document = encode_document_value(dict_doc)
                        obj_row.dt_updated_at = datetime.now(timezone.utc)
                        int_modified += 1
                    if not bool_many:
                        break
                if int_matched == 0 and upsert:
                    dict_doc = _new_document_from_upsert(dict_filter, dict_update)
                    str_id = str(dict_doc["_id"])
                    str_natural, str_secondary = _natural_keys(self.name, dict_doc)
                    dt_now = datetime.now(timezone.utc)
                    obj_session.add(ApplicationDocument(
                        str_collection=self.name,
                        str_id=str_id,
                        str_natural_key=str_natural,
                        str_secondary_key=str_secondary,
                        dict_document=encode_document_value(dict_doc),
                        dt_created_at=dt_now,
                        dt_updated_at=dt_now,
                    ))
                    obj_upserted_id = dict_doc["_id"]
        return DocumentWriteResult(
            matched_count=int_matched,
            modified_count=int_modified,
            upserted_id=obj_upserted_id,
        )

    async def delete_one(self, dict_filter: dict) -> DocumentWriteResult:
        return await self._delete(dict_filter, bool_many=False)

    async def delete_many(self, dict_filter: dict) -> DocumentWriteResult:
        return await self._delete(dict_filter, bool_many=True)

    async def _delete(self, dict_filter: dict, *, bool_many: bool) -> DocumentWriteResult:
        list_ids: list[str] = []
        async with _DICT_LOCKS[self.name]:
            async with get_postgres_session() as obj_session:
                list_rows = list((await obj_session.scalars(
                    self._candidate_statement(dict_filter)
                )).all())
                for obj_row in list_rows:
                    if document_matches(decode_document_value(obj_row.dict_document), dict_filter):
                        list_ids.append(obj_row.str_id)
                        if not bool_many:
                            break
                if list_ids:
                    await obj_session.execute(delete(ApplicationDocument).where(
                        ApplicationDocument.str_collection == self.name,
                        ApplicationDocument.str_id.in_(list_ids),
                    ))
        return DocumentWriteResult(deleted_count=len(list_ids))

    async def find_one_and_delete(self, dict_filter: dict) -> dict | None:
        dict_doc = await self.find_one(dict_filter)
        if dict_doc is not None:
            await self.delete_one({"_id": dict_doc.get("_id")})
        return dict_doc


class PostgresApplicationDatabase:
    """Attribute-compatible collection namespace used by existing callers."""

    def __init__(self):
        for str_name in APPLICATION_COLLECTIONS:
            setattr(self, str_name, PostgresDocumentCollection(str_name))

    def __getitem__(self, str_name: str) -> PostgresDocumentCollection:
        return getattr(self, str_name)


_APPLICATION_DB = PostgresApplicationDatabase()


def get_application_db() -> PostgresApplicationDatabase:
    return _APPLICATION_DB
