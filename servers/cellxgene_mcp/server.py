"""CELLxGENE queries: public REST baseline with optional SDK-backed deep Census access.

Every tool works in any Python >= 3.10 using plain HTTP against the CELLxGENE
Census release directory and the Discover curation API. Tools that need
cell-level Census reads additionally use the optional cellxgene-census SDK when
it is installed; without the SDK they raise a clear RuntimeError explaining the
Python 3.10-3.13 requirement, and the REST tools above remain fully usable.
"""
from __future__ import annotations

import asyncio
import importlib
import json

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response, local_page
from common.http import bounded, identifier, identifiers, text

mcp = FastMCP("cellxgene")
SOURCE = "https://cellxgene.cziscience.com/census"
RELEASE_URL = "https://census.cellxgene.cziscience.com/cellxgene-census/v1/release.json"
DISCOVER_URL = "https://api.cellxgene.cziscience.com/curation/v1/datasets"
COLLECTIONS_URL = "https://api.cellxgene.cziscience.com/curation/v1/collections"
H5AD_BUCKET_URL = "https://cellxgene-census-public-us-west-2.s3.us-west-2.amazonaws.com/cell-census"
SDK_HINT = ("The optional cellxgene-census SDK is required for cell-level Census queries; "
            "install it from the repository root with Python 3.10-3.13: pip install -e '.[cellxgene]'")


def _sdk():
    try:
        return importlib.import_module("cellxgene_census")
    except ImportError as exc:
        raise RuntimeError("Optional CELLxGENE SDK is not installed. " + SDK_HINT) from exc


def _version(value: str) -> str:
    return identifier(value, r"(?:stable|latest|[0-9]{4}-[0-9]{2}-[0-9]{2})", "Census version")


def _organism(value: str) -> str:
    return choice(value, {"homo_sapiens", "mus_musculus"}, "organism")


async def _resolve(version: str) -> tuple[str, dict, dict]:
    """Map 'stable'/'latest'/dated version to (release_build, directory_entry, meta)."""
    version = _version(version)
    directory, meta = await json_response(RELEASE_URL, max_bytes=1_000_000)
    if version not in ("stable", "latest"):
        if version not in directory or not isinstance(directory[version], dict):
            raise ValueError(f"Unknown Census version; list versions with cellxgene_versions")
        entry = directory[version]
        return entry.get("release_build", version), entry, meta
    if not isinstance(directory.get(version), str):
        raise RuntimeError("Unexpected Census release directory format")
    dated = directory[version]
    if dated not in directory or not isinstance(directory[dated], dict):
        raise RuntimeError(f"Census release directory is missing entry for {dated}")
    return dated, directory[dated], meta


def _sdk_resolved(sdk, version: str) -> tuple[str, dict]:
    description = sdk.get_census_version_description(version)
    return description["release_build"], description


def _literal(value: str) -> str:
    # JSON string escaping is compatible with SOMA's string filter grammar.
    return json.dumps(text(value, "filter value", 200), ensure_ascii=True)


def _labels(values: list) -> list[str]:
    return sorted({item.get("label", "") for item in values if isinstance(item, dict)})


def _dataset_row(record: dict) -> dict:
    """Project a Discover record to bounded, useful metadata."""
    assets = [a for a in record.get("assets", []) if isinstance(a, dict)]
    return {
        "dataset_id": record.get("dataset_id"),
        "dataset_version_id": record.get("dataset_version_id"),
        "collection_id": record.get("collection_id"),
        "collection_name": record.get("collection_name"),
        "title": record.get("title"),
        "organism": _labels(record.get("organism", [])),
        "tissue": _labels(record.get("tissue", [])),
        "disease": _labels(record.get("disease", [])),
        "assay": _labels(record.get("assay", [])),
        "cell_count": record.get("cell_count"),
        "is_primary_data": record.get("is_primary_data"),
        "schema_version": record.get("schema_version"),
        "published_at": record.get("published_at"),
        "assets": [{"filetype": a.get("filetype"), "filesize": a.get("filesize"), "url": a.get("url")}
                   for a in assets],
        "explorer_url": record.get("explorer_url"),
    }


async def _discover() -> tuple[list[dict], dict]:
    payload, meta = await json_response(DISCOVER_URL, max_bytes=25_000_000)
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected Discover datasets format")
    return payload, meta


def _match(record: dict, terms: dict) -> bool:
    for key, expected in terms.items():
        if expected is None:
            continue
        if key == "query":
            haystack = " ".join(filter(None, [str(record.get(field, "")) for field in
                                              ("title", "collection_name")])).lower()
            if expected.lower() not in haystack:
                return False
        else:
            labels = _labels(record.get(key, []))
            if not any(expected.lower() == label.lower() for label in labels):
                return False
    return True


def _scan(kind: str, organism: str, version: str, limit: int, after_joinid: int,
          scan_size: int, filters: dict) -> dict:
    sdk = _sdk()
    release, description = _sdk_resolved(sdk, version)
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
    directory, meta = await json_response(RELEASE_URL, max_bytes=1_000_000)
    aliases = {key: value for key, value in directory.items() if isinstance(value, str)}
    rows = [{"version": key, **value} for key, value in directory.items() if isinstance(value, dict)]
    page = local_page(rows, limit, offset, source_url=meta["source_url"])
    page["aliases"] = aliases
    return page


@mcp.tool()
async def cellxgene_datasets(query: str | None = None, organism: str | None = None,
                             tissue: str | None = None, disease: str | None = None,
                             assay: str | None = None, collection_id: str | None = None,
                             dataset_id: str | None = None, limit: int = 20, offset: int = 0) -> dict:
    """Search curated CELLxGENE Discover datasets over the public REST API.

    Works without the optional SDK. Returns dataset metadata, cell counts and
    H5AD asset URLs; use cellxgene_cells for cell-level Census filters.
    """
    for value in (query, organism, tissue, disease, assay):
        if value is not None:
            text(value, "filter", 200)
    if collection_id is not None:
        identifier(collection_id, r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "collection UUID")
    if dataset_id is not None:
        identifier(dataset_id, r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "dataset UUID")
    bounded(limit)
    bounded(offset, 10000, "offset", 0)
    terms = {"query": query, "organism": organism, "tissue": tissue, "disease": disease, "assay": assay}
    if dataset_id is not None:
        rows, meta = await _discover()
        filtered = [r for r in rows if r.get("dataset_id") == dataset_id]
    elif collection_id is not None:
        payload, meta = await json_response(f"{COLLECTIONS_URL}/{collection_id}", max_bytes=8_000_000)
        filtered = payload.get("datasets", []) if isinstance(payload, dict) else []
    else:
        rows, meta = await _discover()
        filtered = [r for r in rows if _match(r, terms)]
    results = [_dataset_row(r) for r in filtered if isinstance(r, dict)]
    return local_page(results, limit, offset, source_url=meta["source_url"])


@mcp.tool()
async def cellxgene_cells(organism: str = "homo_sapiens", tissue: str | None = None,
                          cell_type: str | None = None, disease: str | None = None,
                          dataset_id: str | None = None, version: str = "stable", limit: int = 20,
                          after_joinid: int = -1, scan_size: int = 1000) -> dict:
    """Filter cell metadata by exact labels within a bounded coordinate window.

    Requires the optional CELLxGENE SDK (Python 3.10-3.13). Cell soma_joinid
    values are specific to the returned Census version.
    """
    return await _scan_async("cells", organism, version, limit, after_joinid, scan_size,
                             {"tissue": tissue, "cell_type": cell_type, "disease": disease, "dataset_id": dataset_id})


@mcp.tool()
async def cellxgene_genes(organism: str = "homo_sapiens", gene_id: str | None = None,
                          version: str = "stable", limit: int = 20,
                          after_joinid: int = -1, scan_size: int = 1000) -> dict:
    """Read gene metadata, optionally matching an exact feature ID, within a coordinate window.

    Requires the optional CELLxGENE SDK (Python 3.10-3.13).
    """
    if gene_id is not None:
        identifier(gene_id)
    return await _scan_async("genes", organism, version, limit, after_joinid, scan_size, {"feature_id": gene_id})


@mcp.tool()
async def cellxgene_expression(cell_ids: list[int], gene_ids: list[str], version: str,
                               organism: str = "homo_sapiens") -> dict:
    """Read raw counts for explicit cell soma_joinid values and feature IDs.

    Requires the optional CELLxGENE SDK (Python 3.10-3.13). Use the exact dated
    Census version returned by cellxgene_cells. At most 100 cells and 100 genes
    are allowed. Matrix rows/columns correspond to returned cells/genes.
    """
    identifier(version, r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "dated Census version")
    _organism(organism)
    if not cell_ids or len(cell_ids) > 100:
        raise ValueError("cell_ids must contain 1-100 soma_joinid values")
    cells = list(dict.fromkeys(bounded(value, 10_000_000_000, "cell ID", 0) for value in cell_ids))
    genes = list(dict.fromkeys(identifier(value) for value in identifiers(gene_ids, 100)))
    def run():
        sdk = _sdk()
        release, description = _sdk_resolved(sdk, version)
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
    release, entry, meta = await _resolve(version)
    base = entry.get("h5ads") if isinstance(entry, dict) else None
    if base is None or not isinstance(base.get("relative_uri"), str):
        raise RuntimeError("Census release directory lacks an h5ads locator")
    return {"source_url": SOURCE, "dataset_id": dataset_id, "census_version": release,
            "h5ad_uri": f"s3://cellxgene-census-public-us-west-2{base['relative_uri']}{dataset_id}.h5ad",
            "https_url": f"{H5AD_BUCKET_URL}/{base['relative_uri'].lstrip('/cell-census/')}{dataset_id}.h5ad",
            "release_entry": {k: entry[k] for k in ("release_build", "release_date", "flags") if k in entry},
            "source_urls": [RELEASE_URL, meta["source_url"]],
            "note": "Discover curation assets may instead be versioned by dataset_version_id; see cellxgene_datasets."}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
