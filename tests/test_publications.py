from unittest.mock import AsyncMock, patch

import httpx

from servers.publications_mcp import server
from tests.helpers import HTTPTestCase


class PublicationRelatedTests(HTTPTestCase):
    async def test_full_and_bare_work_ids_use_the_works_endpoint(self):
        paths = []
        def handler(req):
            paths.append(req.url.path)
            if "doi.org" in req.url.path:
                return httpx.Response(200, json={"related_works": ["https://openalex.org/W123", "W456"]})
            return httpx.Response(200, json={"id": "https://openalex.org/" + req.url.path.rsplit("/", 1)[-1],
                                            "title": "Related work", "publication_year": 2025})
        with self.mock_http(handler):
            result = await server.publication_related("10.1234/example")
        self.assertEqual(paths[1:], ["/works/W123", "/works/W456"])
        self.assertEqual(result["returned"], 2)
        self.assertFalse(result["partial"])

    async def test_partial_failure_is_reported_alongside_successes(self):
        def handler(req):
            if "doi.org" in req.url.path:
                return httpx.Response(200, json={"related_works": ["https://openalex.org/W123", "https://openalex.org/W456"]})
            return httpx.Response(404) if "W123" in req.url.path else httpx.Response(200, json={"title": "Available"})
        with self.mock_http(handler):
            result = await server.publication_related("10.1234/example")
        self.assertEqual(result["returned"], 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["errors"][0]["status_code"], 404)
        self.assertFalse(result["all_requests_failed"])

    async def test_all_failed_and_genuinely_empty_results_are_different(self):
        for ids in ([], ["https://openalex.org/W123"]):
            def handler(req):
                return (httpx.Response(200, json={"related_works": ids}) if "doi.org" in req.url.path
                        else httpx.Response(404))
            with self.mock_http(handler):
                result = await server.publication_related("10.1234/example")
            self.assertEqual(result["articles"], [])
            self.assertEqual(result["all_requests_failed"], bool(ids))
            self.assertEqual(result["partial"], bool(ids))

    async def test_bad_work_urls_do_not_trigger_offsite_requests(self):
        with patch.object(server, "_get", AsyncMock(return_value={"related_works": ["https://evil.invalid/W123"]})) as get:
            result = await server.publication_related("10.1234/example")
        self.assertEqual(get.await_count, 1)
        self.assertTrue(result["all_requests_failed"])

    async def test_limit_and_invalid_upstream_response(self):
        async def get(url, params=None):
            return {"related_works": ["W1", "W2", "W3"]} if "doi.org" in url else {"title": "One"}
        with patch.object(server, "_get", side_effect=get):
            result = await server.publication_related("10.1234/example", limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["returned"], 1)
        with patch.object(server, "_get", AsyncMock(return_value={"error": "not a valid work"})):
            with self.assertRaises(ValueError):
                await server.publication_related("10.1234/example")
