"""CSRF 방어 미들웨어 (순수 ASGI — BaseHTTPMiddleware 사용 안 함)

JWT 가 Authorization 헤더로만 전달되므로 브라우저의 자동 쿠키 전송 기반
CSRF 는 원천 차단되지만, defense-in-depth 로 상태 변경 요청(POST/PUT/
PATCH/DELETE)에 `X-Requested-With` 커스텀 헤더를 요구한다.

- 브라우저의 <form> submit 은 커스텀 헤더를 보낼 수 없음
- JS fetch/XHR 만 이 헤더를 설정할 수 있어 cross-origin form CSRF 차단
- 미디어 엔드포인트(GET)는 영향 없음
"""

import json

# CSRF 검사를 면제할 경로 (인증 전 or GET-only 엔드포인트)
_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/health",
})

_STATE_CHANGING_METHODS = frozenset({b"POST", b"PUT", b"PATCH", b"DELETE"})


class CSRFMiddleware:
    """순수 ASGI 미들웨어 — 상태 변경 요청에 X-Requested-With 헤더 필수."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").encode()
        if method in _STATE_CHANGING_METHODS:
            path = scope.get("path", "").rstrip("/")
            if path not in _EXEMPT_PATHS:
                # 헤더에서 x-requested-with 찾기
                headers = dict(scope.get("headers", []))
                if not headers.get(b"x-requested-with"):
                    body = json.dumps(
                        {"detail": "Missing X-Requested-With header (CSRF protection)"}
                    ).encode()
                    await send({
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            [b"content-type", b"application/json"],
                            [b"content-length", str(len(body)).encode()],
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                    })
                    return

        await self.app(scope, receive, send)
