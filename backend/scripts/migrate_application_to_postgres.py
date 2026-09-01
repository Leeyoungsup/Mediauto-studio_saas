#!/usr/bin/env python3
"""Copy and verify project, slide, AI-state, and annotation data in PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient
from sqlalchemy import select


PATH_BACKEND = Path(__file__).resolve().parent.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

from app.config import settings  # noqa: E402
from app.postgres.database import connect_postgres, disconnect_postgres, get_postgres_session  # noqa: E402
from app.postgres.models import ApplicationDataMigration  # noqa: E402
from app.repositories.application_store import (  # noqa: E402
    APPLICATION_COLLECTIONS,
    encode_document_value,
    get_application_db,
)


MIGRATION_ID = "mongodb_application_state_v1"


def _normalize_source(obj_value):
    if isinstance(obj_value, datetime) and obj_value.tzinfo is None:
        return obj_value.replace(tzinfo=timezone.utc)
    if isinstance(obj_value, dict):
        return {str(k): _normalize_source(v) for k, v in obj_value.items()}
    if isinstance(obj_value, (list, tuple)):
        return [_normalize_source(v) for v in obj_value]
    return obj_value


def _canonical_document(dict_doc: dict) -> str:
    return json.dumps(
        encode_document_value(dict_doc),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _snapshot_digest(dict_documents: dict[str, list[dict]]) -> str:
    obj_hash = hashlib.sha256()
    for str_collection in sorted(dict_documents):
        for dict_doc in sorted(dict_documents[str_collection], key=lambda d: str(d.get("_id", ""))):
            obj_hash.update(str_collection.encode("utf-8"))
            obj_hash.update(b"\0")
            obj_hash.update(_canonical_document(dict_doc).encode("utf-8"))
            obj_hash.update(b"\n")
    return obj_hash.hexdigest()


async def _migrate(*, bool_dry_run: bool, bool_if_empty: bool) -> int:
    if not settings.POSTGRES_URI:
        print("[ERROR] POSTGRES_URI is required.")
        return 2

    obj_mongo = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        obj_mongo.admin.command("ping")
        obj_source_db = obj_mongo[settings.MONGO_DB_NAME]
        dict_source_docs = {
            str_name: [_normalize_source(d) for d in obj_source_db[str_name].find({})]
            for str_name in APPLICATION_COLLECTIONS
        }
        dict_source_counts = {k: len(v) for k, v in dict_source_docs.items()}
        print("[INFO] MongoDB source: " + ", ".join(
            f"{k}={v}" for k, v in dict_source_counts.items()
        ))

        await connect_postgres()
        obj_target_db = get_application_db()
        async with get_postgres_session() as obj_session:
            obj_marker = await obj_session.get(ApplicationDataMigration, MIGRATION_ID)
        if bool_if_empty and obj_marker is not None:
            print(
                f"[SKIP] Verified application migration already exists: "
                f"{obj_marker.str_payload_sha256}"
            )
            return 0

        for str_name, list_source in dict_source_docs.items():
            obj_collection = getattr(obj_target_db, str_name)
            int_inserted = 0
            int_existing = 0
            for dict_source in list_source:
                dict_existing = await obj_collection.find_one({"_id": dict_source.get("_id")})
                if dict_existing is not None:
                    if _canonical_document(dict_existing) != _canonical_document(dict_source):
                        raise RuntimeError(
                            f"Content conflict in {str_name}: _id={dict_source.get('_id')}"
                        )
                    int_existing += 1
                    continue
                if not bool_dry_run:
                    await obj_collection.insert_one(dict_source)
                int_inserted += 1
            print(
                f"[{'DRY-RUN' if bool_dry_run else 'OK'}] {str_name}: "
                f"insert={int_inserted}, existing={int_existing}"
            )

        if bool_dry_run:
            return 0

        dict_target_docs = {
            str_name: await getattr(obj_target_db, str_name).find({}).to_list(length=None)
            for str_name in APPLICATION_COLLECTIONS
        }
        dict_target_counts = {k: len(v) for k, v in dict_target_docs.items()}
        if dict_target_counts != dict_source_counts:
            raise RuntimeError(
                f"Count mismatch: source={dict_source_counts}, target={dict_target_counts}"
            )
        str_source_digest = _snapshot_digest(dict_source_docs)
        str_target_digest = _snapshot_digest(dict_target_docs)
        if str_source_digest != str_target_digest:
            raise RuntimeError(
                f"Snapshot digest mismatch: MongoDB={str_source_digest}, "
                f"PostgreSQL={str_target_digest}"
            )

        async with get_postgres_session() as obj_session:
            obj_marker = await obj_session.get(ApplicationDataMigration, MIGRATION_ID)
            if obj_marker is None:
                obj_marker = ApplicationDataMigration(str_id=MIGRATION_ID)
                obj_session.add(obj_marker)
            obj_marker.dict_source_counts = dict_source_counts
            obj_marker.dict_target_counts = dict_target_counts
            obj_marker.str_payload_sha256 = str_source_digest
            obj_marker.dt_completed_at = datetime.now(timezone.utc)
        print(
            f"[OK] Exact snapshot verified: records={sum(dict_target_counts.values())}, "
            f"sha256={str_source_digest}"
        )
        return 0
    finally:
        await disconnect_postgres()
        obj_mongo.close()


def main() -> int:
    obj_parser = argparse.ArgumentParser(description=__doc__)
    obj_parser.add_argument("--dry-run", action="store_true")
    obj_parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Skip only when the verified migration marker already exists.",
    )
    obj_args = obj_parser.parse_args()
    return asyncio.run(_migrate(bool_dry_run=obj_args.dry_run, bool_if_empty=obj_args.if_empty))


if __name__ == "__main__":
    raise SystemExit(main())
