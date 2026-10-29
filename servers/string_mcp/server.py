from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

from common.http import bounded

mcp = FastMCP("string")
BASE = "https://string-db.org/api"


def _species(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000_000:
        raise ValueError("species must be a NCBI taxonomy ID between 1 and 10000000")
    return value


def _proteins(values: list[str], maximum: int) -> list[str]:
    if not values or len(values) > maximum:
        raise ValueError(f"proteins must contain 1-{maximum} names")
    for value in values:
        if not value or len(value) > 100 or any(c.isspace() or c in ",\r" for c in value):
            raise ValueError("protein names must be 1-100 characters without commas or whitespace")
    return values


async def _get(endpoint: str, params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{BASE}/json/{endpoint}", params=params); r.raise_for_status()
        return r.json()


@mcp.tool()
async def string_resolve(proteins: list[str], species: int = 9606) -> list[dict]:
    """Resolve gene/protein names to STRING identifiers."""
    return await _get("get_string_ids", {"identifiers": "\r".join(_proteins(proteins, 100)), "species": _species(species)})


@mcp.tool()
async def string_interactions(proteins: list[str], species: int = 9606, required_score: int = 400, limit: int = 100) -> list[dict]:
    """Get protein-protein interaction edges from STRING, returning at most limit edges.

    The limit caps returned edges locally; it does not expand the input protein set.
    """
    if isinstance(required_score, bool) or not isinstance(required_score, int) or not 0 <= required_score <= 1000:
        raise ValueError("required_score must be between 0 and 1000")
    params = {"identifiers": "\r".join(_proteins(proteins, 100)), "species": _species(species),
              "required_score": required_score}
    return (await _get("network", params))[:bounded(limit, 1000)]


@mcp.tool()
async def string_enrichment(proteins: list[str], species: int = 9606) -> list[dict]:
    """Run GO/pathway functional enrichment for a protein list."""
    return await _get("enrichment", {"identifiers": "\r".join(_proteins(proteins, 2000)), "species": _species(species)})


def main() -> None: mcp.run()
if __name__ == "__main__": main()
