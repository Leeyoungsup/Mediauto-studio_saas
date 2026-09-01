#!/usr/bin/env python3
"""Idempotently copy MongoDB users and refresh sessions to PostgreSQL."""

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
from app.postgres.database import connect_postgres, disconnect_postgres  # noqa: E402
from app.repositories.auth_store import PostgresSessionStore, PostgresUserStore  # noqa: E402


def _copy_document_with_string_id(dict_source: dict) -> dict:
    dict_target = dict(dict_source)
    dict_target["_id"] = str(dict_target["_id"])
    for str_key, obj_value in list(dict_target.items()):
        if str_key.startswith("dt_") and isinstance(obj_value, datetime) and obj_value.tzinfo is None:
            dict_target[str_key] = obj_value.replace(tzinfo=timezone.utc)
    return dict_target


async def _migrate(bool_dry_run: bool, bool_skip_sessions: bool) -> int:
    if not settings.POSTGRES_URI:
        print("[ERROR] POSTGRES_URI is required.")
        return 2

    obj_mongo_client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        obj_mongo_client.admin.command("ping")
        obj_mongo_db = obj_mongo_client[settings.MONGO_DB_NAME]
        int_source_users = obj_mongo_db.users.count_documents({})
        int_source_sessions = obj_mongo_db.sessions.count_documents({})
        print(
            f"[INFO] MongoDB source: {int_source_users} user(s), "
            f"{int_source_sessions} session(s)"
        )

        await connect_postgres()
        obj_users = PostgresUserStore()
        obj_sessions = PostgresSessionStore()

        int_users_inserted = 0
        int_users_skipped = 0
        for dict_mongo_user in obj_mongo_db.users.find({}):
            dict_user = _copy_document_with_string_id(dict_mongo_user)
            str_user_id = dict_user["_id"]
            dict_by_id = await obj_users.find_by_id(str_user_id)
            if dict_by_id is not None:
                if dict_by_id.get("str_login_id") != dict_user.get("str_login_id"):
                    raise RuntimeError(f"User ID conflict: {str_user_id}")
                int_users_skipped += 1
                continue
            dict_by_login = await obj_users.find_by_login_id(dict_user.get("str_login_id", ""))
            if dict_by_login is not None:
                raise RuntimeError(
                    "Login ID conflict with a different ID: "
                    f"{dict_user.get('str_login_id')}"
                )
            if not bool_dry_run:
                await obj_users.insert(dict_user)
            int_users_inserted += 1

        int_sessions_inserted = 0
        int_sessions_skipped = 0
        if not bool_skip_sessions:
            for dict_mongo_session in obj_mongo_db.sessions.find({}):
                dict_session = _copy_document_with_string_id(dict_mongo_session)
                str_token = dict_session.get("str_refresh_token", "")
                if not str_token:
                    raise RuntimeError(
                        f"Session has no refresh token: {dict_session['_id']}"
                    )
                if await obj_sessions.find_by_token(str_token) is not None:
                    int_sessions_skipped += 1
                    continue
                str_user_id = str(dict_session.get("str_user_id", ""))
                if await obj_users.find_by_id(str_user_id) is None and not bool_dry_run:
                    raise RuntimeError(
                        f"Session references a missing user: {dict_session['_id']}"
                    )
                if not bool_dry_run:
                    await obj_sessions.insert(dict_session)
                int_sessions_inserted += 1

        print(
            f"[{'DRY-RUN' if bool_dry_run else 'OK'}] users: "
            f"insert={int_users_inserted}, existing={int_users_skipped}"
        )
        if not bool_skip_sessions:
            print(
                f"[{'DRY-RUN' if bool_dry_run else 'OK'}] sessions: "
                f"insert={int_sessions_inserted}, existing={int_sessions_skipped}"
            )

        if not bool_dry_run:
            int_target_users = await obj_users.count()
            int_target_sessions = await obj_sessions.count()
            if int_target_users != int_source_users:
                raise RuntimeError(
                    f"User count mismatch: MongoDB={int_source_users}, PostgreSQL={int_target_users}"
                )
            if not bool_skip_sessions and int_target_sessions > int_source_sessions:
                raise RuntimeError(
                    "PostgreSQL contains more sessions than MongoDB; inspect before cutover."
                )
            print(
                f"[OK] verification: {int_target_users} user(s), "
                f"{int_target_sessions} non-expired session(s)"
            )
        return 0
    finally:
        await disconnect_postgres()
        obj_mongo_client.close()


def main() -> int:
    obj_parser = argparse.ArgumentParser(
        description="Copy authentication data from MongoDB to PostgreSQL.",
    )
    obj_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check conflicts and report planned inserts without writing PostgreSQL.",
    )
    obj_parser.add_argument(
        "--skip-sessions",
        action="store_true",
        help="Copy users only; all clients must sign in again after cutover.",
    )
    obj_args = obj_parser.parse_args()
    try:
        return asyncio.run(_migrate(obj_args.dry_run, obj_args.skip_sessions))
    except Exception as obj_error:
        print(f"[ERROR] Authentication migration failed: {obj_error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
