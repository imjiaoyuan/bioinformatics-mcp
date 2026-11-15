import base64
from unittest.mock import AsyncMock, patch

import httpx

from servers.phytozome_mcp import api
from tests.helpers import HTTPTestCase

AUTH = base64.b64encode(b"user@example.org:secret").decode()


class PhytozomeTests(HTTPTestCase):
    def setUp(self):
        super().setUp()
        self.env = patch.dict("os.environ", {"JGI_EMAIL": "user@example.org",
                                             "JGI_PASSWORD": "secret"})

    async def test_organisms_list_and_filter(self):
        def handler(req):
            self.assertEqual(req.headers["Authorization"], f"Basic {AUTH}")
            self.assertEqual(req.url.params["compressed"], "false")
            return httpx.Response(200, json={"data": [
                {"organism": "Athaliana", "organismName": "Athaliana",
                 "scientific_name": "Arabidopsis thaliana", "version": "1.1",
                 "geneCount": 35386, "taxonomy": "eudicotyledons"},
                {"organism": "Sbicolor", "organismName": "Sbicolor",
                 "scientific_name": "Sorghum bicolor", "version": "3.1.1",
                 "geneCount": 34211, "taxonomy": "monocots"}]})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.phytozome_organisms()
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["results"][0]["scientific_name"], "Arabidopsis thaliana")
            self.assertFalse(result["truncated"])
            filtered = await api.phytozome_organisms(query="sorghum")
            self.assertEqual(filtered["total"], 1)
            self.assertEqual(filtered["results"][0]["organism"], "Sbicolor")
            paged = await api.phytozome_organisms(limit=1, offset=1)
            self.assertEqual(paged["results"][0]["organism"], "Sbicolor")
            self.assertFalse(paged["truncated"])

    async def test_organism_detail(self):
        def handler(req):
            self.assertIn("/organism/Athaliana", req.url.path)
            return httpx.Response(200, json={"organism": "Athaliana",
                                             "scientific_name": "Arabidopsis thaliana",
                                             "version": "1.1"})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.phytozome_organism("Athaliana")
            self.assertEqual(result["scientific_name"], "Arabidopsis thaliana")
            self.assertEqual(result["organism_id"], "Athaliana")

    async def test_gene_detail(self):
        def handler(req):
            self.assertIn("/gene/AT1G01010", req.url.path)
            return httpx.Response(200, json={"transcriptId": "AT1G01010.1",
                                             "chr": "Chr1", "start": 5928, "end": 8737,
                                             "strand": "+", "aliases": ["COLD1"],
                                             "go_terms": ["GO:0003676"],
                                             "geneName": "AT1G01010",
                                             "organismName": "Athaliana"})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.phytozome_gene("AT1G01010")
            self.assertEqual(result["transcript_id"], "AT1G01010.1")
            self.assertEqual(result["chromosome"], "Chr1")
            self.assertEqual(result["start"], 5928)
            self.assertEqual(result["strand"], "+")
            self.assertEqual(result["synonyms"], ["COLD1"])
            self.assertEqual(result["go_terms"], ["GO:0003676"])
            self.assertIn("raw", result)

    async def test_gene_search(self):
        def handler(req):
            self.assertEqual(req.url.params["keyword"], "cold")
            if "organism" in req.url.params:
                self.assertEqual(req.url.params["organism"], "Athaliana")
            return httpx.Response(200, json=[{"geneId": "AT1G01010", "organismName": "Athaliana"},
                                             {"geneId": "AT2G28570", "organismName": "Athaliana"}])
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.phytozome_gene_search("cold", organism="Athaliana")
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["results"][0]["geneId"], "AT1G01010")
            paged = await api.phytozome_gene_search("cold", limit=1, offset=1)
            self.assertEqual(paged["results"][0]["geneId"], "AT2G28570")
            self.assertFalse(paged["truncated"])

    async def test_download_info_urls_only(self):
        with self.env:
            result = await api.phytozome_download_info("Athaliana")
        self.assertEqual(result["info_url"], "https://phytozome-next.jgi.doe.gov/info/Athaliana")
        self.assertIn("JGI", result["directory_note"])

    async def test_unknown_shape_passthrough(self):
        def handler(req):
            if "/gene/search" in req.url.path:
                return httpx.Response(200, json={"unexpected": {"nested": "shape"}})
            return httpx.Response(200, json={"weird": [1, 2, 3]})
        with self.env, self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            result = await api.phytozome_gene_search("cold")
            self.assertEqual(result["raw"], {"unexpected": {"nested": "shape"}})
            result = await api.phytozome_organisms()
            self.assertEqual(result["raw"], {"weird": [1, 2, 3]})

    async def test_missing_credentials(self):
        cases = [(api.phytozome_organisms, {"query": "a"}),
                 (api.phytozome_organism, {"organism_id": "Athaliana"}),
                 (api.phytozome_gene, {"gene_id": "AT1G01010"}),
                 (api.phytozome_gene_search, {"keyword": "cold"}),
                 ]
        with patch.dict("os.environ", {"JGI_EMAIL": "user@example.org"}, clear=True):
            for func, args in cases:
                with self.subTest(tool=func.__name__, error="missing password"), self.assertRaises(ValueError):
                    await func(**args)
        with patch.dict("os.environ", {"JGI_PASSWORD": "secret"}, clear=True):
            with self.assertRaises(ValueError):
                await api.phytozome_organisms()

    async def test_validation(self):
        with self.env:
            cases = [(api.phytozome_organism, {"organism_id": "bad name!"}),
                     (api.phytozome_gene, {"gene_id": "bad id;rm"}),
                     (api.phytozome_gene_search, {"keyword": ""}),
                     (api.phytozome_gene_search, {"keyword": "cold", "organism": "bad name!"}),
                     (api.phytozome_gene_search, {"keyword": "cold", "limit": 0}),
                     (api.phytozome_organisms, {"limit": 0}),
                     (api.phytozome_organisms, {"offset": -1}),
                     (api.phytozome_download_info, {"organism": "bad name!"})]
            for func, args in cases:
                with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                    await func(**args)

    async def test_401_invalid_credentials(self):
        with self.env, self.mock_http(lambda req: httpx.Response(401)), \
                patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(ValueError) as ctx:
                await api.phytozome_organisms()
        self.assertIn("Invalid JGI credentials", str(ctx.exception))
