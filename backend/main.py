"""
MeDIAuto Studio SaaS — FastAPI Backend
WSI 타일 서빙 + AI 분석 API
"""

import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager


# ── 200 OK 로그 숨기기 (에러만 출력) ──
class _SuccessFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # 정상 응답(2xx, 3xx)은 숨기고 에러(4xx, 5xx)만 출력
        if "HTTP/1.1" in msg:
            for code in ("200", "204", "304"):
                if f'" {code}' in msg:
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import connect_db, disconnect_db
from app import cpu_layout  # CPU 파티셔닝 — import 시 executor 생성, startup 에서 affinity 적용
from app.routers import slides, tiles, ai, auth, users
from app import auto_ai
from app import tile_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 리소스 관리"""
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
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 설정 (개발 중에는 모든 origin 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


if FRONTEND_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "MeDIAuto Studio SaaS"}
