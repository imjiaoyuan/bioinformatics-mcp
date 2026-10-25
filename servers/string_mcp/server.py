from __future__ import annotations
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("string")
BASE = "https://string-db.org/api"

async def _get(endpoint: str, params: dict) -> list[dict]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{BASE}/json/{endpoint}", params=params); r.raise_for_status()
        return r.json()

@mcp.tool()
async def string_resolve(proteins: list[str], species: int = 9606) -> list[dict]:
    """Resolve gene/protein names to STRING identifiers."""
    if not proteins or len(proteins) > 100: raise ValueError("proteins must contain 1-100 names")
    return await _get("get_string_ids", {"identifiers": "%0d".join(proteins), "species": species})

@mcp.tool()
async def string_interactions(proteins: list[str], species: int = 9606, required_score: int = 400, limit: int = 100) -> list[dict]:
    """Get protein-protein interaction edges from STRING."""
    if not proteins or len(proteins) > 100: raise ValueError("proteins must contain 1-100 names")
    required_score = max(0, min(required_score, 1000)); limit = max(1, min(limit, 1000))
    return await _get("network", {"identifiers": "%0d".join(proteins), "species": species,
                                  "required_score": required_score, "limit": limit})

@mcp.tool()
async def string_enrichment(proteins: list[str], species: int = 9606) -> list[dict]:
    """Run GO/ pathway functional enrichment for a protein list."""
    if not proteins or len(proteins) > 2000: raise ValueError("proteins must contain 1-2000 names")
    return await _get("enrichment", {"identifiers": "%0d".join(proteins), "species": species})

def main() -> None: mcp.run()
if __name__ == "__main__": main()
