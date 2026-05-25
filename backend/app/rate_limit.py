"""IP text Rate Limiting text (text ASGI — BaseHTTPMiddleware text text text)

text text(slowapi) text in-memory text text text text.
- text text: 10text/5text (text text)
- text API: 200text/text
- text/text: rate limit text (text text, text text text)

On-Premise text text text text text text.
"""

import json
import time


class _FixedWindowCounter:
    """text text text — O(1) text, text text.

    text text(text text O(n))text text.
    text text burst text text text.
    """

    __slots__ = ("int_window", "int_max", "_dict_buckets")

    def __init__(self, int_window_seconds: int, int_max_requests: int):
        self.int_window = int_window_seconds
        self.int_max = int_max_requests
        # {ip: (window_start, count)}
        self._dict_buckets: dict[str, tuple[float, int]] = {}

    def is_allowed(self, str_key: str) -> bool:
        float_now = time.monotonic()
        entry = self._dict_buckets.get(str_key)
        if entry is None or float_now - entry[0] >= self.int_window:
            # text text text
            self._dict_buckets[str_key] = (float_now, 1)
            return True
        if entry[1] >= self.int_max:
            return False
        self._dict_buckets[str_key] = (entry[0], entry[1] + 1)
        return True

    def cleanup(self):
        """text text text — text text text."""
        float_now = time.monotonic()
        float_cutoff = float_now - self.int_window * 2
        list_stale = [
            k for k, (t, _) in self._dict_buckets.items() if t < float_cutoff
        ]
        for k in list_stale:
            del self._dict_buckets[k]


# ── text text text ──
_LOGIN_LIMITER = _FixedWindowCounter(int_window_seconds=300, int_max_requests=10)
_API_LIMITER = _FixedWindowCounter(int_window_seconds=60, int_max_requests=200)

# text text text
_int_request_count = 0
_CLEANUP_INTERVAL = 5000


import os as _os

# X-Forwarded-For / X-Real-IP text text text text text text.
# text text text text text text rate_limit text text text text
# text text text. TRUSTED_PROXIES env text prox y peer IP text text text text.
_SET_RL_TRUSTED_PROXIES = {
    s.strip() for s in _os.environ.get("TRUSTED_PROXIES", "").split(",") if s.strip()
}


def _get_client_ip(headers: list[tuple[bytes, bytes]], scope: dict) -> str:
    """ASGI scope/headers text text IP text. TCP peer text TRUSTED_PROXIES
    text text text X-Forwarded-For / X-Real-IP text text."""
    str_peer = "unknown"
    client = scope.get("client")
    if client:
        str_peer = client[0]
    if _SET_RL_TRUSTED_PROXIES and str_peer in _SET_RL_TRUSTED_PROXIES:
        for k, v in headers:
            if k == b"x-forwarded-for":
                return v.decode().split(",")[0].strip()
            if k == b"x-real-ip":
                return v.decode().strip()
    return str_peer


def _send_429(retry_after: str):
    """429 text text text text."""
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
    """text ASGI text — IPtext text text.

    text/text/text text rate limit text:
    - text(media ticket)text text text
    - text text text text 0 text text
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        str_path = scope.get("path", "")

        # ── text text / text / text: rate limit text ──
        # text text(media ticket)text text. text text 0text.
        if not str_path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        if (str_path.startswith("/api/tiles/")
                or "/thumbnail" in str_path
                or "/virtual-stain/" in str_path):
            await self.app(scope, receive, send)
            return

        # ── text text text ──
        global _int_request_count
        _int_request_count += 1
        if _int_request_count % _CLEANUP_INTERVAL == 0:
            _LOGIN_LIMITER.cleanup()
            _API_LIMITER.cleanup()

        headers = scope.get("headers", [])
        str_ip = _get_client_ip(headers, scope)

        # text text — text text
        if str_path.rstrip("/") in ("/api/auth/login", "/api/auth/register"):
            if not _LOGIN_LIMITER.is_allowed(str_ip):
                await _send_429("300")(send)
                return
            await self.app(scope, receive, send)
            return

        # text API
        if not _API_LIMITER.is_allowed(str_ip):
            await _send_429("60")(send)
            return

        await self.app(scope, receive, send)
