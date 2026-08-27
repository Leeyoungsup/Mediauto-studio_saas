"""IP text Rate Limiting text (text ASGI — BaseHTTPMiddleware text text text)

text text(slowapi) text in-memory text text text text.
- text text: 10text/5text (text text)
- text API: 200text/text
- text/text: rate limit text (text text, text text text)

On-Premise text text text text text text.
"""

import ipaddress
import json
import os as _os
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

    def is_blocked(self, str_key: str) -> bool:
        """Check the current window without increasing its count."""
        float_now = time.monotonic()
        entry = self._dict_buckets.get(str_key)
        if entry is None:
            return False
        if float_now - entry[0] >= self.int_window:
            self._dict_buckets.pop(str_key, None)
            return False
        return entry[1] >= self.int_max

    def record(self, str_key: str) -> bool:
        """Record an event and return whether the limit is now reached."""
        return not self.is_allowed(str_key)

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
_UPLOAD_LIMITER = _FixedWindowCounter(int_window_seconds=60, int_max_requests=2000)


def _env_positive_int(str_name: str, int_default: int) -> int:
    try:
        return max(1, int(_os.environ.get(str_name, str(int_default))))
    except (TypeError, ValueError):
        return max(1, int_default)

# text text text
_int_request_count = 0
_CLEANUP_INTERVAL = 5000


_NOT_FOUND_LIMITER = _FixedWindowCounter(
    int_window_seconds=_env_positive_int("MEDIAUTO_404_RATE_LIMIT_WINDOW_SECONDS", 60),
    int_max_requests=_env_positive_int("MEDIAUTO_404_RATE_LIMIT_MAX", 30),
)

# Immediate application-layer denylist. Entries may be individual IPs or CIDRs.
# The default blocks the Google Cloud source that performed the credential-file
# scan observed on 2026-08-27. Override/extend with a comma-separated env value.
_SET_BLOCKED_IP_ENTRIES = {
    value.strip()
    for value in (
        "207.175.151.181," + _os.environ.get("BLOCKED_IPS", "")
    ).split(",")
    if value.strip()
}
_LIST_BLOCKED_NETWORKS = []
for _str_entry in sorted(_SET_BLOCKED_IP_ENTRIES):
    try:
        _LIST_BLOCKED_NETWORKS.append(ipaddress.ip_network(_str_entry, strict=False))
    except ValueError:
        print(f"[rate_limit] ignoring invalid BLOCKED_IPS entry: {_str_entry}")

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


def _is_blocked_ip(str_ip: str) -> bool:
    try:
        obj_ip = ipaddress.ip_address(str_ip)
    except ValueError:
        return False
    if isinstance(obj_ip, ipaddress.IPv6Address) and obj_ip.ipv4_mapped:
        obj_ip = obj_ip.ipv4_mapped
    return any(obj_ip in obj_network for obj_network in _LIST_BLOCKED_NETWORKS)


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


def _send_403():
    body = json.dumps({"detail": "Request blocked."}).encode()

    async def _respond(send):
        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
                [b"cache-control", b"no-store"],
            ],
        })
        await send({"type": "http.response.body", "body": body})

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
        headers = scope.get("headers", [])
        str_ip = _get_client_ip(headers, scope)

        # Apply the explicit denylist before all route/media exemptions.
        if _is_blocked_ip(str_ip):
            await _send_403()(send)
            return

        global _int_request_count
        _int_request_count += 1
        if _int_request_count % _CLEANUP_INTERVAL == 0:
            _LOGIN_LIMITER.cleanup()
            _API_LIMITER.cleanup()
            _UPLOAD_LIMITER.cleanup()
            _NOT_FOUND_LIMITER.cleanup()

        # Public/static paths are not part of the normal API limiter. Count
        # their actual 404 responses instead, then throttle clients that scan
        # many nonexistent secret/config paths in a short window.
        if not str_path.startswith("/api/"):
            if _NOT_FOUND_LIMITER.is_blocked(str_ip):
                await _send_429(str(_NOT_FOUND_LIMITER.int_window))(send)
                return

            int_status = 0

            async def _capture_status(message):
                nonlocal int_status
                if message.get("type") == "http.response.start":
                    int_status = int(message.get("status", 0) or 0)
                await send(message)

            await self.app(scope, receive, _capture_status)
            if int_status == 404:
                _NOT_FOUND_LIMITER.record(str_ip)
            return

        if (str_path.startswith("/api/tiles/")
                or "/thumbnail" in str_path
                or "/virtual-stain/" in str_path
                or str_path in {
                    "/api/slides/dashboard",
                    "/api/slides/projects",
                    "/api/slides/folder-tree",
                }):
            await self.app(scope, receive, send)
            return

        # text text — text text
        if str_path.rstrip("/") in ("/api/auth/login", "/api/auth/register"):
            if not _LOGIN_LIMITER.is_allowed(str_ip):
                await _send_429("300")(send)
                return
            await self.app(scope, receive, send)
            return

        if str_path.startswith("/api/slides/upload/"):
            if not _UPLOAD_LIMITER.is_allowed(str_ip):
                await _send_429("60")(send)
                return
            await self.app(scope, receive, send)
            return

        # text API
        if not _API_LIMITER.is_allowed(str_ip):
            await _send_429("60")(send)
            return

        await self.app(scope, receive, send)
