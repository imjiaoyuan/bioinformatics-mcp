from unittest.mock import AsyncMock, patch

import httpx

from servers.pubchem_mcp import api
from tests.helpers import HTTPTestCase

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


class PubChemTests(HTTPTestCase):
    async def test_resolve_and_compound(self):
        def handler(req):
            if req.url.path.endswith("/compound/name/aspirin/cids/JSON"):
                return httpx.Response(200, json={"IdentifierList": {"CID": [2244]}})
            self.assertIn("/compound/cid/2244/property/", req.url.path)
            self.assertIn("MolecularFormula", str(req.url))
            return httpx.Response(200, json={"PropertyTable": {"Properties": [
                {"CID": 2244, "MolecularFormula": "C9H8O4", "XLogP": 1.2}]}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.pubchem_resolve("aspirin"))["cids"], [2244])
            compound = (await api.pubchem_compound("2244"))["compound"]
        self.assertEqual(compound["MolecularFormula"], "C9H8O4")

    async def test_synonyms_pagination(self):
        synonyms = [f"name-{i}" for i in range(5)]
        def handler(req):
            return httpx.Response(200, json={"InformationList": {"Information": [
                {"CID": 2244, "Synonym": synonyms}]}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.pubchem_synonyms("2244", limit=2, offset=2)
        self.assertEqual(result["results"], ["name-2", "name-3"])
        self.assertEqual(result["total"], 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["pagination"], "local")

    async def test_description_name_or_cid(self):
        paths = []
        payload = {"InformationList": {"Information": [{"CID": 2244, "Title": "Aspirin"}]}}
        def handler(req):
            paths.append(req.url.path)
            return httpx.Response(200, json=payload)
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.pubchem_description("aspirin"))["descriptions"], 1)
            self.assertEqual((await api.pubchem_description("2244"))["entries"][0]["Title"], "Aspirin")
        self.assertTrue(any(p.endswith("/compound/name/aspirin/description/JSON") for p in paths))
        self.assertTrue(any(p.endswith("/compound/cid/2244/description/JSON") for p in paths))

    async def test_substance_and_aid(self):
        def handler(req):
            if "/substance/sid/2244/JSON" in req.url.path:
                return httpx.Response(200, json={"PC_Substances": [{"sid": {"id": 2244}}]})
            self.assertIn("/assay/aid/10558/description/JSON", req.url.path)
            return httpx.Response(200, json={"PC_AssayContainer": [{"assay": {"descr": {"aid": {"id": 10558}}}}]})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.pubchem_substance("2244"))["substance"]["sid"]["id"], 2244)
            self.assertEqual((await api.pubchem_aid("10558"))["assay"][0]["assay"]["descr"]["aid"]["id"], 10558)

    async def test_annotation_sends_heading_and_extracts_text(self):
        def handler(req):
            self.assertEqual(req.url.params["heading"], "Pharmacology")
            return httpx.Response(200, json={"Record": {"RecordTitle": "Aspirin", "Section": [
                {"TOCHeading": "Pharmacology", "Information": [
                    {"Description": "pharmacodynamics", "Value": {"StringWithMarkup": [
                        {"String": "Aspirin inhibits..."}]}}]}]}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.pubchem_annotation("2244")
        self.assertEqual(result["record_title"], "Aspirin")
        self.assertEqual(result["sections"][0]["text"], "Aspirin inhibits...")

    async def test_validation_all_tools(self):
        for func, args in [(api.pubchem_resolve, {"name": "  "}),
                           (api.pubchem_compound, {"cid": "abc"}),
                           (api.pubchem_compound, {"cid": "22x4"}),
                           (api.pubchem_synonyms, {"cid": "2244", "limit": 0}),
                           (api.pubchem_description, {"name_or_cid": ""}),
                           (api.pubchem_substance, {"sid": "-3"}),
                           (api.pubchem_aid, {"aid": "1e5"}),
                           (api.pubchem_annotation, {"cid": "2244", "heading": "a" * 101})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_not_found_maps_to_value_error(self):
        def handler(req):
            return httpx.Response(404, json={"Fault": {"Code": "PUGREST.NotFound",
                                                       "Message": "No CID found"}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(ValueError, "no record found"):
                await api.pubchem_resolve("zzqqxxnope")

    async def test_pug_fault_body_maps_to_value_error(self):
        def handler(req):
            return httpx.Response(200, json={"Fault": {"Code": "PUGREST.BadRequest",
                                                       "Message": "Invalid ID",
                                                       "Details": ["must be positive integer"]}})
        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaisesRegex(ValueError, "PUGREST.BadRequest.*positive integer"):
                await api.pubchem_substance("999999999")
