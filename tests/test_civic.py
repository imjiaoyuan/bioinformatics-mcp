import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import httpx

from servers.civic_mcp import server

from tests.helpers import HTTPTestCase

BASE = "https://civicdb.org/api/graphql"

RESPONSES = {
    "search": {"data": {"search": [{"id": 5, "name": "BRAF", "resultType": "FEATURE",
                                    "matchingText": "", "link": "/features/5"},
                                   {"id": 6, "name": "V600E", "resultType": "VARIANT",
                                    "matchingText": "", "link": "/variants/6"}]}},
    "gene": {"data": {"gene": {"id": 5, "name": "BRAF", "fullName": "B-Raf proto-oncogene",
                               "description": "BRAF mutations...", "entrezId": 673,
                               "featureAliases": ["B-RAF1"], "link": "/features/5",
                               "stats": {"variantCount": 114, "evidenceItemCount": 500,
                                         "assertionCount": 29, "molecularProfileCount": 182}}}},
    "variants": {"data": {"gene": {"variants": {
        "nodes": [{"id": 6, "name": "V600E", "variantAliases": ["V600E"],
                   "variantTypes": [{"id": 202, "name": "Missense Variant"}],
                   "feature": {"id": 5, "name": "BRAF"}, "link": "/variants/6"}],
        "pageInfo": {"endCursor": "Mg", "hasNextPage": True}, "totalCount": 114}}}},
    "variant": {"data": {"variant": {"id": 6, "name": "V600E", "variantAliases": ["V600E"],
                                     "variantTypes": [{"id": 202, "name": "Missense Variant"}],
                                     "feature": {"id": 5, "name": "BRAF"},
                                     "link": "/variants/6"}}},
    "evidenceItem": {"data": {"evidenceItem": {
        "id": 1, "name": "EID1", "description": "JAK2 V617F finding.",
        "evidenceType": "DIAGNOSTIC", "evidenceLevel": "B", "evidenceDirection": "SUPPORTS",
        "significance": "NEGATIVE", "variantOrigin": "SOMATIC", "status": "ACCEPTED",
        "evidenceRating": 4, "variantHgvs": "9:5073770-5073770", "link": "/evidence/1",
        "disease": {"id": 3034, "name": "Lymphoid Leukemia"}, "therapies": [], "phenotypes": [],
        "source": {"id": 51, "title": "JAK2V617F in CMMoL and AML",
                   "citation": "Levine et al., 2005"}}}},
    "evidenceItems": {"data": {"evidenceItems": {
        "nodes": [{"id": 259, "name": "EID259", "description": "Imatinib response.",
                   "evidenceType": "PREDICTIVE", "evidenceLevel": "A",
                   "evidenceDirection": "SUPPORTS", "significance": "SENSITIVITYRESPONSE",
                   "variantOrigin": "SOMATIC", "status": "ACCEPTED", "evidenceRating": 5,
                   "variantHgvs": None, "link": "/evidence/259",
                   "disease": {"id": 3033, "name": "Acute Myeloid Leukemia"},
                   "therapies": [{"id": 10, "name": "Imatinib"}], "phenotypes": [],
                   "source": {"id": 32, "title": "Imatinib study", "citation": "2002"}}],
        "pageInfo": {"endCursor": "Mg", "hasNextPage": True}, "totalCount": 464}}},
}

NOT_FOUND_ID = 404


def handler(request: httpx.Request) -> httpx.Response:
    if request.method != "POST" or str(request.url) != BASE:
        return httpx.Response(404)
    payload = json.loads(request.content)
    if payload.get("variables", {}).get("id") == NOT_FOUND_ID:
        return httpx.Response(NOT_FOUND_ID, json={"message": "Not Found"})
    if payload.get("variables", {}).get("symbol") == "ZZZZ":
        return httpx.Response(200, json={"errors": [{"message": "not found"}], "data": None})
    query = payload.get("query", "")
    mapping = (("search(", "search"), ("variants(", "variants"),
               ("evidenceItems(", "evidenceItems"), ("gene(entrezSymbol", "gene"),
               ("gene(id", "gene"), ("variant(id", "variant"), ("evidenceItem(id", "evidenceItem"))
    for field, key in mapping:
        if field in query:
            return httpx.Response(200, json=RESPONSES[key])
    return httpx.Response(200, json={"errors": [{"message": "not found"}], "data": None})


class CivicTests(HTTPTestCase):
    def mock(self):
        stack = ExitStack()
        stack.enter_context(self.mock_http(handler))
        stack.enter_context(patch("common.http.asyncio.sleep", new_callable=AsyncMock))
        return stack

    async def test_success_responses(self):
        with self.mock():
            search = await server.civic_search("BRAF", entity="VARIANT")
            self.assertEqual(search["status"], "ok")
            self.assertEqual(search["source_url"], BASE)
            self.assertEqual(search["results"][1]["resultType"], "VARIANT")
            gene = await server.civic_gene(gene_id="5")
            self.assertEqual(gene["data"]["gene"]["entrezId"], 673)
            symbol = await server.civic_gene(entrez_symbol="BRAF")
            self.assertEqual(symbol["data"]["gene"]["name"], "BRAF")
            variants = await server.civic_gene_variants("5")
            self.assertEqual(variants["results"][0]["name"], "V600E")
            self.assertEqual(variants["totalCount"], 114)
            self.assertEqual(variants["end_cursor"], "Mg")
            variant = await server.civic_variant("6")
            self.assertEqual(variant["data"]["variant"]["feature"]["name"], "BRAF")
            evidence = await server.civic_evidence_item("1")
            self.assertEqual(evidence["data"]["evidenceItem"]["evidenceLevel"], "B")
            listing = await server.civic_variant_evidence("6")
            self.assertEqual(listing["results"][0]["therapies"][0]["name"], "Imatinib")
            self.assertEqual(listing["has_next_page"], True)

    async def test_validation_errors(self):
        with self.mock():
            with self.assertRaises(ValueError):
                await server.civic_search("")
            with self.assertRaises(ValueError):
                await server.civic_search("BRAF", entity="GENE")
            with self.assertRaises(ValueError):
                await server.civic_search("BRAF", limit=0)
            with self.assertRaises(ValueError):
                await server.civic_gene()
            with self.assertRaises(ValueError):
                await server.civic_gene("5", "BRAF")
            with self.assertRaises(ValueError):
                await server.civic_gene(gene_id="abc")
            with self.assertRaises(ValueError):
                await server.civic_gene(entrez_symbol="BRAF; drop")
            with self.assertRaises(ValueError):
                await server.civic_gene_variants("bad")
            with self.assertRaises(ValueError):
                await server.civic_variant("6x")
            with self.assertRaises(ValueError):
                await server.civic_evidence_item("")
            with self.assertRaises(ValueError):
                await server.civic_variant_evidence("-1")

    async def test_http_error(self):
        with self.mock():
            with self.assertRaises(httpx.HTTPStatusError):
                await server.civic_gene(gene_id=str(NOT_FOUND_ID))

    async def test_graphql_error_response(self):
        with self.mock():
            result = await server.civic_gene(entrez_symbol="ZZZZ")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["errors"][0]["message"], "not found")
