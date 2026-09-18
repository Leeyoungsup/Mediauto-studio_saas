"""text text"""

import json
import os
import secrets
from pathlib import Path


# ══════════════════════════════════════════════════════════════════
# text text
# ──
# text(JWT_SECRET_KEY / FIELD_ENCRYPTION_KEY) text text text text text.
# text `backend/.secrets.json` text text text/text — text text text
# text text text text text/text text text text.
# On-Premise text text text text text text text.
# ══════════════════════════════════════════════════════════════════
BACKEND_DIR = Path(__file__).resolve().parent.parent


def configured_path(name: str, default: Path) -> Path:
    """Resolve local overrides consistently, independently of the launch directory."""
    value = os.environ.get(name, "").strip()
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else BACKEND_DIR / path


_SECRETS_FILE = configured_path("MEDIAUTO_SECRETS_FILE", BACKEND_DIR / ".secrets.json")


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
    # - text text(.secrets.json text text text text)text text pepper text text.
    # - text text(text text pepper text text text)text text text text text
    #   text legacy text text text text text — text text
    #   .secrets.json(0600) text text text.
    # - text AUTH_PEPPER text text text text.
    if not dict_loaded.get("pepper"):
        if bool_existed:
            dict_loaded["pepper"] = "MeDICus_2024_P3pp3r"  # legacy text
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
            print(f"[MeDIAuto SaaS] Persistent secrets written to {_SECRETS_FILE}")
        except Exception as e:
            print(f"[MeDIAuto SaaS] WARN — failed to persist secrets: {e}")

    return dict_loaded


_dict_persistent_secrets = _load_or_create_secrets()


class Settings:
    CELL_ANNOTATION_DIR: str = str(configured_path("CELL_ANNOTATION_DIR", BACKEND_DIR / "cell_annotation"))
    SECRETS_FILE: str = str(_SECRETS_FILE)
    # Empty means use packaged OpenSlide/system discovery, then legacy DLL folders.
    OPENSLIDE_PATH: str = str(configured_path("OPENSLIDE_PATH", BACKEND_DIR)) if os.environ.get("OPENSLIDE_PATH", "").strip() else ""

    # text text (text text text — text WSI text)
    UPLOAD_DIR: str = str(configured_path("UPLOAD_DIR", BACKEND_DIR / "uploads"))

    # text text (text JPEG text text)
    TILES_DIR: str = str(configured_path("TILES_DIR", BACKEND_DIR / "tiles"))

    # AI text text text (uploadstext text)
    AI_RESULTS_DIR: str = str(configured_path("AI_RESULTS_DIR", BACKEND_DIR / "ai_results"))

    # text text
    ANNOTATIONS_DIR: str = str(configured_path("ANNOTATIONS_DIR", BACKEND_DIR / "annotations"))

    # Extracted source instances for DICOM WSI ZIP archives.
    DICOM_CACHE_DIR: str = str(configured_path("DICOM_CACHE_DIR", BACKEND_DIR / "dicom_cache"))
    DICOM_ZIP_MAX_FILES: int = int(os.environ.get("DICOM_ZIP_MAX_FILES", "10000"))
    DICOM_ZIP_MAX_UNCOMPRESSED_BYTES: int = int(os.environ.get(
        "DICOM_ZIP_MAX_UNCOMPRESSED_BYTES", str(100 * 1024 * 1024 * 1024)
    ))
    DICOM_FRAME_CACHE_SIZE: int = int(os.environ.get("DICOM_FRAME_CACHE_SIZE", "32"))
    DICOM_PYRAMID_TOLERANCE_MM: float = float(os.environ.get(
        "DICOM_PYRAMID_TOLERANCE_MM", "0.1"
    ))

    TILE_SIZE: int = 1024
    TILE_FORMAT: str = "JPEG"  # JPEGtext PNGtext text text
    TILE_QUALITY: int = 85

    # text text text text (text, text 1 TB). 0 text janitor text.
    # janitor text text TILES_DIR text text, text text LRU
    # text text text text text text + DB text text.
    # text slide_manager text text text (text) text text.
    TILE_CACHE_QUOTA_BYTES: int = int(os.environ.get(
        "TILE_CACHE_QUOTA_BYTES",
        str(1024 * 1024 * 1024 * 1024),
    ))

    # text text text
    CHUNK_SIZE: int = 5 * 1024 * 1024  # 5MB

    # Uploaded JPG/JPEG files are converted to pyramidal BigTIFF.  Keep a
    # finite source-dimension cap instead of disabling decompression-bomb
    # protection globally.  The default accepts images up to one gigapixel.
    JPEG_CONVERSION_MAX_PIXELS: int = int(os.environ.get(
        "JPEG_CONVERSION_MAX_PIXELS", "1000000000"
    ))
    JPEG_CONVERSION_QUALITY: int = int(os.environ.get(
        "JPEG_CONVERSION_QUALITY", "100"
    ))

    # AI model weights. Keep the local path as the workstation default while
    # allowing production deployments to mount models outside the Git tree.
    MODEL_DIR: str = str(configured_path("MODEL_DIR", BACKEND_DIR / "model"))

    # text text
    SUPPORTED_EXTENSIONS: set = {
        ".svs", ".ndpi", ".vms", ".vmu", ".scn",
        ".mrxs", ".tiff", ".tif", ".png", ".jpg", ".jpeg",
        ".isyntax", ".i2syntax", ".zip",
    }

    # PostgreSQL is the sole application datastore. A URL is deliberately
    # not hard-coded so production credentials never need to live in Git.
    POSTGRES_URI: str = os.environ.get("POSTGRES_URI", "").strip()
    POSTGRES_POOL_SIZE: int = int(os.environ.get("POSTGRES_POOL_SIZE", "10"))
    POSTGRES_MAX_OVERFLOW: int = int(os.environ.get("POSTGRES_MAX_OVERFLOW", "20"))
    POSTGRES_POOL_TIMEOUT: int = int(os.environ.get("POSTGRES_POOL_TIMEOUT", "30"))

    # ── JWT text ──
    JWT_SECRET_KEY: str = os.environ.get(
        "JWT_SECRET_KEY",
        _dict_persistent_secrets["jwt_secret_key"],
    )
    MEDIA_SIGNING_KEY: str = os.environ.get("MEDIA_SIGNING_KEY", "")
    JWT_ALGORITHM: str = "HS256"
    # text text text = main text text 15text/7text.
    # on-premise text text text text env text text: text) ACCESS_TOKEN_EXPIRE_MINUTES=360
    # Default access token lifetime is 6 hours for on-premise workstation use.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 360))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7))

    # ── text text ──
    MAX_LOGIN_ATTEMPTS: int = 5
    ACCOUNT_LOCK_MINUTES: int = 30
    SESSION_INACTIVE_MINUTES: int = 30

    # CORS text origin text (text text). text text same-origin text text.
    # text text: CORS_ORIGINS=http://localhost:3000,http://localhost:8000
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "")

    # text text text (text 20 GB — WSI text text). text `MAX_UPLOAD_BYTES` text text.
    MAX_UPLOAD_BYTES: int = int(os.environ.get(
        "MAX_UPLOAD_BYTES",
        str(20 * 1024 * 1024 * 1024),
    ))

    # ── text text text text (AES-256-GCM) ──
    FIELD_ENCRYPTION_KEY: str = os.environ.get(
        "FIELD_ENCRYPTION_KEY",
        _dict_persistent_secrets["field_encryption_key"],
    )

    # ── text text pepper (bcrypt text text text) ──
    # text models.py text text — text text text. text text text
    # .secrets.json(0600) text text. text text legacy text text
    # text text text text text.
    AUTH_PEPPER: str = os.environ.get(
        "AUTH_PEPPER",
        _dict_persistent_secrets["pepper"],
    )


settings = Settings()
