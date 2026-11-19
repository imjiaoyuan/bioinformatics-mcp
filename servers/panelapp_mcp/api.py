"""PanelApp gene panels: expert-reviewed gene-disease clinical validity (Genomics England).

Queries the public PanelApp REST API
(https://panelapp.genomicsengland.co.uk/api/v1). Green (level 4) panels are
used in NHS diagnostic practice; confidence levels: 1=red ... 4=green.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import bounded, identifier, text

BASE = "https://panelapp.genomicsengland.co.uk/api/v1"

# PageNumberPagination with explicit page_size; upstream pages are 1-indexed.
_PAGE_SIZE = 100


def _panel_id(value: str) -> str:
    return identifier(value, r"[0-9]+", "PanelApp panel id")


def _confidence_levels(value: str) -> str:
    levels = [identifier(level, r"[1-4]", "confidence level") for level in value.split(",")]
    return "&".join(sorted(set(levels)))


async def _get(path: str, params: dict | None = None) -> tuple[dict, dict]:
    data, source = await json_response(f"{BASE}/{path}", params)
    if isinstance(data, dict) and data.get("detail") == "Not found.":
        raise ValueError(f"PanelApp returned no match for {path}")
    return data, source


async def panelapp_panels(name: str | None = None,
                          page_index: Annotated[int, Field(ge=1, le=500)] = 1,
                          page_size: Annotated[int, Field(ge=1, le=_PAGE_SIZE)] = 50) -> dict:
    """List gene panels with versions and disease groups; optionally filter by name locally.

    ``name`` filters case-insensitively over the fetched page (upstream has no name filter).
    """
    data, source = await _get("panels/", {"page": bounded(page_index, 500, "page_index", 1),
                                          "page_size": bounded(page_size, _PAGE_SIZE)})
    rows = data.get("results", [])
    if name is not None:
        needle = text(name, "name", 200).lower()
        rows = [row for row in rows if needle in row.get("name", "").lower()]
    results = [{"id": row.get("id"), "name": row.get("name"), "version": row.get("version"),
                "status": row.get("status"), "disease_group": row.get("disease_group"),
                "relevant_disorders": row.get("relevant_disorders"), "types": row.get("types")}
               for row in rows]
    return {**source, "results": results, "total": data.get("count", len(results)),
            "page": page_index, "limit": page_size, "pagination": "upstream page index"}


async def panelapp_panel(panel_id: str) -> dict:
    """Retrieve one gene panel's metadata, version and constituent entities."""
    data, source = await _get(f"panels/{_panel_id(panel_id)}/")
    return {**source, "id": data.get("id"), "name": data.get("name"), "version": data.get("version"),
            "status": data.get("status"), "disease_group": data.get("disease_group"),
            "relevant_disorders": data.get("relevant_disorders"), "types": data.get("types"),
            "stats": data.get("stats")}


async def panelapp_panel_genes(panel_id: str, confidence_levels: str = "3,4",
                               limit: Annotated[int, Field(ge=1, le=100)] = 50,
                               offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List genes in one panel with confidence levels, inheritance and phenotypes.

    ``confidence_levels`` is a comma list of 1 (red) to 4 (green); default 3,4.
    """
    levels = _confidence_levels(confidence_levels)
    paging = page(limit, offset)
    data, source = await _get(f"panels/{_panel_id(panel_id)}/genes/", {"confidence_levels": levels})
    rows = [{key: row.get(key) for key in ("entity_name", "entity_type", "confidence_level",
                                           "mode_of_inheritance", "mode_of_pathogenicity",
                                           "phenotypes", "publications", "evidence", "tags")}
            | {"gene_symbol": (row.get("gene_data") or {}).get("gene_symbol"),
               "hgnc_id": (row.get("gene_data") or {}).get("hgnc_id")}
            for row in data.get("results", [])]
    return {**source, **local_page(rows, paging["limit"], paging["offset"]),
            "panel_id": _panel_id(panel_id), "confidence_levels": confidence_levels}


async def panelapp_gene(gene_symbol: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                        offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Find every panel that includes one gene, with its confidence level per panel."""
    symbol = identifier(gene_symbol.upper(), r"[A-Za-z][A-Za-z0-9]*", "HGNC gene symbol")
    paging = page(limit, offset)
    data, source = await _get(f"genes/{symbol}/", {"page_size": paging["limit"],
                                                   "page": paging["offset"] // paging["limit"] + 1})
    rows = [{"panel": row.get("panel"), "confidence_level": row.get("confidence_level"),
             "mode_of_inheritance": row.get("mode_of_inheritance"),
             "phenotypes": row.get("phenotypes"),
             "gene_symbol": (row.get("gene_data") or {}).get("gene_symbol")}
            for row in data.get("results", [])]
    return {**source, "results": rows, "total": data.get("count", len(rows)), "gene_symbol": symbol}


TOOLS = (
    panelapp_panels,
    panelapp_panel,
    panelapp_panel_genes,
    panelapp_gene,
)
