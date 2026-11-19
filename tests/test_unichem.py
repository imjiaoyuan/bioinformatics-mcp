"""Mocked tests for the UniChem MCP api."""
import httpx

from servers.unichem_mcp import api
from tests.helpers import HTTPTestCase

SOURCES = {"response": "Success", "sources": [
    {"srcId": 1, "name": "chembl", "nameLong": "ChEMBL", "UCICount": 2897819,
     "description": "Bioactive drug-like small molecules", "baseIdUrl": "https://chembl.example/"},
    {"srcId": 2, "name": "drugbank", "nameLong": "DrugBank", "UCICount": 12000,
     "description": "Drug data", "baseIdUrl": "https://drugbank.example/"}]}
COMPOUND = {"compounds": [{"uci": "102157809", "inchi": {"inchi": "InChI=1S/C16H13ClN2O",
                                                         "formula": "C16H13ClN2O"},
                           "sources": [{"srcId": 1, "srcCompoundId": "CHEMBL25"}]}]}
XREFS = [{"src_id": 2, "name": "drugbank", "name_long": "DrugBank", "src_compound_id": ["DB00829"]}]


class UniChemTests(HTTPTestCase):
    async def test_sources_source_resolve_and_cross_references(self):
        seen = []

        def handler(req):
            seen.append((req.method, req.url.path))
            if req.url.path.endswith("/api/v1/sources/") and req.method == "GET":
                return httpx.Response(200, json=SOURCES)
            if req.url.path.endswith("/api/v1/sources/1"):
                return httpx.Response(200, json={"response": "Success", "sources": [SOURCES["sources"][0]]})
            if req.url.path.endswith("/api/v1/compounds") and req.method == "POST":
                body = req.read().decode()
                self.assertIn('"type":"inchikey"', body.replace(" ", ""))
                self.assertIn("AAOVKJBEBIDNHE-UHFFFAOYSA-N", body)
                return httpx.Response(200, json=COMPOUND)
            if "/rest/verbose_inchikey/" in req.url.path:
                self.assertIn("AAOVKJBEBIDNHE-UHFFFAOYSA-N", req.url.path)
                return httpx.Response(200, json=XREFS)
            raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

        with self.mock_http(handler):
            sources = await api.unichem_sources(limit=1)
            self.assertEqual(sources["results"][0]["name"], "chembl")
            self.assertEqual(sources["total"], 2)
            self.assertTrue(sources["truncated"])
            detail = await api.unichem_source("1")
            self.assertEqual(detail["name_long"], "ChEMBL")
            resolved = await api.unichem_resolve("AAOVKJBEBIDNHE-UHFFFAOYSA-N", "inchikey")
            self.assertEqual(resolved["compounds"][0]["uci"], "102157809")
            xrefs = await api.unichem_cross_references("aaovkjbebidnhe-uhfffaoysa-n")
            self.assertEqual(xrefs["results"][0]["src_compound_ids"], ["DB00829"])
            self.assertEqual(xrefs["inchikey"], "AAOVKJBEBIDNHE-UHFFFAOYSA-N")
        self.assertEqual(seen[2][0], "POST")

    async def test_missing_lookups_are_errors(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"response": "Not found"})):
            with self.assertRaises(ValueError):
                await api.unichem_source("999")
        with self.mock_http(lambda req: httpx.Response(200, json={"compounds": []})):
            with self.assertRaises(ValueError):
                await api.unichem_resolve("unknown", "inchikey")
        with self.mock_http(lambda req: httpx.Response(200, json={"oops": True})):
            with self.assertRaises(ValueError):
                await api.unichem_cross_references("AAOVKJBEBIDNHE-UHFFFAOYSA-N")

    async def test_validation_before_network(self):
        cases = [(api.unichem_sources, {"limit": 0}),
                 (api.unichem_sources, {"offset": -1}),
                 (api.unichem_source, {"src_id": "chembl"}),
                 (api.unichem_resolve, {"compound": "", "type_": "inchikey"}),
                 (api.unichem_resolve, {"compound": "X", "type_": "sourceID"}),
                 (api.unichem_resolve, {"compound": "X", "type_": "inchikey", "source_id": "1"}),
                 (api.unichem_cross_references, {"inchikey": "AAOVKJBEBIDNHE"}),
                 (api.unichem_cross_references, {"inchikey": "AAOVKJBEBIDNHE-UHFFFAOYSA-NX"})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(500)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.unichem_sources()
