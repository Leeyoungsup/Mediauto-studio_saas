"""
MeDIAuto Studio SaaS — FastAPI Backend
WSI text text + AI text API
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager


# ── text text text text ──
# 401 text text text "text/text text → text → text" text text text text.
# text text text(text text) text router text audit_logs (user.login_failed,
# security.token_reuse_detected text) text text text access log text text
# text text text. text text text LOG_AUTH_401=1 text text text text text.
_BOOL_LOG_AUTH_401 = os.environ.get("LOG_AUTH_401", "").lower() in ("1", "true", "yes")

# text text text·access text text text text 401 — text text text text
# text access log text text text text text.
_TUPLE_AUTH_401_SILENT_PATHS = (
    "/api/auth/refresh",
    "/api/auth/media-ticket",
    "/api/ai/active-tasks",
    "/api/slides/thumbnail",        # /thumbnail-by-name + /{slide_id}/thumbnail text text
    "/api/slides/preview",
    "/thumbnail",
    "/preview",
    "/api/tiles/",                  # text·NDP text text text
    "/api/ai/virtual-stain/",       # VS text PNG·text text
)


class _SuccessFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "HTTP/1.1" not in msg:
            return True
        # text text(2xx, 3xx)text text
        for code in ("200", "204", "304"):
            if f'" {code}' in msg:
                return False
        # text/text text text 401 text text text — text (LOG_AUTH_401=1 text text text)
        if not _BOOL_LOG_AUTH_401 and '" 401' in msg:
            for str_path in _TUPLE_AUTH_401_SILENT_PATHS:
                if str_path in msg:
                    return False
        return True


logging.getLogger("uvicorn.access").addFilter(_SuccessFilter())

# ── OpenSlide DLL text text (import text text text) ──
PROJECT_ROOT = Path(__file__).parent.parent.parent
_dll_paths = [
    PROJECT_ROOT / "libs" / "openslide_lib" / "bin",
    PROJECT_ROOT / "libs",
]
for _dp in _dll_paths:
    if _dp.exists():
        os.environ['OPENSLIDE_PATH'] = str(_dp)
        break
_path_additions = [
    str(p) for p in _dll_paths
    if p.exists() and str(p) not in os.environ.get('PATH', '')
]
if _path_additions:
    os.environ['PATH'] = os.pathsep.join(_path_additions) + os.pathsep + os.environ.get('PATH', '')
for _dp in _dll_paths:
    if _dp.exists():
        try:
            os.add_dll_directory(str(_dp))
        except (AttributeError, OSError):
            pass

# AI text text text (text ai/ text text)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.csrf import CSRFMiddleware
from app.rate_limit import RateLimitMiddleware
from app.database import initialize_main_loop
from app.postgres.database import connect_postgres, disconnect_postgres
from app import cpu_layout  # CPU text — import text executor text, startup text affinity text
from app.routers import slides, slide_media, annotation_storage, cell_annotation, projects, file_operations, tiles, ai, auth, users, admin_settings
from app import auto_ai
from app import slide_store
from app import tile_worker
from app.runtime_settings import load_worker_settings
from app.version import APP_VERSION, get_version_info


def _install_asyncio_noise_filter():
    """Suppress benign Windows socket reset callbacks without hiding real errors."""
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def _handle_exception(loop, context):
        exc = context.get("exception")
        if isinstance(exc, ConnectionResetError) and getattr(exc, "winerror", None) == 10054:
            return
        if previous_handler:
            previous_handler(loop, context)
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_handle_exception)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """text text/text text text text"""
    _install_asyncio_noise_filter()

    # CPU text text — text text affinity text AI cores text text.
    # viewer / bg pool text text initializer text text cores text override.
    cpu_layout.setup_process_affinity()

    initialize_main_loop()
    await connect_postgres()
    print("[MeDIAuto SaaS] PostgreSQL repositories connected")
    int_repaired_slide_keys = await slide_store.repair_slide_cache_keys()
    if int_repaired_slide_keys:
        print(f"[slide_store] repaired/removed {int_repaired_slide_keys} legacy slide cache record(s)")

    # text text
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.TILES_DIR, exist_ok=True)
    print(f"[MeDIAuto SaaS] Upload dir: {settings.UPLOAD_DIR}")
    print(f"[MeDIAuto SaaS] Tiles dir:  {settings.TILES_DIR}")
    print(f"[MeDIAuto SaaS] Server ready")

    dict_worker_settings = await load_worker_settings()
    if dict_worker_settings.get("bool_tile_worker_enabled", True):
        await tile_worker.start_tile_worker()
    else:
        print("[tile_worker] disabled by admin settings")
    if dict_worker_settings.get("bool_ai_worker_enabled", True):
        await auto_ai.start_auto_worker()
    else:
        print("[auto_ai] worker disabled by admin settings")

    yield
    # text text text text
    await auto_ai.stop_auto_worker()
    await tile_worker.stop_tile_worker()
    # text text text text text
    from app.slide_manager import slide_manager
    from app.philips_proxy import shutdown_persistent_bridges
    slide_manager.close_all()
    shutdown_persistent_bridges()
    cpu_layout.shutdown_executors()
    await disconnect_postgres()
    print("[MeDIAuto SaaS] Shutdown complete")


app = FastAPI(
    title="MeDIAuto Studio SaaS",
    description="text AI text SaaS API",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS text — text CORS_ORIGINS text text origin text
# text text same-origin text (StaticFiles text CORS text)
_cors_origins = [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
] if settings.CORS_ORIGINS else []
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# CSRF text — text text text X-Requested-With text text
# Rate Limiting — IPtext text text (text: 10text/5text, API: 200text/text)
# text ASGI text — BaseHTTPMiddleware text body text text text
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)

# text text
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(admin_settings.router, prefix="/api/admin", tags=["admin-settings"])
app.include_router(projects.router, prefix="/api/slides", tags=["slide-projects"])
app.include_router(file_operations.router, prefix="/api/slides", tags=["slide-files"])
app.include_router(slides.router, prefix="/api/slides", tags=["slides"])
app.include_router(slide_media.router, prefix="/api/slides", tags=["slides-media"])
app.include_router(annotation_storage.router, prefix="/api/slides", tags=["slide-annotations"])
app.include_router(cell_annotation.router, prefix="/api/cell-annotation", tags=["cell-annotation"])
app.include_router(tiles.router, prefix="/api/tiles", tags=["tiles"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(ai.media_router, prefix="/api/ai", tags=["ai-media"])

# text text text text
# text: .js/.html/.css text Cache-Control: no-cache text text text.
# ETag/Last-Modified text 304 text text text text text text text text.
# text text text text text JS text text text api text text text
# text "text text text text text" text text.
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        str_lower = path.lower()
        if str_lower.endswith((".js", ".mjs", ".html", ".css")):
            # All deployed JS/CSS imports carry an explicit version query
            # parameter (for example ``app.js?v=...``).  Those immutable
            # assets do not need a conditional request on every page change;
            # revalidating them through the public domain added ~200–300 ms
            # per asset before the browser could execute the page.
            query = scope.get("query_string", b"")
            bool_versioned_asset = b"v=" in query
            if bool_versioned_asset and not str_lower.endswith(".html"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "MeDIAuto Studio SaaS", "version": APP_VERSION}


@app.get("/api/version")
async def version_check():
    return get_version_info()


@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools_probe():
    return Response(status_code=204)


_DICT_PAGE_ROUTES = {
    "home": "home.html",
    "project": "project.html",
    "data-linkage": "data-linkage.html",
    "ai": "app.html",
    "annotation": "annotation.html",
    "tissue-annotation": "annotation.html",
    "cell-annotation": "cell-annotation.html",
    "admin": "admin.html",
    "login": "login.html",
    "profile": "profile.html",
    "upload": "upload.html",
}


def _frontend_page_response(str_page: str) -> FileResponse:
    return FileResponse(
        FRONTEND_DIR / _DICT_PAGE_ROUTES[str_page],
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


for _clean_path, _html_file in _DICT_PAGE_ROUTES.items():
    async def _serve_frontend_page(str_page: str = _clean_path):
        return _frontend_page_response(str_page)

    async def _redirect_legacy_page(request: Request, str_page: str = _clean_path):
        str_query = request.url.query
        str_url = f"/{str_page}" + (f"?{str_query}" if str_query else "")
        return RedirectResponse(url=str_url, status_code=308)

    app.get(f"/{_clean_path}", include_in_schema=False)(_serve_frontend_page)
    app.get(f"/{_html_file}", include_in_schema=False)(_redirect_legacy_page)


if FRONTEND_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
