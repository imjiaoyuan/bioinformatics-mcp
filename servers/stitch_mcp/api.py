"""STITCH chemical-protein interaction network (STRING's chemistry sibling).

Mirrors the STRING REST API conventions at https://stitch.embl.de. STITCH
scores are confidence values between chemicals and proteins aggregated from
databases, literature and metabolic associations; cite STITCH in derived work.
"""
from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field

from common.http import bounded, request

BASE = "https://stitch.embl.de/api"


def _species(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000_000:
        raise ValueError("species must be a NCBI taxonomy ID between 1 and 10000000")
    return value


def _values(values: list[str], maximum: int) -> list[str]:
    if not values or len(values) > maximum:
        raise ValueError(f"identifiers must contain 1-{maximum} names")
    for value in values:
        if not value or len(value) > 100 or any(c.isspace() or c in ",\r" for c in value):
            raise ValueError("identifiers must be 1-100 characters without commas or whitespace")
    return values


async def _get(endpoint: str, params: dict) -> list[dict]:
    response = await request("GET", f"{BASE}/json/{endpoint}", params=params, timeout=60)
    return response.json()


async def stitch_resolve(proteins: list[str], species: Annotated[int, Field(ge=1, le=10_000_000)] = 9606) -> list[dict]:
    """Resolve gene/protein/chemical names to STITCH identifiers."""
    return await _get("get_string_ids", {"identifiers": "\r".join(_values(proteins, 100)),
                                         "species": _species(species)})


async def stitch_interactions(proteins: list[str], species: Annotated[int, Field(ge=1, le=10_000_000)] = 9606,
                              required_score: Annotated[int, Field(ge=0, le=1000)] = 400,
                              limit: Annotated[int, Field(ge=1, le=1000)] = 100) -> list[dict]:
    """Get chemical-protein and protein-protein interaction edges, capped at limit edges.

    ``required_score`` is the STITCH confidence on the 0-1000 scale (400 = medium).
    """
    if isinstance(required_score, bool) or not isinstance(required_score, int) or not 0 <= required_score <= 1000:
        raise ValueError("required_score must be between 0 and 1000")
    bounded(limit, 1000)
    params = {"identifiers": "\r".join(_values(proteins, 100)), "species": _species(species),
              "required_score": required_score}
    return (await _get("network", params))[:limit]


async def stitch_enrichment(proteins: list[str], species: Annotated[int, Field(ge=1, le=10_000_000)] = 9606) -> list[dict]:
    """Run functional enrichment for a chemical/protein list against STITCH pathways."""
    return await _get("enrichment", {"identifiers": "\r".join(_values(proteins, 2000)),
                                     "species": _species(species)})


TOOLS = (
    stitch_resolve,
    stitch_interactions,
    stitch_enrichment,
)


def constraints() -> str:
    """Describe STITCH endpoint constraints used by this server."""
    return json.dumps({
        "resource": "stitch://constraints",
        "species": "NCBI taxonomy ID between 1 and 10000000",
        "endpoints": {
            "stitch_resolve": {"max_identifiers": 100, "name_length": "1-100 chars, no commas/whitespace"},
            "stitch_interactions": {"max_identifiers": 100, "required_score": "0-1000",
                                    "limit": "1-1000 edges"},
            "stitch_enrichment": {"max_identifiers": 2000},
        },
    })


RESOURCES = (
    ("stitch://constraints", constraints),
)
