"""IP 기반 Rate Limiting 미들웨어 (순수 ASGI — BaseHTTPMiddleware 사용 안 함)

외부 라이브러리(slowapi) 없이 in-memory 슬라이딩 윈도우로 구현.
- 로그인 엔드포인트: 10회/5분 (브루트포스 방지)
- 일반 API: 200회/분
- 타일/미디어: 2000회/분 (뷰어 렌더링 고려)

On-Premise 단일 프로세스 전제이므로 메모리 기반으로 충분.
"""

import json
import time
from collections import defaultdict


class _SlidingWindow:
    """슬라이딩 윈도우 카운터."""

    def __init__(self, int_window_seconds: int, int_max_requests: int):
        self.int_window = int_window_seconds
        self.int_max = int_max_requests
        self._dict_buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, str_key: str) -> bool:
        float_now = time.monotonic()
        float_cutoff = float_now - self.int_window
        list_ts = self._dict_buckets[str_key]
        # 오래된 항목 제거
        list_ts[:] = [t for t in list_ts if t > float_cutoff]
        if len(list_ts) >= self.int_max:
            return False
        list_ts.append(float_now)
        return True

    def cleanup(self):
        """주기적 메모리 정리."""
        float_now = time.monotonic()
        list_stale = [
            k for k, v in self._dict_buckets.items()
            if not v or v[-1] < float_now - self.int_window * 2
        ]
        for k in list_stale:
            del self._dict_buckets[k]


# ── 경로별 윈도우 설정 ──
_LOGIN_LIMITER = _SlidingWindow(int_window_seconds=300, int_max_requests=10)
_API_LIMITER = _SlidingWindow(int_window_seconds=60, int_max_requests=200)
_MEDIA_LIMITER = _SlidingWindow(int_window_seconds=60, int_max_requests=2000)

# 주기적 정리 카운터
_int_request_count = 0
_CLEANUP_INTERVAL = 1000


def _get_client_ip(headers: list[tuple[bytes, bytes]], scope: dict) -> str:
    """ASGI scope/headers에서 클라이언트 IP 추출."""
    for k, v in headers:
        if k == b"x-forwarded-for":
            return v.decode().split(",")[0].strip()
        if k == b"x-real-ip":
            return v.decode().strip()
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


def _send_429(retry_after: str):
    """429 응답을 보내는 코루틴 팩토리."""
    body = json.dumps(
        {"detail": "Too many requests. Please try again later."}
    ).encode()

    async def _respond(send):
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"retry-after", retry_after.encode()],
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    return _respond


class RateLimitMiddleware:
    """순수 ASGI 미들웨어 — IP별 요청 제한."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        global _int_request_count
        _int_request_count += 1
        if _int_request_count % _CLEANUP_INTERVAL == 0:
            _LOGIN_LIMITER.cleanup()
            _API_LIMITER.cleanup()
            _MEDIA_LIMITER.cleanup()

        str_path = scope.get("path", "")
        headers = scope.get("headers", [])
        str_ip = _get_client_ip(headers, scope)

        # 로그인 엔드포인트 — 엄격한 제한
        if str_path.rstrip("/") in ("/api/auth/login", "/api/auth/register"):
            if not _LOGIN_LIMITER.is_allowed(str_ip):
                await _send_429("300")(send)
                return
            await self.app(scope, receive, send)
            return

        # 타일/미디어 — 뷰어 렌더링용 높은 제한
        if str_path.startswith("/api/tiles/") or "/thumbnail" in str_path:
            if not _MEDIA_LIMITER.is_allowed(str_ip):
                await _send_429("60")(send)
                return
            await self.app(scope, receive, send)
            return

        # 일반 API
        if str_path.startswith("/api/"):
            if not _API_LIMITER.is_allowed(str_ip):
                await _send_429("60")(send)
                return

        await self.app(scope, receive, send)
