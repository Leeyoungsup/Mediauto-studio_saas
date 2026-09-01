"""MongoDB text text text"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

# Global MongoDB connection state managed by the FastAPI lifespan.
_client: AsyncIOMotorClient = None
_db = None
_connected: bool = False
_main_loop: asyncio.AbstractEventLoop = None


async def connect_db():
    """text text text MongoDB text (text text text text)"""
    global _client, _db, _connected, _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
        _client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            tls=False,  # On-Premise text TLS text text True + text text
        )
        _db = _client[settings.MONGO_DB_NAME]

        # text text (ping)
        await _client.admin.command("ping")

        # Core indexes.
        await _db.users.create_index("str_login_id", unique=True)
        await _db.users.create_index("str_approval_status")
        await _db.sessions.create_index("str_refresh_token", unique=True)
        await _db.sessions.create_index("dt_expires_at", expireAfterSeconds=0)
        await _db.audit_logs.create_index("dt_created_at")
        await _db.audit_logs.create_index("str_user_id")
        await _db.audit_logs.create_index("str_action")
        await _db.audit_logs.create_index(
            [("str_user_id", 1), ("str_action", 1), ("dt_created_at", -1)]
        )
        await _db.audit_logs.create_index("str_hmac")

        # MongoDB TTL index for cached IP geolocation records.
        await _db.ip_geo_cache.create_index("str_ip", unique=True)
        await _db.ip_geo_cache.create_index("dt_expires_at", expireAfterSeconds=0)

        # Slide metadata indexes.
        await _db.slides.create_index(
            [("str_rel_path", 1), ("str_filename", 1)], unique=True
        )
        await _db.slides.create_index("str_slide_id")
        await _db.slides.create_index("dt_last_opened_at")

        # Folder/project configuration indexes.
        await _db.folder_ai_configs.create_index("str_rel_path", unique=True)
        await _db.folder_ai_configs.create_index("bool_enabled")

        await _db.project_infos.create_index("str_project_path", unique=True)
        await _db.project_infos.create_index("str_status")
        await _db.project_infos.create_index("bool_project_ai_enabled")
        await _db.project_infos.create_index("bool_annotation_ai_enabled")
        await _db.project_infos.create_index("str_annotation_ai_key")
        await _db.project_infos.create_index("dt_updated_at")
        await _db.annotation_required_regions.create_index("str_slide_id", unique=True)
        await _db.patch_annotation_status.create_index(
            [("str_slide_id", 1), ("str_patch_id", 1)],
            unique=True,
        )
        await _db.patch_annotation_status.create_index(
            [("str_slide_id", 1), ("str_status", 1), ("int_py", 1), ("int_px", 1)]
        )
        await _db.patch_cell_annotations.create_index(
            [("str_slide_id", 1), ("str_patch_id", 1)],
            unique=True,
        )

        # User-specific AI result edits.
        await _db.user_ai_edits.create_index(
            [
                ("str_slide_id", 1),
                ("str_ai_mode", 1),
                ("str_variant", 1),
                ("str_user_id", 1),
            ],
            unique=True,
        )
        await _db.user_ai_edits.create_index(
            [("str_slide_id", 1), ("str_ai_mode", 1), ("str_variant", 1)]
        )

        # Legacy approval-status migration.
        # Admin accounts are approved and active; other legacy accounts reset to pending.
        int_migrated_admin = (await _db.users.update_many(
            {
                "str_approval_status": {"$exists": False},
                "str_role": "admin",
            },
            {
                "$set": {
                    "str_approval_status": "approved",
                    "str_approved_by": "system",
                    "bool_is_active": True,
                }
            },
        )).modified_count
        int_migrated_pending = (await _db.users.update_many(
            {
                "str_approval_status": {"$exists": False},
                "str_role": {"$ne": "admin"},
            },
            {
                "$set": {
                    "str_approval_status": "pending",
                    "str_approved_by": "",
                    "bool_is_active": False,
                }
            },
        )).modified_count
        if int_migrated_admin or int_migrated_pending:
            print(
                f"[MeDIAuto SaaS] Approval migration: "
                f"admin approved: {int_migrated_admin}, reset to pending: {int_migrated_pending}"
            )

        # Legacy role migration. Technician was replaced by viewer.
        int_migrated_tech = (await _db.users.update_many(
            {"str_role": "technician"},
            {"$set": {"str_role": "viewer"}},
        )).modified_count
        if int_migrated_tech:
            print(
                f"[MeDIAuto SaaS] Role migration: "
                f"technician to viewer: {int_migrated_tech}"
            )

        _connected = True
        print(f"[MeDIAuto SaaS] MongoDB connected: {settings.MONGO_DB_NAME}")
    except Exception as e:
        _client = None
        _db = None
        _connected = False
        print(f"[MeDIAuto SaaS] MongoDB unavailable ({e}). Auth features disabled.")


async def disconnect_db():
    """text text text MongoDB text text"""
    global _client, _db, _connected
    if _client:
        _client.close()
        _client = None
        _db = None
        _connected = False
    print("[MeDIAuto SaaS] MongoDB disconnected")


def is_db_connected() -> bool:
    """Return readiness for the configured application persistence backend."""
    if settings.DATABASE_BACKEND == "postgresql":
        from app.postgres.database import is_postgres_connected
        return is_postgres_connected()
    return _connected


def get_main_loop() -> asyncio.AbstractEventLoop:
    """Return the main event loop used for thread-safe async DB calls."""
    return _main_loop


def initialize_main_loop() -> None:
    """Record the application loop when MongoDB startup is intentionally skipped."""
    global _main_loop
    _main_loop = asyncio.get_running_loop()


def get_db():
    """Return the configured application database facade."""
    if settings.DATABASE_BACKEND == "postgresql":
        from app.repositories.application_store import get_application_db
        from app.postgres.database import is_postgres_connected
        if not is_postgres_connected():
            raise RuntimeError("PostgreSQL is not connected.")
        return get_application_db()
    if _db is None:
        raise RuntimeError("Database not connected. MongoDB is required for auth features.")
    return _db


def get_mongo_db():
    """Return MongoDB explicitly for rollback-only repository implementations."""
    if _db is None:
        raise RuntimeError("MongoDB is not connected.")
    return _db
