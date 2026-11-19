"""Mocked tests for the OLS MCP api."""
import httpx

from servers.ols_mcp import api
from tests.helpers import HTTPTestCase

SEARCH = {"response": {"numFound": 42839, "docs": [
    {"iri": "http://purl.obolibrary.org/obo/MONDO_0007254", "label": "breast cancer",
     "description": ["A malignancy of the breast."], "obo_id": "MONDO:0007254",
     "ontology_name": "mondo", "ontology_prefix": "MONDO", "type": "class",
     "exact_synonyms": ["mammary cancer"]},
    {"iri": "http://www.ebi.ac.uk/efo/EFO_0000311", "label": "obsolete_cancer",
     "description": [], "obo_id": "EFO:0000311", "ontology_name": "efo",
     "ontology_prefix": "EFO", "type": "class"}]}}
ONTOS = {"_embedded": {"ontologies": [{"ontologyId": "efo", "title": "Experimental Factor Ontology",
                                       "config": {"preferredPrefix": "EFO", "description": "EFO",
                                                  "version": "v3.62.0"}}]},
         "page": {"totalElements": 190}}
TERM = {"_embedded": {"terms": [{"iri": "http://www.ebi.ac.uk/efo/EFO_0000311", "label": "obsolete_cancer",
                                 "description": ["Cancer."], "obo_id": "EFO:0000311",
                                 "is_obsolete": True, "has_children": False}]}}
ANCESTORS = {"_embedded": {"terms": [{"iri": "http://purl.obolibrary.org/obo/BFO_0000001", "label": "entity"}]}}


class OlsTests(HTTPTestCase):
    async def test_search_ontologies_term_and_hierarchy(self):
        seen = []

        def handler(req):
            seen.append((req.url.path, dict(req.url.params)))
            if req.url.path.endswith("/search"):
                self.assertEqual(req.url.params["q"], "cancer")
                self.assertEqual(req.url.params["ontology"], "mondo")
                self.assertEqual(req.url.params["size"], "1")
                self.assertEqual(req.url.params["start"], "0")
                return httpx.Response(200, json=SEARCH)
            if req.url.path == "/ols4/api/ontologies":
                return httpx.Response(200, json=ONTOS)
            if req.url.path == "/ols4/api/ontologies/efo/terms":
                self.assertEqual(req.url.params["iri"], "http://www.ebi.ac.uk/efo/EFO_0000311")
                return httpx.Response(200, json=TERM)
            if "/ancestors" in req.url.path:
                self.assertIn("%252F", req.url.raw_path.decode())
                return httpx.Response(200, json=ANCESTORS)
            if "/children" in req.url.path:
                return httpx.Response(200, json=ANCESTORS)
            raise AssertionError(f"unexpected path: {req.url.path}")

        with self.mock_http(handler):
            search = await api.ols_search("cancer", ontology="mondo", limit=1)
            self.assertEqual(search["hit_count"], 42839)
            self.assertEqual(search["results"][0]["prefix"], "MONDO")
            self.assertEqual(search["results"][0]["description"], "A malignancy of the breast.")
            ontologies = await api.ols_ontologies(limit=1)
            self.assertEqual(ontologies["results"][0]["prefix"], "EFO")
            self.assertEqual(ontologies["total"], 190)
            term = await api.ols_term("efo", "http://www.ebi.ac.uk/efo/EFO_0000311")
            self.assertTrue(term["is_obsolete"])
            ancestors = await api.ols_ancestors("efo", "http://www.ebi.ac.uk/efo/EFO_0000311")
            self.assertEqual(ancestors["results"][0]["label"], "entity")
            children = await api.ols_children("efo", "http://www.ebi.ac.uk/efo/EFO_0000311")
            self.assertEqual(children["total"], 1)
        self.assertEqual(len(seen), 5)

    async def test_missing_term_is_an_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"_embedded": {}})):
            with self.assertRaises(ValueError):
                await api.ols_term("efo", "http://www.ebi.ac.uk/efo/EFO_0000000")

    async def test_validation_before_network(self):
        cases = [(api.ols_search, {"query": ""}),
                 (api.ols_search, {"query": "cancer", "ontology": "EFO!"}),
                 (api.ols_search, {"query": "cancer", "limit": 0}),
                 (api.ols_ontologies, {"limit": 201}),
                 (api.ols_ontologies, {"page_index": -1}),
                 (api.ols_term, {"ontology": "efo", "iri": "EFO:0000311"}),
                 (api.ols_term, {"ontology": "e fo", "iri": "http://example.org/x"}),
                 (api.ols_ancestors, {"ontology": "efo", "iri": "ftp://example.org/x"}),
                 (api.ols_children, {"ontology": "efo", "iri": "http://example.org/x", "limit": 0})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.ols_ontologies()
