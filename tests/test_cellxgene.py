import json
import importlib.util
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from servers.cellxgene_mcp import server

DATASET = "00000000-0000-0000-0000-000000000001"
VERSION = "2025-11-08"


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


class CensusTests(unittest.IsolatedAsyncioTestCase):
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
        sdk.get_source_h5ad_uri.return_value = {"uri": "s3://example/dataset.h5ad", "s3_region": "us-west-2"}
        return sdk, frame

    async def test_version_and_source_uri(self):
        sdk, _ = self.make_sdk([])
        with patch.object(server, "_sdk", return_value=sdk):
            self.assertEqual((await server.cellxgene_versions())["results"][0]["release_build"], VERSION)
            result = await server.cellxgene_dataset_url(DATASET)
        sdk.get_source_h5ad_uri.assert_called_once_with(DATASET, census_version=VERSION)
        self.assertEqual(result["h5ad_uri"], "s3://example/dataset.h5ad")

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

    async def test_datasets_genes_and_empty_window(self):
        sdk, frame = self.make_sdk([])
        with patch.object(server, "_sdk", return_value=sdk):
            result = await server.cellxgene_datasets(scan_size=10)
            self.assertEqual(result["next_after_joinid"], 9)
            self.assertTrue(result["has_more"])
            self.assertEqual((await server.cellxgene_genes(gene_id="ENSG1"))["results"], [])
            self.assertIn("feature_id ==", frame.read.call_args.kwargs["value_filter"])
            frame.non_empty_domain.return_value = ((0, 0),)
            self.assertFalse((await server.cellxgene_datasets())["has_more"])
            result = await server.cellxgene_datasets(after_joinid=100)
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

    async def test_validation_all_tools(self):
        for func, args in [(server.cellxgene_versions, {"limit": 0}),
                           (server.cellxgene_datasets, {"scan_size": 10001}),
                           (server.cellxgene_cells, {"organism": "unknown"}),
                           (server.cellxgene_genes, {"gene_id": "../"}),
                           (server.cellxgene_expression, {"cell_ids": [0], "gene_ids": ["ENSG1"], "version": "stable"}),
                           (server.cellxgene_expression, {"cell_ids": [True], "gene_ids": ["ENSG1"], "version": VERSION}),
                           (server.cellxgene_expression, {"cell_ids": [0], "gene_ids": ["ENSG1"] * 101, "version": VERSION}),
                           (server.cellxgene_dataset_url, {"dataset_id": "bad"})]:
            with self.subTest(tool=func.__name__), self.assertRaises(ValueError):
                await func(**args)

    async def test_missing_sdk_and_upstream_failure(self):
        with patch("servers.cellxgene_mcp.server.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(RuntimeError, "optional SDK"):
                await server.cellxgene_versions()
        sdk, _ = self.make_sdk([])
        sdk.get_census_version_description.side_effect = RuntimeError("unavailable")
        with patch.object(server, "_sdk", return_value=sdk):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                await server.cellxgene_datasets()

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
