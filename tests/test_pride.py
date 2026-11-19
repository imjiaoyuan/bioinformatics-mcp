"""Mocked tests for the PRIDE MCP api."""
import httpx

from servers.pride_mcp import api
from tests.helpers import HTTPTestCase

SEARCH = [{"accession": "PXD086409", "title": "Phosphoproteomics landscape", "projectDescription": "x" * 400,
           "publicationDate": "2024-01-01", "keywords": ["phosphoproteomics"]},
          {"accession": "PXD008409", "title": "Other study", "projectDescription": "small",
           "publicationDate": "2017-06-12", "keywords": []}]
DETAIL = {"accession": "PXD001357", "title": "Ancient dental calculus", "projectDescription": "desc",
          "doi": "10.1234/pride", "publicationDate": "2020-05-01",
          "organisms": [{"name": "Homo sapiens", "taxId": "9606"}],
          "instruments": [{"name": "Q Exactive"}], "experimentTypes": [{"name": "proteomic profiling"}],
          "keywords": ["archaeology"], "labPIs": ["A. Researcher"], "countries": ["United Kingdom"],
          "license": {"uri": "https://creativecommons.org/licenses/by/4.0/", "label": "CC-BY 4.0"},
          "identifiedPTMStrings": ["Phospho"]}


class PrideTests(HTTPTestCase):
    async def test_search_and_project(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/search/projects"):
                self.assertEqual(req.url.params["keyword"], "phosphoproteomics")
                self.assertEqual(req.url.params["pageSize"], "1")
                self.assertEqual(req.url.params["page"], "2")
                return httpx.Response(200, json=[SEARCH[1]])
            if req.url.path.endswith("/projects/PXD001357"):
                return httpx.Response(200, json=DETAIL)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            search = await api.pride_search_projects("phosphoproteomics", limit=1, offset=1)
            self.assertEqual(search["results"][0]["accession"], "PXD008409")
            self.assertEqual(search["returned"], 1)
            self.assertEqual(search["results"][0]["description"], "small")
            project = await api.pride_project("pxd001357")
            self.assertEqual(project["doi"], "10.1234/pride")
            self.assertEqual(project["license"]["label"], "CC-BY 4.0")
        self.assertEqual(len(seen), 2)

    async def test_missing_project_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"error": "not found"})):
            with self.assertRaises(ValueError):
                await api.pride_project("PXD99999999")

    async def test_validation_before_network(self):
        cases = [(api.pride_search_projects, {"keyword": ""}),
                 (api.pride_search_projects, {"keyword": "x" * 201}),
                 (api.pride_search_projects, {"keyword": "p53", "limit": 0}),
                 (api.pride_search_projects, {"keyword": "p53", "offset": -1}),
                 (api.pride_project, {"accession": "bad"}),
                 (api.pride_project, {"accession": "PXD"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.pride_project("PXD001357")
