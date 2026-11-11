from unittest.mock import AsyncMock, patch

import httpx

from common.http import request
from common.http import safe_url
from tests.helpers import HTTPTestCase


class TransportTests(HTTPTestCase):
    async def test_credentials_are_sent_but_not_returned_or_logged(self):
        def handler(req):
            self.assertEqual(req.url.params["api_key"], "TEST_SECRET")
            self.assertEqual(req.url.params["email"], "test@example.invalid")
            return httpx.Response(200, json={})
        with self.mock_http(handler), self.assertLogs("httpx", level="INFO") as logs:
            response = await request("GET", "https://example.org/search", params={"api_key": "TEST_SECRET",
                                     "email": "test@example.invalid", "term": "brain", "retstart": 20})
        for output in (str(response.url), " ".join(logs.output)):
            self.assertNotIn("TEST_SECRET", output)
            self.assertNotIn("test@example.invalid", output)
        self.assertEqual(response.url.params["term"], "brain")
        self.assertEqual(response.url.params["retstart"], "20")

    async def test_error_paths_hide_credentials(self):
        def handler(req):
            raise httpx.ConnectError("unable to connect to " + str(req.url), request=req)
        with self.mock_http(handler):
            with self.assertRaises(httpx.ConnectError) as caught:
                await request("GET", "https://example.org/?api_key=TEST_SECRET")
        self.assertNotIn("TEST_SECRET", str(caught.exception))
        self.assertNotIn("TEST_SECRET", str(caught.exception.request.url))
        with self.mock_http(lambda req: httpx.Response(401)):
            with self.assertRaises(httpx.HTTPStatusError) as caught:
                await request("GET", "https://example.org/?accesskey=TEST_SECRET")
        self.assertNotIn("TEST_SECRET", str(caught.exception))
        self.assertNotIn("TEST_SECRET", str(caught.exception.response.url))

    def test_redaction_handles_encoded_names_and_userinfo(self):
        self.assertEqual(safe_url("https://user:pass@example.org/?%61pi_key=secret&ACCESSKEY=secret&term=a%20b"),
                         "https://example.org/?term=a+b")

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

    async def test_idempotent_post_can_retry_service_failure(self):
        calls = []
        def handler(req):
            calls.append(req)
            return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            await request("POST", "https://example.org", json={}, retryable=True)
        self.assertEqual(len(calls), 2)

    async def test_response_size_bounded(self):
        with self.mock_http(lambda req: httpx.Response(200, content=b"x" * 10)):
            with self.assertRaisesRegex(ValueError, "too large"):
                await request("GET", "https://example.org", max_bytes=5)
