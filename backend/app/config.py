"""앱 설정"""

import os
import secrets
from pathlib import Path


class Settings:
    # 업로드 디렉토리 (서버 로컬 디스크 — 원본 WSI 저장)
    UPLOAD_DIR: str = os.environ.get(
        "UPLOAD_DIR",
        str(Path(__file__).parent.parent / "uploads")
    )

    # 프리타일 디렉토리 (뷰어용 JPEG 타일 캐시)
    TILES_DIR: str = os.environ.get(
        "TILES_DIR",
        str(Path(__file__).parent.parent / "tiles")
    )

    # AI 결과 캐시 디렉토리 (uploads와 분리)
    AI_RESULTS_DIR: str = os.environ.get(
        "AI_RESULTS_DIR",
        str(Path(__file__).parent.parent / "ai_results")
    )

    # 타일 설정
    TILE_SIZE: int = 512
    TILE_FORMAT: str = "JPEG"  # JPEG이 PNG보다 빠르고 작음
    TILE_QUALITY: int = 85

    # 청크 업로드 설정
    CHUNK_SIZE: int = 5 * 1024 * 1024  # 5MB

    # AI 모델 경로 (backend/model/)
    MODEL_DIR: str = str(Path(__file__).parent.parent / "model")

    # 지원 확장자
    SUPPORTED_EXTENSIONS: set = {
        ".svs", ".ndpi", ".vms", ".vmu", ".scn",
        ".mrxs", ".tiff", ".tif", ".png", ".jpg", ".jpeg",
    }

    # ── MongoDB 설정 (On-Premise) ──
    MONGO_URI: str = os.environ.get(
        "MONGO_URI",
        "mongodb://localhost:27017"
    )
    MONGO_DB_NAME: str = os.environ.get("MONGO_DB_NAME", "medicus_studio")

    # ── JWT 설정 ──
    JWT_SECRET_KEY: str = os.environ.get(
        "JWT_SECRET_KEY",
        secrets.token_urlsafe(64)
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 보안 설정 ──
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 30
    SESSION_INACTIVE_MINUTES: int = 30

    # ── 민감 필드 암호화 키 (AES-256-GCM) ──
    FIELD_ENCRYPTION_KEY: str = os.environ.get(
        "FIELD_ENCRYPTION_KEY",
        secrets.token_urlsafe(32)
    )


settings = Settings()
