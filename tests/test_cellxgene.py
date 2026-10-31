import json
import importlib.util
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

from servers.cellxgene_mcp import server
from tests.helpers import HTTPTestCase

DATASET = "00000000-0000-0000-0000-000000000001"
COLLECTION = "8e880741-bf9a-4c8e-9227-934204631d2a"
VERSION = "2025-11-08"

RELEASE = {
    "stable": "2025-11-08",
    "latest": "2025-11-17",
    "2025-11-17": {"release_build": "2025-11-17", "flags": {},
                   "h5ads": {"relative_uri": "/cell-census/2025-11-17/h5ads/", "s3_region": "us-west-2"}},
    VERSION: {"release_build": VERSION, "release_date": "2025-11-08", "flags": {"lts": True},
              "h5ads": {"uri": "s3://cellxgene-census-public-us-west-2/cell-census/2025-11-08/h5ads/",
                        "relative_uri": "/cell-census/2025-11-08/h5ads/", "s3_region": "us-west-2"}},
}
DISCOVER = [
    {"dataset_id": DATASET, "dataset_version_id": "11111111-1111-1111-1111-111111111111",
     "collection_id": COLLECTION, "collection_name": "Atlas",
     "title": "Lung atlas", "organism": [{"label": "Homo sapiens", "ontology_term_id": "NCBITaxon:9606"}],
     "tissue": [{"label": "lung", "ontology_term_id": "UBERON:0002048", "tissue_type": "tissue"}],
     "disease": [{"label": "normal", "ontology_term_id": "PATO:0000461"}],
     "assay": [{"label": "10x 3' v3", "ontology_term_id": "EFO:0009922"}],
     "cell_count": 26239, "is_primary_data": True, "schema_version": "5.2.0", "published_at": "2024-01-01T00:00:00Z",
     "assets": [{"filesize": 1000, "filetype": "H5AD",
                 "url": f"https://datasets.cellxgene.cziscience.com/11111111-1111-1111-1111-111111111111.h5ad"}],
     "explorer_url": "https://cellxgene.cziscience.com/e/x.cxg/"},
    {"dataset_id": "00000000-0000-0000-0000-000000000002",
     "collection_id": "00000000-0000-0000-0000-000000000003", "collection_name": "Other",
     "title": "Mouse brain", "organism": [{"label": "Mus musculus"}], "tissue": [{"label": "brain"}],
     "disease": [], "assay": [], "cell_count": 5, "is_primary_data": False, "assets": []},
]


class Table:
    def __init__(self, rows):
        self.rows = rows

    def slice(self, start, length):
        return Table(self.rows[start:start + length])

    def to_pylist(self):
        return self.rows


class Records:
    def __init__(self, rows):
        self.rows = rows

    def to_json(self, orient):
        return json.dumps(self.rows)


class RestTests(HTTPTestCase):
    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("release.json"):
            return httpx.Response(200, json=RELEASE)
        if request.url.path == "/curation/v1/datasets":
            return httpx.Response(200, json=DISCOVER)
        if request.url.path == f"/curation/v1/collections/{COLLECTION}":
            return httpx.Response(200, json={"collection_id": COLLECTION, "datasets": [DISCOVER[0]]})
        return httpx.Response(404)

    async def test_versions_rest(self):
        with self.mock_http(self.handler):
            result = await server.cellxgene_versions()
        rows = {row["release_build"]: row for row in result["results"]}
        self.assertIn(VERSION, rows)
        self.assertEqual(result["aliases"], {"stable": "2025-11-08", "latest": "2025-11-17"})

    async def test_datasets_filters_and_paging(self):
        with self.mock_http(self.handler):
            result = await server.cellxgene_datasets(organism="Homo sapiens", tissue="lung")
        self.assertEqual(len(result["results"]), 1)
        row = result["results"][0]
        self.assertEqual(row["dataset_id"], DATASET)
        self.assertEqual(row["organism"], ["Homo sapiens"])
        self.assertEqual(row["tissue"], ["lung"])
        self.assertIn("datasets.cellxgene.cziscience.com", row["assets"][0]["url"])
        with self.mock_http(self.handler):
            result = await server.cellxgene_datasets(query="mouse")
        self.assertEqual(result["results"][0]["title"], "Mouse brain")

    async def test_dataset_by_id_and_collection(self):
        with self.mock_http(self.handler):
            result = await server.cellxgene_datasets(dataset_id=DATASET)
        self.assertEqual(result["total"], 1)
        with self.mock_http(self.handler):
            result = await server.cellxgene_datasets(collection_id=COLLECTION)
        self.assertEqual(result["total"], 1)
        self.assertTrue(all(r["collection_id"] == COLLECTION for r in result["results"]))

    async def test_dataset_url_rest(self):
        with self.mock_http(self.handler):
            result = await server.cellxgene_dataset_url(DATASET)
            stable = await server.cellxgene_dataset_url(DATASET, version="latest")
        self.assertEqual(result["census_version"], "2025-11-08")
        self.assertEqual(result["h5ad_uri"],
                         f"s3://cellxgene-census-public-us-west-2/cell-census/2025-11-08/h5ads/{DATASET}.h5ad")
        self.assertTrue(result["https_url"].startswith(
            "https://cellxgene-census-public-us-west-2.s3.us-west-2.amazonaws.com/cell-census/2025-11-08/h5ads/"))
        self.assertEqual(stable["census_version"], "2025-11-17")
        with self.mock_http(self.handler):
            with self.assertRaises(ValueError):
                await server.cellxgene_dataset_url(DATASET, version="1999-01-01")

    async def test_rest_tools_work_without_sdk(self):
        with self.mock_http(self.handler), \
                patch("servers.cellxgene_mcp.server.importlib.import_module", side_effect=ImportError):
            await server.cellxgene_versions()
            await server.cellxgene_datasets(organism="Homo sapiens")
            await server.cellxgene_dataset_url(DATASET)

    async def test_validation_rest(self):
        for func, args in [(server.cellxgene_versions, {"limit": 0}),
                           (server.cellxgene_versions, {"offset": -1}),
                           (server.cellxgene_datasets, {"organism": ""}),
                           (server.cellxgene_datasets, {"dataset_id": "bad"}),
                           (server.cellxgene_datasets, {"collection_id": "../"}),
                           (server.cellxgene_dataset_url, {"dataset_id": "bad"}),
                           (server.cellxgene_dataset_url, {"dataset_id": DATASET, "version": "bad"})]:
            with self.subTest(tool=func.__name__, args=args):
                with self.mock_http(self.handler):
                    with self.assertRaises(ValueError):
                        await func(**args)

    async def test_rate_limit_error(self):
        with self.mock_http(lambda req: httpx.Response(429)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.cellxgene_versions()


class SdkTests(unittest.IsolatedAsyncioTestCase):
    def make_sdk(self, rows):
        frame = Mock()
        frame.schema.names = ["soma_joinid", "dataset_id", "feature_id", "feature_name", "tissue"]
        frame.non_empty_domain.return_value = ((0, 9999),)
        frame.read.return_value = MagicMock()
        frame.read.return_value.__iter__.side_effect = lambda: iter([Table(rows)])
        experiment = SimpleNamespace(obs=frame, ms={"RNA": SimpleNamespace(var=frame)})
        census = {"census_info": {"datasets": frame}, "census_data": {"homo_sapiens": experiment}}
        sdk = Mock()
        sdk.get_census_version_description.return_value = {"release_build": VERSION}
        sdk.get_census_version_directory.return_value = {"stable": {"release_build": VERSION}}
        sdk.open_soma.side_effect = lambda **kw: nullcontext(census)
        sdk.get_anndata.return_value = None
        return sdk, frame

    async def test_scan_window_cursor_escaping_and_no_concat(self):
        rows = [{"soma_joinid": 10, "feature_id": "ENSG1"}, {"soma_joinid": 15, "feature_id": "ENSG2"}]
        sdk, frame = self.make_sdk(rows)
        with patch.object(server, "_sdk", return_value=sdk):
            result = await server.cellxgene_cells(tissue='lung" or tissue != "x', after_joinid=9, scan_size=20, limit=1)
        kwargs = frame.read.call_args.kwargs
        self.assertEqual(kwargs["coords"], (slice(10, 29),))
        self.assertEqual(kwargs["value_filter"], 'tissue == "lung\\" or tissue != \\"x"')
        self.assertEqual(result["next_after_joinid"], 10)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["has_more"])
        self.assertEqual(result["census_version"], VERSION)
        frame.read.return_value.concat.assert_not_called()

    async def test_genes_and_empty_window(self):
        sdk, frame = self.make_sdk([])
        with patch.object(server, "_sdk", return_value=sdk):
            self.assertEqual((await server.cellxgene_genes(gene_id="ENSG1"))["results"], [])
            self.assertIn("feature_id ==", frame.read.call_args.kwargs["value_filter"])
            frame.non_empty_domain.return_value = ((0, 0),)
            self.assertFalse((await server.cellxgene_genes())["has_more"])
            result = await server.cellxgene_genes(after_joinid=100)
            self.assertEqual(result["next_after_joinid"], 100)
            self.assertFalse(result["has_more"])

    async def test_expression_bounded_selection_axes_and_missing_ids(self):
        sdk, _ = self.make_sdk([])
        matrix = Mock()
        matrix.toarray.return_value.tolist.return_value = [[7]]
        sdk.get_anndata.return_value = SimpleNamespace(n_obs=1, n_vars=1, X=matrix,
            obs=Records([{"soma_joinid": 10, "dataset_id": DATASET}]),
            var=Records([{"soma_joinid": 20, "feature_id": "ENSG1"}]))
        with patch.object(server, "_sdk", return_value=sdk):
            result = await server.cellxgene_expression([10, 11], ["ENSG1", "ENSG2"], VERSION)
        self.assertEqual(sdk.get_anndata.call_args.kwargs["obs_coords"], [10, 11])
        self.assertEqual(sdk.get_anndata.call_args.kwargs["X_name"], "raw")
        self.assertEqual(result["matrix"], [[7]])
        self.assertEqual(result["missing_cell_ids"], [11])
        self.assertEqual(result["missing_gene_ids"], ["ENSG2"])

    async def test_validation_sdk_tools(self):
        for func, args in [(server.cellxgene_cells, {"organism": "unknown"}),
                           (server.cellxgene_genes, {"gene_id": "../"}),
                           (server.cellxgene_expression, {"cell_ids": [0], "gene_ids": ["ENSG1"], "version": "stable"}),
                           (server.cellxgene_expression, {"cell_ids": [True], "gene_ids": ["ENSG1"], "version": VERSION}),
                           (server.cellxgene_expression, {"cell_ids": [0], "gene_ids": ["ENSG1"] * 101, "version": VERSION})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_missing_sdk_and_upstream_failure(self):
        with patch("servers.cellxgene_mcp.server.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(RuntimeError, "Optional CELLxGENE SDK"):
                await server.cellxgene_cells()
            with self.assertRaisesRegex(RuntimeError, "Optional CELLxGENE SDK"):
                await server.cellxgene_genes()
            with self.assertRaisesRegex(RuntimeError, "Optional CELLxGENE SDK"):
                await server.cellxgene_expression([0], ["ENSG1"], VERSION)
        sdk, _ = self.make_sdk([])
        sdk.get_census_version_description.side_effect = RuntimeError("unavailable")
        with patch.object(server, "_sdk", return_value=sdk):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                await server.cellxgene_cells()

    @unittest.skipUnless(importlib.util.find_spec("tiledbsoma"), "optional CELLxGENE SDK is not installed")
    async def test_real_soma_dataframe_iterator_and_filter(self):
        """Catch SDK iterator/filter incompatibilities using a tiny local SOMA dataframe."""
        import pyarrow as pa
        import tiledbsoma as soma

        with tempfile.TemporaryDirectory() as directory:
            uri = f"{directory}/cells"
            schema = pa.schema([("soma_joinid", pa.int64()), ("tissue", pa.large_string())])
            with soma.DataFrame.create(uri, schema=schema, domain=[(0, 2)]) as frame:
                frame.write(pa.Table.from_pydict({"soma_joinid": [0, 1, 2], "tissue": ["lung", "brain", "lung"]}, schema=schema))
            with soma.DataFrame.open(uri) as frame:
                sdk = Mock()
                sdk.get_census_version_description.return_value = {"release_build": VERSION}
                sdk.open_soma.return_value = nullcontext({"census_data": {"homo_sapiens": SimpleNamespace(obs=frame)}})
                with patch.object(server, "_sdk", return_value=sdk):
                    result = await server.cellxgene_cells(tissue="lung", limit=1, scan_size=3)
            self.assertEqual(result["results"], [{"soma_joinid": 0, "tissue": "lung"}])
            self.assertEqual(result["next_after_joinid"], 0)
            self.assertTrue(result["truncated"])
