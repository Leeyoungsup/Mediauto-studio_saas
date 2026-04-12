"""MongoDB 비동기 연결 관리"""

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

# ── 모듈 레벨 싱글톤 (lifespan에서 connect/disconnect) ──
_client: AsyncIOMotorClient = None
_db = None
_connected: bool = False


async def connect_db():
    """앱 시작 시 MongoDB 연결 (실패해도 앱은 계속 동작)"""
    global _client, _db, _connected
    try:
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
        await _db.sessions.create_index("str_refresh_token", unique=True)
        await _db.sessions.create_index("dt_expires_at", expireAfterSeconds=0)
        await _db.audit_logs.create_index("dt_created_at")
        await _db.audit_logs.create_index("str_user_id")

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


def get_db():
    """현재 DB 인스턴스 반환"""
    if _db is None:
        raise RuntimeError("Database not connected. MongoDB is required for auth features.")
    return _db
