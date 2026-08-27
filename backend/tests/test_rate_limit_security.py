import asyncio
import unittest

from app.rate_limit import RateLimitMiddleware, _NOT_FOUND_LIMITER


async def _request(middleware, path: str, client_ip: str) -> int:
    list_messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        list_messages.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "client": (client_ip, 12345),
    }
    await middleware(scope, receive, send)
    starts = [item for item in list_messages if item.get("type") == "http.response.start"]
    return int(starts[0]["status"])


class RateLimitSecurityTests(unittest.TestCase):
    def test_explicit_scanner_ip_is_blocked_before_application(self):
        dict_calls = {"count": 0}

        async def app(_scope, _receive, send):
            dict_calls["count"] += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        status = asyncio.run(
            _request(RateLimitMiddleware(app), "/", "207.175.151.181")
        )
        self.assertEqual(status, 403)
        self.assertEqual(dict_calls["count"], 0)

        mapped_status = asyncio.run(
            _request(RateLimitMiddleware(app), "/", "::ffff:207.175.151.181")
        )
        self.assertEqual(mapped_status, 403)
        self.assertEqual(dict_calls["count"], 0)

    def test_repeated_public_404_requests_are_throttled(self):
        str_ip = "198.51.100.77"
        _NOT_FOUND_LIMITER._dict_buckets.pop(str_ip, None)

        async def app(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b"missing"})

        middleware = RateLimitMiddleware(app)
        try:
            for int_index in range(_NOT_FOUND_LIMITER.int_max):
                status = asyncio.run(
                    _request(middleware, f"/missing-{int_index}", str_ip)
                )
                self.assertEqual(status, 404)
            status = asyncio.run(_request(middleware, "/still-scanning", str_ip))
            self.assertEqual(status, 429)
        finally:
            _NOT_FOUND_LIMITER._dict_buckets.pop(str_ip, None)

    def test_successful_static_requests_do_not_consume_404_limit(self):
        str_ip = "198.51.100.78"
        _NOT_FOUND_LIMITER._dict_buckets.pop(str_ip, None)

        async def app(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = RateLimitMiddleware(app)
        try:
            for _ in range(_NOT_FOUND_LIMITER.int_max + 5):
                status = asyncio.run(_request(middleware, "/app.js", str_ip))
                self.assertEqual(status, 200)
            self.assertNotIn(str_ip, _NOT_FOUND_LIMITER._dict_buckets)
        finally:
            _NOT_FOUND_LIMITER._dict_buckets.pop(str_ip, None)


if __name__ == "__main__":
    unittest.main()
