#!/usr/bin/env python3
"""Idempotently copy audit, IP geo cache, and clinical data to PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient


PATH_BACKEND = Path(__file__).resolve().parent.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

from app.config import settings  # noqa: E402
from app.audit import (  # noqa: E402
    audit_hmac_key_fingerprint,
    compute_audit_seal_hmac,
    compute_audit_snapshot_digest,
    verify_log_hmac,
)
from app.postgres.database import connect_postgres, disconnect_postgres  # noqa: E402
from app.repositories.operational_store import (  # noqa: E402
    PostgresAuditIntegritySealStore,
    PostgresAuditStore,
    PostgresClinicalInfoStore,
    PostgresIpGeoStore,
)


def _with_string_id(dict_source: dict) -> dict:
    dict_target = dict(dict_source)
    dict_target["_id"] = str(dict_target["_id"])
    # PyMongo returns BSON UTC datetimes as naive by default.  Passing those
    # directly to TIMESTAMPTZ makes the client timezone shift the instant.
    for str_key, obj_value in list(dict_target.items()):
        if str_key.startswith("dt_") and isinstance(obj_value, datetime) and obj_value.tzinfo is None:
            dict_target[str_key] = obj_value.replace(tzinfo=timezone.utc)
    return dict_target


async def _migrate_collection(
    *, str_label: str, obj_collection, obj_store, str_natural_key: str | None,
    bool_dry_run: bool, list_sort: list[tuple[str, int]] | None = None,
) -> tuple[int, int]:
    int_inserted = 0
    int_existing = 0
    obj_cursor = obj_collection.find({})
    if list_sort:
        obj_cursor = obj_cursor.sort(list_sort)

    for dict_source in obj_cursor:
        dict_doc = _with_string_id(dict_source)
        str_id = dict_doc["_id"]
        str_hmac_status = None
        dt_hmac_created_at = None
        if str_label == "audit_logs":
            _, str_hmac_status, dt_hmac_created_at = verify_log_hmac(dict_doc)
            dict_doc["str_hmac_verification_status"] = str_hmac_status
            dict_doc["dt_hmac_created_at"] = dt_hmac_created_at
        dict_existing = await obj_store.find_by_id(str_id)
        if dict_existing is None and str_natural_key:
            obj_value = dict_doc.get(str_natural_key)
            if obj_value:
                if str_natural_key == "str_ip":
                    dict_existing = await obj_store.find(obj_value)
                elif str_natural_key == "str_case_name":
                    dict_existing = await obj_store.find(obj_value)
                if dict_existing is not None and dict_existing.get("_id") != str_id:
                    raise RuntimeError(
                        f"{str_label} natural-key conflict: {obj_value} "
                        f"(MongoDB ID={str_id}, PostgreSQL ID={dict_existing.get('_id')})"
                    )
        if dict_existing is not None:
            if str_natural_key and dict_existing.get(str_natural_key) != dict_doc.get(str_natural_key):
                raise RuntimeError(f"{str_label} ID conflict: {str_id}")
            if str_label == "audit_logs" and (
                dict_existing.get("str_action") != dict_doc.get("str_action")
                or dict_existing.get("str_hmac", "") != dict_doc.get("str_hmac", "")
            ):
                raise RuntimeError(f"audit_logs content conflict: {str_id}")
            if str_label == "audit_logs" and not bool_dry_run:
                await obj_store.update_verification_metadata(
                    str_id,
                    str_hmac_status,
                    dt_hmac_created_at,
                )
            int_existing += 1
            continue
        if not bool_dry_run:
            await obj_store.insert(dict_doc)
        int_inserted += 1
    return int_inserted, int_existing


async def _seal_migrated_audit_snapshot(obj_mongo_collection, obj_audit) -> dict:
    """HMAC-seal the exact ordered MongoDB snapshot after it reaches PostgreSQL."""
    list_source_ids = [
        str(dict_doc["_id"])
        for dict_doc in obj_mongo_collection.find({}, {"_id": 1}).sort([
            ("dt_created_at", 1), ("_id", 1),
        ])
    ]
    dict_target = {
        dict_log["_id"]: dict_log
        for dict_log in await obj_audit.list(bool_ascending=True)
    }
    list_snapshot = []
    for str_id in list_source_ids:
        if str_id not in dict_target:
            raise RuntimeError(f"Cannot seal missing PostgreSQL audit log: {str_id}")
        list_snapshot.append(dict_target[str_id])

    dict_status_counts: dict[str, int] = {}
    for dict_log in list_snapshot:
        str_status = dict_log.get("str_hmac_verification_status") or "unknown"
        dict_status_counts[str_status] = dict_status_counts.get(str_status, 0) + 1

    list_signed = sorted(
        [dict_log for dict_log in list_snapshot if dict_log.get("str_hmac")],
        key=lambda dict_log: (
            dict_log.get("dt_hmac_created_at") or dict_log.get("dt_created_at"),
            dict_log["_id"],
        ),
    )
    int_chain_discontinuities = 0
    str_previous_hmac = ""
    for dict_log in list_signed:
        if dict_log.get("str_prev_hmac", "") != str_previous_hmac:
            int_chain_discontinuities += 1
        str_previous_hmac = dict_log.get("str_hmac", "")

    str_scope = "mongodb_migration_v1"
    str_first_id = list_source_ids[0] if list_source_ids else ""
    str_last_id = list_source_ids[-1] if list_source_ids else ""
    str_digest = compute_audit_snapshot_digest(list_snapshot)
    int_count = len(list_snapshot)
    dt_now = datetime.now(timezone.utc)
    dict_seal = {
        "str_scope": str_scope,
        "int_record_count": int_count,
        "str_first_record_id": str_first_id,
        "str_last_record_id": str_last_id,
        "str_payload_sha256": str_digest,
        "str_hmac": compute_audit_seal_hmac(
            str_scope, int_count, str_first_id, str_last_id, str_digest,
        ),
        "str_key_fingerprint": audit_hmac_key_fingerprint(),
        "dict_summary": {
            "hmac_status_counts": dict_status_counts,
            "original_chain_discontinuities": int_chain_discontinuities,
            "source": "mongodb",
        },
        "dt_created_at": dt_now,
        "dt_updated_at": dt_now,
    }
    await PostgresAuditIntegritySealStore().upsert(dict_seal)
    return dict_seal


async def _migrate(bool_dry_run: bool) -> int:
    if not settings.POSTGRES_URI:
        print("[ERROR] POSTGRES_URI is required.")
        return 2

    obj_mongo_client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        obj_mongo_client.admin.command("ping")
        obj_db = obj_mongo_client[settings.MONGO_DB_NAME]
        dict_sources = {
            "audit_logs": obj_db.audit_logs.count_documents({}),
            "ip_geo_cache": obj_db.ip_geo_cache.count_documents({}),
            "case_clinical_info": obj_db.case_clinical_info.count_documents({}),
        }
        print("[INFO] MongoDB source: " + ", ".join(
            f"{str_name}={int_count}" for str_name, int_count in dict_sources.items()
        ))

        await connect_postgres()
        obj_audit = PostgresAuditStore()
        obj_geo = PostgresIpGeoStore()
        obj_clinical = PostgresClinicalInfoStore()

        list_jobs = [
            ("audit_logs", obj_db.audit_logs, obj_audit, None, [("dt_created_at", 1), ("_id", 1)]),
            ("ip_geo_cache", obj_db.ip_geo_cache, obj_geo, "str_ip", None),
            ("case_clinical_info", obj_db.case_clinical_info, obj_clinical, "str_case_name", None),
        ]
        for str_label, obj_collection, obj_store, str_natural_key, list_sort in list_jobs:
            int_inserted, int_existing = await _migrate_collection(
                str_label=str_label,
                obj_collection=obj_collection,
                obj_store=obj_store,
                str_natural_key=str_natural_key,
                bool_dry_run=bool_dry_run,
                list_sort=list_sort,
            )
            print(
                f"[{'DRY-RUN' if bool_dry_run else 'OK'}] {str_label}: "
                f"insert={int_inserted}, existing={int_existing}"
            )

        if not bool_dry_run:
            dict_targets = {
                "audit_logs": await obj_audit.count(),
                "ip_geo_cache": await obj_geo.count(),
                "case_clinical_info": await obj_clinical.count(),
            }
            for str_name, int_source in dict_sources.items():
                if dict_targets[str_name] < int_source:
                    raise RuntimeError(
                        f"Count mismatch for {str_name}: MongoDB={int_source}, "
                        f"PostgreSQL={dict_targets[str_name]}"
                    )
            dict_seal = await _seal_migrated_audit_snapshot(obj_db.audit_logs, obj_audit)
            print("[OK] verification: " + ", ".join(
                f"{str_name}={int_count}" for str_name, int_count in dict_targets.items()
            ))
            print(
                "[OK] audit snapshot seal: "
                f"records={dict_seal['int_record_count']}, "
                f"sha256={dict_seal['str_payload_sha256'][:16]}..., "
                f"status={dict_seal['dict_summary']['hmac_status_counts']}"
            )
        return 0
    finally:
        await disconnect_postgres()
        obj_mongo_client.close()


def main() -> int:
    obj_parser = argparse.ArgumentParser(
        description="Copy audit, IP geo cache, and clinical data from MongoDB to PostgreSQL.",
    )
    obj_parser.add_argument(
        "--dry-run", action="store_true",
        help="Check conflicts and report planned inserts without writing PostgreSQL.",
    )
    obj_args = obj_parser.parse_args()
    try:
        return asyncio.run(_migrate(obj_args.dry_run))
    except Exception as obj_error:
        print(f"[ERROR] Operational-data migration failed: {obj_error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
