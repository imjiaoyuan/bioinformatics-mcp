"""WikiPathways community pathway catalogue: organisms, pathway search and listings.

WikiPathways now distributes its catalogue as static JSON snapshots
(https://www.wikipathways.org/json); the classic SOAP/REST webservice is gone,
so search and filtering run locally over the cached snapshot (1 hour TTL).
GPML model files are distributed separately and are not fetched here.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, text

JSON_BASE = "https://www.wikipathways.org/json"

_CACHE_TTL = 3600


def _species_key(value: str) -> str:
    return value.replace("_", " ").strip().lower()


async def _pathway_rows() -> tuple[list, dict]:
    data, source = await json_response(f"{JSON_BASE}/findPathwaysByText.json", ttl=_CACHE_TTL)
    return data.get("pathwayInfo", []), source


async def _organisms() -> tuple[list, dict]:
    data, source = await json_response(f"{JSON_BASE}/listPathways.json", ttl=_CACHE_TTL)
    return data.get("organisms", []), source


def _species(species: str | None) -> str | None:
    if species is None:
        return None
    value = text(species, "species", 100)
    identifier(value, r"[A-Za-z][A-Za-z0-9_. -]*", "species")
    return value


async def wikipathways_organisms() -> dict:
    """List WikiPathways organisms with their pathway counts (cached snapshot)."""
    organisms, source = await _organisms()
    results = [{"common": organism.get("common"), "latin": organism.get("latin"),
                "two_letter_code": organism.get("two-letter-code"),
                "pathway_count": len(organism.get("pathways", []))}
               for organism in organisms]
    return {**source, "results": results, "total": len(results)}


async def wikipathways_search(query: str, species: str | None = None,
                              limit: Annotated[int, Field(ge=1, le=100)] = 20,
                              offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search pathway names and IDs locally over the cached catalogue snapshot.

    Matching is case-insensitive on name and pathway ID; ``species`` filters with
    a case-insensitive contains-match (e.g. ``Homo sapiens``).
    """
    query = text(query, "query", 200)
    species_filter = _species(species)
    rows, source = await _pathway_rows()
    needle = query.lower()
    filtered = [row for row in rows
                if (needle in row.get("name", "").lower() or needle in row.get("id", "").lower())
                and (species_filter is None
                     or _species_key(species_filter) in _species_key(row.get("species", "")))]
    return {**source, **local_page(filtered, limit, offset), "query": query,
            "species": species_filter}


async def wikipathways_species_pathways(species: str,
                                        limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                        offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List all catalogue pathways of one species (e.g. ``Homo sapiens`` or ``Homo_sapiens``)."""
    species_filter = _species(species)
    needle = species_filter.replace("_", " ").lower()
    organisms, source = await _organisms()
    rows = [pathway for organism in organisms
            if _species_key(organism.get("latin", "")) == needle
            or organism.get("common", "").lower() == needle.lower()
            for pathway in organism.get("pathways", [])]
    if not rows:
        raise ValueError(f"No WikiPathways organism matches {species_filter}; try wikipathways_organisms")
    return {**source, **local_page(rows, limit, offset), "species": species_filter,
            "total": len(rows)}


TOOLS = (
    wikipathways_organisms,
    wikipathways_search,
    wikipathways_species_pathways,
)
