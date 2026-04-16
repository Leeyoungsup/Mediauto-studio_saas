"""CSRF 방어 미들웨어

JWT 가 Authorization 헤더로만 전달되므로 브라우저의 자동 쿠키 전송 기반
CSRF 는 원천 차단되지만, defense-in-depth 로 상태 변경 요청(POST/PUT/
PATCH/DELETE)에 `X-Requested-With` 커스텀 헤더를 요구한다.

- 브라우저의 <form> submit 은 커스텀 헤더를 보낼 수 없음
- JS fetch/XHR 만 이 헤더를 설정할 수 있어 cross-origin form CSRF 차단
- 미디어 엔드포인트(GET)는 영향 없음
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# CSRF 검사를 면제할 경로 (인증 전 or GET-only 엔드포인트)
_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/health",
})

_STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """상태 변경 요청에 X-Requested-With 헤더 필수."""

    async def dispatch(self, request: Request, call_next):
        if request.method in _STATE_CHANGING_METHODS:
            str_path = request.url.path.rstrip("/")
            if str_path not in _EXEMPT_PATHS:
                str_xrw = request.headers.get("X-Requested-With", "")
                if not str_xrw:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Missing X-Requested-With header (CSRF protection)"},
                    )
        return await call_next(request)
