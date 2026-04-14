"""MongoDB 비동기 연결 관리"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

# ── 모듈 레벨 싱글톤 (lifespan에서 connect/disconnect) ──
_client: AsyncIOMotorClient = None
_db = None
_connected: bool = False
_main_loop: asyncio.AbstractEventLoop = None


async def connect_db():
    """앱 시작 시 MongoDB 연결 (실패해도 앱은 계속 동작)"""
    global _client, _db, _connected, _main_loop
    try:
        _main_loop = asyncio.get_running_loop()
        _client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=5000,
            tls=False,  # On-Premise 환경에서 TLS 설정 시 True + 인증서 경로
        )
        _db = _client[settings.MONGO_DB_NAME]

        # 연결 테스트 (ping)
        await _client.admin.command("ping")

        # ── 인덱스 생성 (멱등) ──
        await _db.users.create_index("str_login_id", unique=True)
        await _db.users.create_index("str_approval_status")
        await _db.sessions.create_index("str_refresh_token", unique=True)
        await _db.sessions.create_index("dt_expires_at", expireAfterSeconds=0)
        await _db.audit_logs.create_index("dt_created_at")
        await _db.audit_logs.create_index("str_user_id")

        # ── slides 컬렉션 인덱스 ──
        await _db.slides.create_index(
            [("str_rel_path", 1), ("str_filename", 1)], unique=True
        )
        await _db.slides.create_index("str_slide_id")
        await _db.slides.create_index("dt_last_opened_at")

        # ── folder_ai_configs 컬렉션 ──
        await _db.folder_ai_configs.create_index("str_rel_path", unique=True)
        await _db.folder_ai_configs.create_index("bool_enabled")

        # ── 승인 상태 마이그레이션 ──
        # str_approval_status 필드 없는 기존 사용자 처리:
        #   - admin → approved + is_active=True 유지
        #   - 그 외 → pending + is_active=False (재승인 필요)
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
                f"[MeDICus SaaS] Approval migration — "
                f"admin approved: {int_migrated_admin}, reset to pending: {int_migrated_pending}"
            )

        # ── technician 역할 제거 마이그레이션 ──
        # 제품 정책 변경: technician 역할 폐지. 기존 technician 사용자는
        # viewer 로 downgrade (권한 확대 방지를 위해 doctor 가 아닌 viewer 로).
        int_migrated_tech = (await _db.users.update_many(
            {"str_role": "technician"},
            {"$set": {"str_role": "viewer"}},
        )).modified_count
        if int_migrated_tech:
            print(
                f"[MeDICus SaaS] Role migration — "
                f"technician → viewer: {int_migrated_tech}"
            )

        _connected = True
        print(f"[MeDICus SaaS] MongoDB connected: {settings.MONGO_DB_NAME}")
    except Exception as e:
        _client = None
        _db = None
        _connected = False
        print(f"[MeDICus SaaS] MongoDB unavailable ({e}). Auth features disabled.")


async def disconnect_db():
    """앱 종료 시 MongoDB 연결 해제"""
    global _client, _db, _connected
    if _client:
        _client.close()
        _client = None
        _db = None
        _connected = False
    print("[MeDICus SaaS] MongoDB disconnected")


def is_db_connected() -> bool:
    """MongoDB 연결 여부 확인"""
    return _connected


def get_main_loop() -> asyncio.AbstractEventLoop:
    """메인 이벤트 루프 반환 — 백그라운드 스레드에서 async DB 호출 스케줄용."""
    return _main_loop


def get_db():
    """현재 DB 인스턴스 반환"""
    if _db is None:
        raise RuntimeError("Database not connected. MongoDB is required for auth features.")
    return _db
