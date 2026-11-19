"""Open Tree of Life synthetic phylogeny: name resolution, node info and tree metadata.

Queries the public Open Tree of Life API v3 (https://tree.opentreeoflife.org,
api.opentreeoflife.org). The synthetic tree combines dozens of published
phylogenies; OTT taxon IDs can be mapped back to NCBI/GBIF/IRMNG.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response
from common.http import bounded, identifier, identifiers, text

BASE = "https://api.opentreeoflife.org/v3"


async def _post(path: str, body: dict) -> dict:
    data, source = await json_response(f"{BASE}/{path}", body=body)
    if not isinstance(data, dict):
        raise ValueError("Unexpected Open Tree response format")
    return {**source, **data}


def _names(values: list[str]) -> list[str]:
    names = identifiers(values, 50)
    for value in names:
        if len(value) < 2 or any(c in "|{}@;" for c in value):
            raise ValueError("names must be 2+ characters without |{}@; characters")
    return names


async def opentree_match_names(names: list[str], context: str = "All life") -> dict:
    """Resolve scientific names to Open Tree taxonomy (OTT) IDs via TNRS fuzzy matching.

    ``context`` narrows the search space (e.g. ``Animals``, ``Plants``, ``Fungi``).
    """
    body = {"names": _names(names), "context": text(context, "context", 60)}
    data = await _post("tnrs/match_names", body)
    results = []
    for row in data.get("results", []):
        matches = row.get("matches", [])
        best = matches[0] if matches else {}
        taxon = best.get("taxon", {})
        results.append({"search_string": best.get("search_string", row.get("name", "")),
                        "matched_name": best.get("matched_name"),
                        "ott_id": taxon.get("ott_id"), "is_synonym": best.get("is_synonym", False),
                        "score": best.get("score"), "tax_sources": taxon.get("tax_sources", [])})
    return {"unmatched_names": data.get("unmatched_names", []),
            "results": results, "total": len(results),
            "context": data.get("context", body["context"])}


async def opentree_node(ott_id: str) -> dict:
    """Retrieve one OTT node from the synthetic tree: taxonomy, rank and descendant tip count."""
    ott = identifier(str(ott_id), r"[0-9]+", "OTT id")
    data = await _post("tree_of_life/node_info", {"ott_id": int(ott)})
    taxon = data.get("taxon", {})
    return {"node_id": data.get("node_id"), "synth_id": data.get("synth_id"),
            "ott_id": taxon.get("ott_id"), "name": taxon.get("name"), "rank": taxon.get("rank"),
            "num_tips": data.get("num_tips"), "terminal": data.get("terminal"),
            "tax_sources": taxon.get("tax_sources", []),
            "supported_by": data.get("supported_by", [])}


async def opentree_about() -> dict:
    """Describe the current Open Tree synthetic tree build (version and source count)."""
    data = await _post("tree_of_life/about", {})
    keys = ("synth_id", "taxonomy_version", "num_source_tree_ids", "num_trees",
            "num_tips", "num_studies", "root_taxon_name", "generated_timestamp")
    return {key: data[key] for key in keys if key in data} | {
        "release_version": data.get("release_version")}


TOOLS = (
    opentree_match_names,
    opentree_node,
    opentree_about,
)
