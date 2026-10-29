"""Deterministic regression checks for provider request/response handling."""
import unittest
from unittest.mock import patch

import httpx

from servers.anaconda_mcp import server as anaconda
from servers.bioconductor_mcp import server as bioconductor
from servers.ensembl_mcp import server as ensembl
from servers.pdb_mcp import server as pdb
from servers.publications_mcp import server as publications
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

    async def test_anaconda_package_validates_path_segments(self):
        for owner, package in [("../evil", "samtools"), ("bioconda", "a b"),
                               ("bioconda/extra", "samtools"), ("", "samtools")]:
            with self.subTest(owner=owner, package=package), self.assertRaises(ValueError):
                await anaconda.anaconda_package(owner, package)

    async def test_anaconda_package_uses_normalized_path(self):
        def handler(request):
            self.assertEqual(request.url.path, "/package/BIOCONDA/Samtools")
            return httpx.Response(200, json={"files": [{"version": "1.0"}, {"version": "2.0"}]})
        with self.mock_http(handler):
            files = await anaconda.anaconda_files("BIOCONDA", "Samtools", version="2.0")
        self.assertEqual([f["version"] for f in files], ["2.0"])

    async def test_anaconda_search_rejects_out_of_range_limit(self):
        with self.assertRaises(ValueError):
            await anaconda.anaconda_search("samtools", limit=0)

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

    async def test_ensembl_validates_stable_ids(self):
        for identifier in ("ENSG00000141510;DROP", "../../etc", "TP53 human", ""):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                await ensembl.ensembl_lookup(identifier)

    async def test_ensembl_validates_region_and_species(self):
        for region in ("7:140424943-140624564/../../etc", "17:1-100 and more", "17:"):
            with self.subTest(region=region), self.assertRaises(ValueError):
                await ensembl.ensembl_overlap(region)
        with self.assertRaises(ValueError):
            await ensembl.ensembl_overlap("17:1-100", species="human/extra")

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
            self.assertEqual(len(await string.string_interactions(["TP53", "MDM2"], limit=1)), 1)

    async def test_string_invalid_empty_list(self):
        with self.assertRaises(ValueError):
            await string.string_interactions([])

    async def test_string_validates_species_and_protein_names(self):
        with self.assertRaises(ValueError):
            await string.string_resolve(["TP53"], species=0)
        with self.assertRaises(ValueError):
            await string.string_resolve(["TP53"], species="9606")
        with self.assertRaises(ValueError):
            await string.string_resolve(["TP53,MDM2"])
        with self.assertRaises(ValueError):
            await string.string_interactions(["TP53"], required_score=1001)

    async def test_pdb_validates_ids_and_bounds(self):
        for pdb_id in ("4HH", "4HHBB", "4HHB/../../etc", "fourc", ""):
            with self.subTest(pdb_id=pdb_id), self.assertRaises(ValueError):
                await pdb.pdb_entry(pdb_id)
        with self.assertRaises(ValueError):
            await pdb.pdb_search("hemoglobin", max_results=0)
        with self.assertRaises(ValueError):
            await pdb.pdb_search("")

    async def test_pdb_entry_uppercases_valid_id(self):
        def handler(request):
            self.assertTrue(request.url.path.endswith("/entry/4HHB"))
            return httpx.Response(200, json={"id": "4HHB"})
        with self.mock_http(handler):
            result = await pdb.pdb_entry("4hhb")
        self.assertEqual(result["id"], "4HHB")

    async def test_publications_validates_inputs(self):
        with self.assertRaises(ValueError):
            await publications.publication_by_doi("not-a-doi")
        with self.assertRaises(ValueError):
            await publications.publication_search("query", year_from=1300)
        with self.assertRaises(ValueError):
            await publications.publication_search("query", year_from=9999)
        with self.assertRaises(ValueError):
            await publications.publication_search("query", publisher="elsevier")
        with self.assertRaises(ValueError):
            await publications.publication_search("")

    async def test_publications_doi_accepts_url_prefixes(self):
        def handler(request):
            self.assertTrue(request.url.path.endswith("/works/10.1038/nature12373"))
            return httpx.Response(200, json={"message": {"DOI": "10.1038/nature12373"}})
        with self.mock_http(handler):
            result = await publications.publication_by_doi("https://doi.org/10.1038/nature12373")
        self.assertEqual(result["doi"], "10.1038/nature12373")

    async def test_publications_total_distinguishes_filtered_from_upstream(self):
        def handler(request):
            self.assertIn("select", request.url.params)
            items = [{"DOI": "10.1/a", "publisher": "Cell Press", "container-title": ["Cell"]},
                     {"DOI": "10.1/b", "publisher": "Other", "container-title": ["Journal"]}]
            return httpx.Response(200, json={"message": {"items": items, "total-results": 57}})
        with self.mock_http(handler):
            result = await publications.publication_search("p53", publisher="cell")
        self.assertEqual(result["total_matches"], 57)
        self.assertEqual(result["total"], 1)
        self.assertTrue(result["filtered"])


if __name__ == "__main__":
    unittest.main()
