"""Tests for the json_response TTL cache."""
from __future__ import annotations

import unittest

import httpx

from common import api

from tests.helpers import HTTPTestCase


class JsonCacheTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        api._cache.clear()

    async def test_ttl_reuses_the_first_response_within_the_window(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.params.get("id"))
            return httpx.Response(200, json={"n": len(calls)})

        with self.mock_http(handler):
            first, meta1 = await api.json_response("https://example.org/x", {"id": "7"}, ttl=300)
            second, meta2 = await api.json_response("https://example.org/x", {"id": "7"}, ttl=300)
            different, _ = await api.json_response("https://example.org/x", {"id": "8"}, ttl=300)
        self.assertEqual(first, second)
        self.assertTrue(meta2.get("cached"))
        self.assertEqual(len(calls), 2)
        self.assertEqual(different["n"], 2)

    async def test_expired_entries_refetch(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json={"n": len(calls)})

        with self.mock_http(handler):
            await api.json_response("https://example.org/y", {"id": "1"}, ttl=300)
            # Simulate expiry without sleeping: rewind the stored timestamp.
            api._cache[next(iter(api._cache))] = (api._cache[next(iter(api._cache))][0] - 301,
                                                  api._cache[next(iter(api._cache))][1])
            refreshed, _ = await api.json_response("https://example.org/y", {"id": "1"}, ttl=300)
        self.assertEqual(refreshed["n"], 2)

    async def test_post_bodies_are_never_cached(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json={"n": len(calls)})

        with self.mock_http(handler):
            await api.json_response("https://example.org/z", body={"q": "1"}, ttl=300)
            await api.json_response("https://example.org/z", body={"q": "1"}, ttl=300)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
