import httpx

from servers.interpro_mcp import api
from tests.helpers import HTTPTestCase


class InterProTests(HTTPTestCase):
    async def test_search_and_entry(self):
        def handler(req):
            if req.url.params.get("search"):
                self.assertEqual(req.url.params["page_size"], "1")
                return httpx.Response(200, json={"count": 2, "next": "next-page", "results": [{"metadata": {"accession": "IPR002117"}}]})
            return httpx.Response(200, json={"metadata": {"accession": "IPR002117", "go_terms": [{"identifier": "GO:1"}]}})
        with self.mock_http(handler):
            self.assertEqual((await api.interpro_search("p53", limit=1))["next"], "next-page")
            self.assertTrue((await api.interpro_entry("IPR002117"))["metadata"]["go_terms"])

    async def test_protein_annotations_and_taxon_filter(self):
        def handler(req):
            if "/protein/reviewed/" in req.url.path:
                self.assertIn("/taxonomy/uniprot/4530/", req.url.path)
            return httpx.Response(200, json={"results": [{"proteins": [{"entry_protein_locations": [{"start": 1, "end": 50}]}]}]})
        with self.mock_http(handler):
            self.assertTrue((await api.interpro_protein_annotations("P04637"))["results"])
            self.assertTrue((await api.interpro_proteins("IPR002117", taxon_id=4530))["results"])

    async def test_empty_and_pending_are_distinct(self):
        with self.mock_http(lambda req: httpx.Response(204)):
            self.assertEqual((await api.interpro_search("nothing"))["results"], [])
        with self.mock_http(lambda req: httpx.Response(408)):
            self.assertEqual((await api.interpro_search("slow query"))["status"], "pending")

    async def test_validation_all_tools(self):
        for func, args in [(api.interpro_search, {"query": ""}), (api.interpro_entry, {"accession": "bad"}),
                           (api.interpro_protein_annotations, {"accession": "../../bad"}),
                           (api.interpro_proteins, {"accession": "IPR002117", "taxon_id": 0})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.interpro_entry("IPR002117")
