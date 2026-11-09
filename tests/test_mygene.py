from urllib.parse import parse_qs

from unittest.mock import AsyncMock, patch

import httpx

from servers.mygene_mcp import server
from tests.helpers import HTTPTestCase


def form(req):
    return {k: v[0] for k, v in parse_qs(req.content.decode()).items()}


class MyGeneTests(HTTPTestCase):
    async def test_all_tools_success(self):
        paths = []

        def handler(req):
            paths.append((req.url.host, req.url.path))
            if req.url.path == "/v3/query" and req.method == "GET":
                self.assertEqual(req.url.params["q"], "symbol:cdk2")
                self.assertEqual(req.url.params["size"], "5")
                self.assertEqual(req.url.params["from"], "10")
                self.assertEqual(req.url.params["species"], "human")
                return httpx.Response(200, json={"hits": [{"_id": "1017", "symbol": "CDK2"}], "total": 3})
            if req.url.path == "/v3/gene/1017":
                self.assertEqual(req.url.params["fields"], "symbol,name")
                return httpx.Response(200, json={"_id": "1017", "symbol": "CDK2", "name": "cyclin-dependent kinase 2"})
            if req.url.path == "/v3/query" and req.method == "POST":
                data = form(req)
                self.assertEqual(data["q"], "1017,ENSG00000123374")
                self.assertEqual(data["scopes"], "entrezgene,ensemblgene")
                return httpx.Response(200, json=[{"query": "1017", "_id": "1017", "symbol": "CDK2"},
                                                 {"query": "ENSG00000123374", "notfound": True}])
            if req.url.path == "/v1/variant/chr1:g.35367G>A":
                self.assertEqual(req.url.params["fields"], "cadd")
                return httpx.Response(200, json={"_id": "chr1:g.35367G>A", "cadd": {"phred": 1.493}})
            if req.url.path == "/v1/variant" and req.method == "POST":
                data = form(req)
                self.assertEqual(data["ids"], "chr1:g.35367G>A,chr7:g.55241707G>T")
                return httpx.Response(200, json=[{"query": "chr1:g.35367G>A", "_id": "chr1:g.35367G>A"},
                                                 {"query": "chr7:g.55241707G>T", "notfound": True}])
            if req.url.path == "/v3/metadata":
                return httpx.Response(200, json={"species": [{"taxid": 9606}], "build_version": "2023"})
            return httpx.Response(404)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            hits = await server.mygene_query("symbol:cdk2", species="human", limit=5, skip=10)
            self.assertEqual(hits["hits"][0]["symbol"], "CDK2")
            self.assertEqual(hits["source_url"], "https://api.mygene.info/v3/query?q=symbol%3Acdk2&size=5&from=10&species=human")
            gene = await server.mygene_gene("1017", fields="symbol,name")
            self.assertEqual(gene["symbol"], "CDK2")
            batch = await server.mygene_batch(["1017", "ENSG00000123374"], scopes="entrezgene,ensemblgene")
            self.assertNotIn("notfound", batch["results"][0])
            self.assertTrue(batch["results"][1]["notfound"])
            variant = await server.myvariant_variant("chr1:g.35367G>A", fields="cadd")
            self.assertEqual(variant["cadd"]["phred"], 1.493)
            self.assertEqual(variant["source_url"], "https://api.myvariant.info/v1/variant/chr1:g.35367G%3EA?fields=cadd")
            vbatch = await server.myvariant_batch(["chr1:g.35367G>A", "chr7:g.55241707G>T"])
            self.assertNotIn("notfound", vbatch["results"][0])
            meta = await server.mygene_metadata()
            self.assertEqual(meta["build_version"], "2023")
        self.assertIn(("api.myvariant.info", "/v1/variant"), paths)

    async def test_empty_optional_fields_omitted(self):
        def handler(req):
            self.assertNotIn("fields", req.url.params)
            self.assertNotIn("species", req.url.params)
            return httpx.Response(200, json={"hits": []})

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            self.assertEqual((await server.mygene_query("cdk2"))["hits"], [])

    async def test_validation_all_tools(self):
        cases = [(server.mygene_query, {"query": ""}),
                 (server.mygene_query, {"query": "cdk2", "limit": 101}),
                 (server.mygene_gene, {"gene_id": "bad id"}),
                 (server.mygene_batch, {"ids": []}),
                 (server.mygene_batch, {"ids": ["1017", "bad\nid"]}),
                 (server.mygene_batch, {"ids": ["1017"], "scopes": "a" * 201}),
                 (server.myvariant_variant, {"variant_id": "chr1;g.35367G>A"}),
                 (server.myvariant_variant, {"variant_id": "chr1:g.35367G>A", "fields": "a" * 501}),
                 (server.myvariant_batch, {"ids": []}),
                 (server.myvariant_batch, {"ids": ["chr1:g.1A>T;drop"]})]
        for func, args in cases:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.mygene_gene("999999999999")
        with self.mock_http(lambda req: httpx.Response(404)):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.myvariant_variant("chr1:g.999999999A>T")
