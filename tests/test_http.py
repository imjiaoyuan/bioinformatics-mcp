from unittest.mock import AsyncMock, patch

import httpx

from common.http import request
from tests.helpers import HTTPTestCase


class TransportTests(HTTPTestCase):
    async def test_retry_after_rate_limit(self):
        count = 0
        def handler(req):
            nonlocal count
            count += 1
            return httpx.Response(429, headers={"Retry-After": "invalid"}) if count == 1 else httpx.Response(200, json={"ok": True})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertTrue((await request("GET", "https://example.org" )).json()["ok"])
        self.assertEqual(count, 2)

    async def test_post_not_retried(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            with self.assertRaises(httpx.HTTPStatusError):
                await request("POST", "https://example.org", json={})

    async def test_response_size_bounded(self):
        with self.mock_http(lambda req: httpx.Response(200, content=b"x" * 10)):
            with self.assertRaisesRegex(ValueError, "too large"):
                await request("GET", "https://example.org", max_bytes=5)
