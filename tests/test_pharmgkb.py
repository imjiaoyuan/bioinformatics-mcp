import httpx
from unittest.mock import AsyncMock, patch

from servers.pharmgkb_mcp import server
from tests.helpers import HTTPTestCase


def data_response(rows):
    return httpx.Response(200, json={"status": "success", "data": rows})


class PharmGKBTests(HTTPTestCase):
    async def test_all_tools_success(self):
        drug = {"objCls": "Chemical", "id": "PA448498", "name": "astemizole"}
        gene = {"objCls": "Gene", "id": "PA128", "symbol": "CYP2D6"}
        variant = {"objCls": "Variant", "id": "PA166155139", "symbol": "rs104894541"}
        annotation = {"accessionId": "PA166134613", "levelOfEvidence": {"term": "3"},
                      "allelePhenotypes": [{"allele": "CC", "phenotype": "resistant"}]}
        paths = []

        def handler(req):
            paths.append((req.url.path, dict(req.url.params)))
            if "accessionId" in req.url.params:
                expected = {"drug": "PA448498", "gene": "PA128", "variant": "PA166155139"}
                kind = req.url.path.rsplit("/", 1)[-1]
                self.assertEqual(req.url.params["accessionId"], expected[kind])
                return data_response([{"objCls": "Chemical", "id": req.url.params["accessionId"]}])
            if "Annotation" in req.url.path:
                self.assertEqual(req.url.params["relatedChemicals.accessionId"], "PA449085")
                return data_response([annotation])
            self.assertEqual(req.url.params["name"], "warfarin")
            return data_response([drug])

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.pharmgkb_drug("pa448498"))["results"][0]["id"], "PA448498")
            self.assertTrue((await server.pharmgkb_gene("PA128"))["source_url"].endswith("/gene?accessionId=PA128"))
            self.assertEqual((await server.pharmgkb_variant("PA166155139"))["results"][0]["id"], "PA166155139")
            search = await server.pharmgkb_search("warfarin", "drug", limit=1, offset=0)
            self.assertEqual(search["results"], [drug])
            self.assertEqual(search["pagination"], "local")
            ca = await server.pharmgkb_clinical_annotations("PA449085", limit=2, offset=0)
            self.assertEqual(ca["results"], [annotation])
            self.assertEqual((ca["limit"], ca["total"]), (2, 1))
            self.assertEqual((await server.pharmgkb_annotations("PA449085"))["results"], [annotation])
            self.assertEqual((await server.pharmgkb_annotations("PA449085", "label"))["annotation_type"], "label")

    async def test_validation_all_tools(self):
        for func, args in [(server.pharmgkb_drug, {"drug_id": "warfarin"}),
                           (server.pharmgkb_gene, {"gene_id": "../PA128"}),
                           (server.pharmgkb_variant, {"variant_id": "rs9923189"}),
                           (server.pharmgkb_search, {"query": ""}),
                           (server.pharmgkb_search, {"query": "x", "object_type": "pathway"}),
                           (server.pharmgkb_search, {"query": "x", "limit": 101}),
                           (server.pharmgkb_clinical_annotations, {"drug_id": "PA449085", "limit": 0}),
                           (server.pharmgkb_annotations, {"drug_id": "PA449085", "annotation_type": "ca"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.pharmgkb_gene("PA128")
