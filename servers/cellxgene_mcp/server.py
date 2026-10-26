"""Versioned CELLxGENE Census queries with bounded coordinate selections."""
from __future__ import annotations

import asyncio
import importlib
import json

from mcp.server.fastmcp import FastMCP

from common.api import choice, local_page
from common.http import bounded, identifier, identifiers, text

mcp = FastMCP("cellxgene")
SOURCE = "https://cellxgene.cziscience.com/census"


def _sdk():
    try:
        return importlib.import_module("cellxgene_census")
    except ImportError as exc:
        raise RuntimeError("Install the optional SDK from the repository root: pip install -e '.[cellxgene]'") from exc


def _version(value: str) -> str:
    return identifier(value, r"(?:stable|latest|[0-9]{4}-[0-9]{2}-[0-9]{2})", "Census version")


def _organism(value: str) -> str:
    return choice(value, {"homo_sapiens", "mus_musculus"}, "organism")


def _resolved(sdk, version: str) -> tuple[str, dict]:
    description = sdk.get_census_version_description(version)
    return description["release_build"], description


def _literal(value: str) -> str:
    # JSON string escaping is compatible with SOMA's string filter grammar.
    return json.dumps(text(value, "filter value", 200), ensure_ascii=True)


def _scan(kind: str, organism: str, version: str, limit: int, after_joinid: int,
          scan_size: int, filters: dict) -> dict:
    sdk = _sdk()
    release, description = _resolved(sdk, version)
    start, end = after_joinid + 1, after_joinid + scan_size
    with sdk.open_soma(census_version=release) as census:
        if kind == "datasets":
            frame = census["census_info"]["datasets"]
            wanted = ["soma_joinid", "dataset_id", "collection_id", "collection_name",
                      "dataset_title", "dataset_total_cell_count"]
        else:
            experiment = census["census_data"][organism]
            frame = experiment.obs if kind == "cells" else experiment.ms["RNA"].var
            wanted = (["soma_joinid", "dataset_id", "tissue", "cell_type", "disease", "sex", "is_primary_data"]
                      if kind == "cells" else ["soma_joinid", "feature_id", "feature_name", "feature_length"])
        columns = [column for column in wanted if column in frame.schema.names]
        domain = frame.non_empty_domain()[0]
        maximum_joinid = domain[1] if domain[1] is not None else -1
        end = min(end, maximum_joinid)
        terms = [f"{key} == {_literal(value)}" for key, value in filters.items() if value is not None]
        rows = []
        if start <= end:
            read = frame.read(coords=(slice(start, end),), column_names=columns,
                              value_filter=" and ".join(terms) or None, result_order="row-major")
            for table in read:
                rows.extend(table.slice(0, limit + 1 - len(rows)).to_pylist())
                if len(rows) > limit:
                    break
        selected = rows[:limit]
        next_joinid = selected[-1]["soma_joinid"] if len(rows) > limit else max(after_joinid, end)
    return {"source_url": SOURCE, "census_version": release, "version_description": description,
            "organism": organism if kind != "datasets" else None, "results": selected,
            "limit": limit, "scan_start": start, "scan_end": end, "next_after_joinid": next_joinid,
            "truncated": len(rows) > limit, "has_more": len(rows) > limit or end < maximum_joinid,
            "note": "Only this coordinate window was searched; an empty window does not mean no matches exist. Continue with next_after_joinid."}


async def _scan_async(kind: str, organism: str, version: str, limit: int,
                       after_joinid: int, scan_size: int, filters: dict) -> dict:
    _organism(organism)
    _version(version)
    bounded(limit)
    bounded(after_joinid, 10_000_000_000, "after_joinid", -1)
    bounded(scan_size, 10000, "scan_size")
    for value in filters.values():
        if value is not None:
            _literal(value)
    return await asyncio.to_thread(_scan, kind, organism, version, limit, after_joinid, scan_size, filters)


@mcp.tool()
async def cellxgene_versions(limit: int = 20, offset: int = 0) -> dict:
    """List available Census versions and their release descriptions."""
    bounded(limit)
    bounded(offset, 10000, "offset", 0)
    def run():
        versions = _sdk().get_census_version_directory()
        return local_page([{"version": key, **value} for key, value in versions.items()],
                          limit, offset, source_url=SOURCE)
    return await asyncio.to_thread(run)


@mcp.tool()
async def cellxgene_datasets(version: str = "stable", limit: int = 20,
                             after_joinid: int = -1, scan_size: int = 1000) -> dict:
    """List datasets within a bounded join-ID window; follow next_after_joinid to continue."""
    return await _scan_async("datasets", "homo_sapiens", version, limit, after_joinid, scan_size, {})


@mcp.tool()
async def cellxgene_cells(organism: str = "homo_sapiens", tissue: str | None = None,
                          cell_type: str | None = None, disease: str | None = None,
                          dataset_id: str | None = None, version: str = "stable", limit: int = 20,
                          after_joinid: int = -1, scan_size: int = 1000) -> dict:
    """Filter cell metadata by exact labels within a bounded coordinate window.

    Cell soma_joinid values are specific to the returned Census version.
    """
    return await _scan_async("cells", organism, version, limit, after_joinid, scan_size,
                             {"tissue": tissue, "cell_type": cell_type, "disease": disease, "dataset_id": dataset_id})


@mcp.tool()
async def cellxgene_genes(organism: str = "homo_sapiens", gene_id: str | None = None,
                          version: str = "stable", limit: int = 20,
                          after_joinid: int = -1, scan_size: int = 1000) -> dict:
    """Read gene metadata, optionally matching an exact feature ID, within a coordinate window."""
    if gene_id is not None:
        identifier(gene_id)
    return await _scan_async("genes", organism, version, limit, after_joinid, scan_size, {"feature_id": gene_id})


@mcp.tool()
async def cellxgene_expression(cell_ids: list[int], gene_ids: list[str], version: str,
                               organism: str = "homo_sapiens") -> dict:
    """Read raw counts for explicit cell soma_joinid values and feature IDs.

    Use the exact dated Census version returned by cellxgene_cells. At most 100 cells
    and 100 genes are allowed. Matrix rows/columns correspond to returned cells/genes.
    """
    identifier(version, r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "dated Census version")
    _organism(organism)
    if not cell_ids or len(cell_ids) > 100:
        raise ValueError("cell_ids must contain 1-100 soma_joinid values")
    cells = list(dict.fromkeys(bounded(value, 10_000_000_000, "cell ID", 0) for value in cell_ids))
    genes = list(dict.fromkeys(identifier(value) for value in identifiers(gene_ids, 100)))
    def run():
        sdk = _sdk()
        release, description = _resolved(sdk, version)
        with sdk.open_soma(census_version=release) as census:
            adata = sdk.get_anndata(census, organism=organism, obs_coords=cells,
                                   var_value_filter=f"feature_id in {json.dumps(genes)}", X_name="raw",
                                   obs_column_names=["soma_joinid", "dataset_id"],
                                   var_column_names=["soma_joinid", "feature_id", "feature_name"])
            if adata.n_obs > len(cells) or adata.n_vars > len(genes):
                raise ValueError("Census returned an unexpected matrix shape")
            matrix = adata.X.toarray() if hasattr(adata.X, "toarray") else adata.X
            obs = json.loads(adata.obs.to_json(orient="records"))
            var = json.loads(adata.var.to_json(orient="records"))
            return {"source_url": SOURCE, "census_version": release, "version_description": description,
                    "organism": organism, "layer": "raw", "cells": obs, "genes": var,
                    "matrix": matrix.tolist(),
                    "missing_cell_ids": sorted(set(cells) - {r["soma_joinid"] for r in obs}),
                    "missing_gene_ids": sorted(set(genes) - {r["feature_id"] for r in var})}
    return await asyncio.to_thread(run)


@mcp.tool()
async def cellxgene_dataset_url(dataset_id: str, version: str = "stable") -> dict:
    """Return the official source H5AD URI without downloading the dataset."""
    dataset_id = identifier(dataset_id.lower(), r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "dataset UUID")
    _version(version)
    def run():
        sdk = _sdk()
        release, description = _resolved(sdk, version)
        locator = sdk.get_source_h5ad_uri(dataset_id, census_version=release)
        return {"source_url": SOURCE, "dataset_id": dataset_id, "census_version": release,
                "version_description": description,
                "h5ad_uri": locator["uri"], "locator": locator}
    return await asyncio.to_thread(run)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
