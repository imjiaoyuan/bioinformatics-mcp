"""Deterministic regression checks for provider request/response handling."""
import unittest
from unittest.mock import patch

import httpx

from servers.anaconda_mcp import server as anaconda
from servers.bioconductor_mcp import server as bioconductor
from servers.ensembl_mcp import server as ensembl
from servers.string_mcp import server as string


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def mock_http(self, handler):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        return patch("httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw))

    async def test_anaconda_search_uses_name_and_bounds_results(self):
        def handler(request):
            self.assertEqual(dict(request.url.params), {"name": "samtools"})
            return httpx.Response(200, json=[{"name": "samtools"}] * 5)
        with self.mock_http(handler):
            self.assertEqual(len(await anaconda.anaconda_search("samtools", 2)), 2)

    async def test_anaconda_rate_limit_propagates(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            with self.assertRaises(httpx.HTTPStatusError):
                await anaconda.anaconda_search("samtools")

    async def test_ensembl_json_format_preserves_parameters(self):
        def handler(request):
            self.assertEqual(request.url.params["content-type"], "application/json")
            if "/lookup/" in request.url.path:
                self.assertEqual(request.url.params["expand"], "1")
                return httpx.Response(200, json={"display_name": "TP53"})
            self.assertEqual(request.url.params["feature"], "gene")
            self.assertEqual(request.url.path, "/overlap/region/human/17:1-100")
            return httpx.Response(200, json=[])
        with self.mock_http(handler):
            self.assertEqual((await ensembl.ensembl_lookup("ENSG00000141510", True))["display_name"], "TP53")
            await ensembl.ensembl_overlap("human:17:1-100")

    async def test_ensembl_invalid_feature(self):
        with self.assertRaises(ValueError):
            await ensembl.ensembl_overlap("17:1-100", feature="invalid")

    async def test_bioconductor_looks_up_exact_name_in_index(self):
        def handler(request):
            self.assertTrue(request.url.path.endswith("/packages.json"))
            return httpx.Response(200, json={"DESeq2": {"Package": "DESeq2", "Version": "1.48.2"}})
        with self.mock_http(handler):
            result = await bioconductor.bioconductor_package("DESeq2")
            self.assertEqual(result["Package"], "DESeq2")
            self.assertEqual(result["repository"], "bioc")
            self.assertIn("/html/DESeq2.html", result["web_url"])
            install = await bioconductor.bioconductor_install("DESeq2")
            self.assertIn('BiocManager::install("DESeq2"', install["r"])

    async def test_bioconductor_fallback_supports_list_index(self):
        def handler(request):
            if "/bioc/" in request.url.path:
                return httpx.Response(404)
            return httpx.Response(200, json=[{"Package": "org.Hs.eg.db"}])
        with self.mock_http(handler):
            result = await bioconductor.bioconductor_package("org.Hs.eg.db")
            self.assertEqual(result["repository"], "data/annotation")

    async def test_bioconductor_does_not_hide_rate_limit(self):
        with self.mock_http(lambda req: httpx.Response(429)):
            for call in (bioconductor.bioconductor_package, bioconductor.bioconductor_search):
                with self.assertRaises(httpx.HTTPStatusError):
                    await call("DESeq2")

    async def test_bioconductor_missing_and_invalid_package(self):
        with self.mock_http(lambda req: httpx.Response(200, json={})):
            with self.assertRaisesRegex(ValueError, "not found"):
                await bioconductor.bioconductor_package("MissingPackage")
        with self.assertRaises(ValueError):
            await bioconductor.bioconductor_install('bad";system("command")')

    async def test_string_identifiers_encoded_once_and_edge_limit(self):
        def handler(request):
            self.assertEqual(request.url.params["identifiers"], "TP53\rMDM2")
            self.assertNotIn("%250d", str(request.url).lower())
            self.assertNotIn("limit", request.url.params)
            return httpx.Response(200, json=[{"score": 0.9}] * 8)
        with self.mock_http(handler):
            self.assertEqual(len(await string.string_interactions(["TP53", "MDM2"], limit=3)), 3)
            self.assertEqual(len(await string.string_interactions(["TP53", "MDM2"], limit=0)), 1)

    async def test_string_invalid_empty_list(self):
        with self.assertRaises(ValueError):
            await string.string_interactions([])


if __name__ == "__main__":
    unittest.main()
