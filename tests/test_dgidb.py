"""Mocked tests for the DGIdb MCP api."""
import httpx

from servers.dgidb_mcp import api
from tests.helpers import HTTPTestCase

GENES = {"data": {"genes": {"nodes": [
    {"name": "BRAF", "longName": "B-Raf proto-oncogene",
     "interactions": [{"interactionScore": 0.26, "drug": {"name": "BINIMETINIB"},
                       "sources": [{"sourceDbName": "ChEMBL"}]},
                      {"interactionScore": 0.006, "drug": {"name": "VINBLASTINE"},
                       "sources": [{"sourceDbName": "DrugBank"}]}]}]}}}
DRUGS = {"data": {"drugs": {"nodes": [
    {"name": "IMATINIB", "conceptId": "rxcui:282388", "approved": True,
     "interactions": [{"interactionScore": 0.03, "gene": {"name": "RET"}},
                      {"interactionScore": 0.005, "gene": {"name": "BRAF"}}]}]}}}
MATCHES = {"data": {"geneMatches": {
    "noMatches": [], "directMatches": [
        {"searchTerm": "BRAF1", "matchType": "ALIAS", "matches": [{"name": "BRAF",
                                                                   "longName": "B-Raf proto-oncogene"}]}]}}}


def response_for(query: str):
    if "genes(names" in query:
        return httpx.Response(200, json=GENES)
    if "drugs(names" in query:
        return httpx.Response(200, json=DRUGS)
    if "geneMatches(" in query:
        return httpx.Response(200, json=MATCHES)
    raise AssertionError(f"unexpected query: {query}")


class DgidbTests(HTTPTestCase):
    async def test_genes_drugs_and_matches(self):
        seen = []

        def handler(req):
            body = req.read().decode()
            seen.append(body)
            return response_for(body)

        with self.mock_http(handler):
            genes = await api.dgidb_genes(["braf"], first=2)
            interactions = genes["data"]["genes"]["nodes"][0]["interactions"]
            self.assertEqual(interactions[0]["drug"]["name"], "BINIMETINIB")
            self.assertEqual(len(interactions), 2)
            self.assertIn('"BRAF"', seen[0])
            drugs = await api.dgidb_drugs(["imatinib"])
            self.assertEqual(drugs["data"]["drugs"]["nodes"][0]["conceptId"], "rxcui:282388")
            self.assertTrue(drugs["data"]["drugs"]["nodes"][0]["approved"])
            matches = await api.dgidb_gene_matches(["BRAF1"])
            self.assertEqual(matches["data"]["geneMatches"]["directMatches"][0]["matchType"], "ALIAS")
            self.assertEqual(matches["data"]["geneMatches"]["noMatches"], [])
        self.assertEqual(len(seen), 3)

    async def test_graphql_error_becomes_value_error(self):
        with self.mock_http(lambda req: httpx.Response(200, json={"errors": [{"message": "bad query"}]})):
            with self.assertRaisesRegex(ValueError, "bad query"):
                await api.dgidb_genes(["BRAF"])

    async def test_validation_before_network(self):
        cases = [(api.dgidb_genes, {"names": []}),
                 (api.dgidb_genes, {"names": ["BRAF"] * 11}),
                 (api.dgidb_genes, {"names": ["BRAF"], "first": 0}),
                 (api.dgidb_drugs, {"names": [""]}),
                 (api.dgidb_drugs, {"names": ["imatinib"], "first": 101}),
                 (api.dgidb_gene_matches, {"search_terms": []}),
                 (api.dgidb_gene_matches, {"search_terms": ["a" * 151]})]
        for func, kwargs in cases:
            with self.subTest(tool=func.__name__, kwargs=kwargs), self.assertRaises(ValueError):
                await func(**kwargs)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(502)):
            with self.assertRaises(httpx.HTTPStatusError):
                await api.dgidb_drugs(["imatinib"])
