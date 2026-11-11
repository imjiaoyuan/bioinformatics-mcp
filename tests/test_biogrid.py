from unittest.mock import AsyncMock, patch

import httpx

from servers.biogrid_mcp import api
from tests.helpers import HTTPTestCase


class BioGRIDTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        self.env = patch.dict("os.environ", {"BIOGRID_API_KEY": "0" * 32})

    async def test_interactions_and_single_record(self):
        def handler(req):
            self.assertEqual(req.url.params["accesskey"], "0" * 32)
            if req.url.path.endswith("/interactions/"):
                self.assertEqual(req.url.params["geneList"], "MDM2|TP53")
                self.assertEqual(req.url.params["searchNames"], "true")
                self.assertEqual(req.url.params["taxId"], "9606")
                self.assertEqual(req.url.params["max"], "5")
                self.assertEqual(req.url.params["start"], "10")
                return httpx.Response(200, json={
                    "123": {"OFFICIAL_SYMBOL_A": "MDM2", "OFFICIAL_SYMBOL_B": "TP53",
                            "EXPERIMENTAL_SYSTEM": "Affinity Capture-MS",
                            "THROUGHPUT": "Low throughput", "PUBMED_ID": 18316726}})
            self.assertIn("/interaction/123", req.url.path)
            return httpx.Response(200, json={
                "123": {"OFFICIAL_SYMBOL_A": "MDM2", "OFFICIAL_SYMBOL_B": "TP53"}})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.biogrid_interactions(genes=["MDM2", "TP53"], tax_id="9606",
                                                       limit=5, start=10)
            self.assertIn("source_url", result)
            self.assertEqual(result["123"]["EXPERIMENTAL_SYSTEM"], "Affinity Capture-MS")
            self.assertEqual(result["123"]["THROUGHPUT"], "Low throughput")
            single = await api.biogrid_interaction("123")
            self.assertEqual(single["123"]["OFFICIAL_SYMBOL_B"], "TP53")

    async def test_reference_lists_and_version(self):
        def handler(req):
            path = req.url.path
            if path.endswith("/evidence/"):
                return httpx.Response(200, json={"EXPERIMENTAL_SYSTEMS": [
                    {"EXPERIMENTAL_SYSTEM": "Two-hybrid", "CODE": "Y2H"}]})
            if path.endswith("/organisms/"):
                return httpx.Response(200, json={"9606": "Homo sapiens", "559292": "Saccharomyces cerevisiae"})
            if path.endswith("/identifiers/"):
                return httpx.Response(200, json={"UNIPROT": "UniProtKB", "REFSEQ": "RefSeq"})
            return httpx.Response(200, json={"version": "4.4.201"})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await api.biogrid_evidence())["EXPERIMENTAL_SYSTEMS"][0]["CODE"], "Y2H")
            organisms = await api.biogrid_organisms()
            self.assertEqual(organisms["9606"], "Homo sapiens")
            self.assertEqual((await api.biogrid_identifiers())["REFSEQ"], "RefSeq")
            self.assertIn("version", await api.biogrid_version())

    async def test_pubmed_and_evidence_filters(self):
        def handler(req):
            params = req.url.params
            self.assertEqual(params["pubmedList"], "18316726|17662948")
            self.assertEqual(params["evidenceList"], "Two-hybrid|Affinity Capture-MS")
            self.assertEqual(params["includeEvidence"], "true")
            self.assertEqual(params["throughputTag"], "low")
            return httpx.Response(200, json={})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            await api.biogrid_interactions(
                pubmed_list=["18316726", "17662948"], evidence_list=["Two-hybrid", "Affinity Capture-MS"],
                throughput="low")

    async def test_validation_all_tools(self):
        missing_key_cases = [
            (api.biogrid_interactions, {"genes": ["MDM2"]}),
            (api.biogrid_interaction, {"interaction_id": "123"}),
            (api.biogrid_evidence, {}),
            (api.biogrid_organisms, {}),
            (api.biogrid_identifiers, {}),
            (api.biogrid_version, {}),
        ]
        with patch.dict("os.environ", {}, clear=True):
            for func, args in missing_key_cases:
                with self.subTest(tool=func.__name__, error="missing key"), self.assertRaises(ValueError):
                    await func(**args)
        with self.env:
            cases = [(api.biogrid_interactions, {}),
                     (api.biogrid_interactions, {"genes": ["MDM2"], "limit": 0}),
                     (api.biogrid_interactions, {"genes": ["MDM2"], "throughput": "bad"}),
                     (api.biogrid_interactions, {"genes": []}),
                     (api.biogrid_interaction, {"interaction_id": "abc"})]
            for func, args in cases:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**args)

    async def test_api_error(self):
        with self.env, self.mock_http(lambda req: httpx.Response(404)):
            with patch("common.http.asyncio.sleep", new_callable=AsyncMock), \
                    self.assertRaises(httpx.HTTPStatusError):
                await api.biogrid_interaction("999999999999")
