"""CSRF text text (text ASGI — BaseHTTPMiddleware text text text)

JWT text Authorization text text text text text text text
CSRF text text text, defense-in-depth text text text text(POST/PUT/
PATCH/DELETE)text `X-Requested-With` text text text.

- text <form> submit text text text text text text
- JS fetch/XHR text text text text text text cross-origin form CSRF text
- text text(GET)text text text
"""

import json

# CSRF text text text (text text or GET-only text)
_EXEMPT_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/health",
})

_STATE_CHANGING_METHODS = frozenset({b"POST", b"PUT", b"PATCH", b"DELETE"})


class CSRFMiddleware:
    """text ASGI text — text text text X-Requested-With text text."""

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
                # text x-requested-with text
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
