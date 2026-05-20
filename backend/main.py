"""
MeDIAuto Studio SaaS — FastAPI Backend
WSI 타일 서빙 + AI 분석 API
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager


# ── 불필요한 액세스 로그 숨기기 ──
# 401 은 거의 다 "토큰/티켓 만료 → 재발급 → 재시도" 정상 흐름이라 디폴트로 숨긴다.
# 진짜 인증 실패(잘못된 자격증명) 는 router 안에서 audit_logs (user.login_failed,
# security.token_reuse_detected 등) 로 별도 기록되므로 access log 에서 빠져도
# 추적성에 영향 없음. 필요 시 환경변수 LOG_AUTH_401=1 로 다시 켤 수 있다.
_BOOL_LOG_AUTH_401 = os.environ.get("LOG_AUTH_401", "").lower() in ("1", "true", "yes")

# 만료된 미디어 티켓·access 토큰으로 들어오는 정상 흐름 401 — 한 화면당 수십 건씩
# 찍혀 access log 를 도배하므로 화이트리스트로 일괄 침묵.
_TUPLE_AUTH_401_SILENT_PATHS = (
    "/api/auth/refresh",
    "/api/auth/media-ticket",
    "/api/ai/active-tasks",
    "/api/slides/thumbnail",        # /thumbnail-by-name + /{slide_id}/thumbnail 모두 매칭
    "/api/slides/preview",
    "/thumbnail",
    "/preview",
    "/api/tiles/",                  # 타일·NDP 변형 타일 전체
    "/api/ai/virtual-stain/",       # VS 결과 PNG·피라미드 타일
)


class _SuccessFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "HTTP/1.1" not in msg:
            return True
        # 정상 응답(2xx, 3xx)은 숨김
        for code in ("200", "204", "304"):
            if f'" {code}' in msg:
                return False
        # 토큰/티켓 만료 흐름의 401 은 정상 동작 — 숨김 (LOG_AUTH_401=1 로 강제 표시)
        if not _BOOL_LOG_AUTH_401 and '" 401' in msg:
            for str_path in _TUPLE_AUTH_401_SILENT_PATHS:
                if str_path in msg:
                    return False
        return True


logging.getLogger("uvicorn.access").addFilter(_SuccessFilter())

# ── OpenSlide DLL 경로 설정 (import 전에 실행해야 함) ──
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

# AI 모듈 경로 추가 (기존 ai/ 코드 재사용)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.csrf import CSRFMiddleware
from app.rate_limit import RateLimitMiddleware
from app.database import connect_db, disconnect_db
from app import cpu_layout  # CPU 파티셔닝 — import 시 executor 생성, startup 에서 affinity 적용
from app.routers import slides, tiles, ai, auth, users
from app import auto_ai
from app import tile_worker
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
    """앱 시작/종료 시 리소스 관리"""
    _install_asyncio_noise_filter()

    # CPU 파티셔닝 적용 — 메인 프로세스 affinity 를 AI cores 로 설정.
    # viewer / bg pool 은 자체 initializer 로 자기 cores 를 override.
    cpu_layout.setup_process_affinity()

    # MongoDB 연결
    await connect_db()

    # 디렉토리 생성
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.TILES_DIR, exist_ok=True)
    print(f"[MeDIAuto SaaS] Upload dir: {settings.UPLOAD_DIR}")
    print(f"[MeDIAuto SaaS] Tiles dir:  {settings.TILES_DIR}")
    print(f"[MeDIAuto SaaS] Server ready")

    # 뷰어 타일 생성 워커 시작 (사용자 활동 무관, 최우선 백그라운드)
    await tile_worker.start_tile_worker()
    # AI 자동 추론 워커 시작 (1분 스캔, 10분 idle)
    await auto_ai.start_auto_worker()

    yield
    # 종료 시 워커 중단
    await auto_ai.stop_auto_worker()
    await tile_worker.stop_tile_worker()
    # 종료 시 열린 슬라이드 정리
    from app.slide_manager import slide_manager
    slide_manager.close_all()
    # MongoDB 연결 해제
    await disconnect_db()
    print("[MeDIAuto SaaS] Shutdown complete")


app = FastAPI(
    title="MeDIAuto Studio SaaS",
    description="병리 AI 분석 SaaS API",
    version=APP_VERSION,
    lifespan=lifespan,
)

# CORS 설정 — 환경변수 CORS_ORIGINS 로 허용 origin 지정
# 비어 있으면 same-origin 전용 (StaticFiles 서빙이므로 CORS 불필요)
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

# CSRF 방어 — 상태 변경 요청에 X-Requested-With 헤더 필수
# Rate Limiting — IP별 요청 제한 (로그인: 10회/5분, API: 200회/분)
# 순수 ASGI 미들웨어 — BaseHTTPMiddleware 의 body 버퍼링 오버헤드 제거
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)

# 라우터 등록
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(slides.router, prefix="/api/slides", tags=["slides"])
app.include_router(slides.media_router, prefix="/api/slides", tags=["slides-media"])
app.include_router(tiles.router, prefix="/api/tiles", tags=["tiles"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(ai.media_router, prefix="/api/ai", tags=["ai-media"])

# 프론트엔드 정적 파일 서빙
# 주의: .js/.html/.css 는 Cache-Control: no-cache 로 강제 재검증.
# ETag/Last-Modified 기반 304 는 유지되므로 실제 바이트 재전송은 파일이 바뀐 경우에만.
# 이 설정이 없으면 브라우저가 오래된 JS 를 붙잡고 있어 api 계약이 바뀐 뒤에도
# 사용자가 "하드 리프레시 해도 안 먹는" 상황이 발생한다.
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        str_lower = path.lower()
        if str_lower.endswith((".js", ".mjs", ".html", ".css")):
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
    return FileResponse(FRONTEND_DIR / _DICT_PAGE_ROUTES[str_page])


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
