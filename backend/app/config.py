"""앱 설정"""

import json
import os
import secrets
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
# 시크릿 영속화
# ──
# 환경변수(JWT_SECRET_KEY / FIELD_ENCRYPTION_KEY) 가 설정돼 있으면 그대로 사용.
# 없으면 `backend/.secrets.json` 에 자동 생성/로드 — 서버 재시작 시에도
# 같은 키가 유지되어 기존 토큰/암호화 필드가 깨지지 않음.
# On-Premise 전제이므로 파일 권한 외 별도 보호 안함.
# ══════════════════════════════════════════════════════════════════
_SECRETS_FILE = Path(__file__).parent.parent / ".secrets.json"


def _load_or_create_secrets() -> dict:
    dict_loaded: dict = {}
    bool_existed = _SECRETS_FILE.exists()
    if bool_existed:
        try:
            with open(_SECRETS_FILE, "r", encoding="utf-8") as f:
                dict_loaded = json.load(f) or {}
        except Exception:
            dict_loaded = {}

    bool_changed = False
    if not dict_loaded.get("jwt_secret_key"):
        dict_loaded["jwt_secret_key"] = secrets.token_urlsafe(64)
        bool_changed = True
    if not dict_loaded.get("field_encryption_key"):
        dict_loaded["field_encryption_key"] = secrets.token_urlsafe(32)
        bool_changed = True
    # Pepper:
    # - 새 설치(.secrets.json 이 존재하지 않던 경우)는 무작위 pepper 를 생성한다.
    # - 이전 설치(파일은 있지만 pepper 키가 없는 경우)는 기존 유저 해시와의 호환을
    #   위해 legacy 하드코딩 값을 그대로 파일로 이관한다 — 소스에서는 지우고
    #   .secrets.json(0600) 으로만 존재하게 된다.
    # - 환경변수 AUTH_PEPPER 가 있으면 항상 우선.
    if not dict_loaded.get("pepper"):
        if bool_existed:
            dict_loaded["pepper"] = "MeDICus_2024_P3pp3r"  # legacy 호환
        else:
            dict_loaded["pepper"] = secrets.token_urlsafe(32)
        bool_changed = True

    if bool_changed:
        try:
            _SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_SECRETS_FILE, "w", encoding="utf-8") as f:
                json.dump(dict_loaded, f, indent=2)
            try:
                os.chmod(_SECRETS_FILE, 0o600)
            except Exception:
                pass
            print(f"[MeDICus SaaS] Persistent secrets written to {_SECRETS_FILE}")
        except Exception as e:
            print(f"[MeDICus SaaS] WARN — failed to persist secrets: {e}")

    return dict_loaded


_dict_persistent_secrets = _load_or_create_secrets()


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
    TILE_SIZE: int = 1024
    TILE_FORMAT: str = "JPEG"  # JPEG이 PNG보다 빠르고 작음
    TILE_QUALITY: int = 85

    # 타일 디스크 캐시 쿼터 (바이트, 기본 50 GB). 0 이하이면 janitor 비활성화.
    # janitor 는 주기적으로 TILES_DIR 총량을 검사하고, 쿼터를 초과하면 LRU
    # 기준으로 오래된 슬라이드 타일 디렉토리를 삭제 + DB 플래그 리셋한다.
    # 현재 slide_manager 에 열려 있는 (활성) 슬라이드는 보호된다.
    TILE_CACHE_QUOTA_BYTES: int = int(os.environ.get(
        "TILE_CACHE_QUOTA_BYTES",
        str(50 * 1024 * 1024 * 1024),
    ))

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
        _dict_persistent_secrets["jwt_secret_key"],
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── 보안 설정 ──
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 30
    SESSION_INACTIVE_MINUTES: int = 30

    # 업로드 크기 상한 (기본 20 GB — WSI 파일 고려). 환경변수 `MAX_UPLOAD_BYTES` 로 오버라이드.
    MAX_UPLOAD_BYTES: int = int(os.environ.get(
        "MAX_UPLOAD_BYTES",
        str(20 * 1024 * 1024 * 1024),
    ))

    # ── 민감 필드 암호화 키 (AES-256-GCM) ──
    FIELD_ENCRYPTION_KEY: str = os.environ.get(
        "FIELD_ENCRYPTION_KEY",
        _dict_persistent_secrets["field_encryption_key"],
    )

    # ── 비밀번호 해시용 pepper (bcrypt 입력에 사전 연결) ──
    # 과거엔 models.py 에 하드코딩 — 소스 노출 위험. 이제는 환경변수 또는
    # .secrets.json(0600) 에서 읽는다. 기존 배포에서는 legacy 값이 파일로
    # 이관되어 기존 해시와의 호환이 유지된다.
    AUTH_PEPPER: str = os.environ.get(
        "AUTH_PEPPER",
        _dict_persistent_secrets["pepper"],
    )


settings = Settings()
