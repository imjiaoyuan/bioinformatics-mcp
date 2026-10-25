from __future__ import annotations
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ensembl")
BASE = "https://rest.ensembl.org"

async def _get(path: str, params: dict | None = None) -> dict | list:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        r = await client.get(BASE + path, params={**(params or {}), "content-type": "application/json"})
        r.raise_for_status()
        return r.json()

@mcp.tool()
async def ensembl_lookup(identifier: str, expand: bool = False) -> dict:
    """Look up an Ensembl gene, transcript, variant, or other stable ID."""
    return await _get(f"/lookup/id/{identifier.strip()}", {"expand": 1 if expand else 0})

@mcp.tool()
async def ensembl_xrefs(identifier: str) -> list:
    """Find external database cross-references for an Ensembl identifier."""
    return await _get(f"/xrefs/id/{identifier.strip()}")

@mcp.tool()
async def ensembl_overlap(region: str, feature: str = "gene", species: str = "human") -> list:
    """Return Ensembl features overlapping a region such as  human:7:140424943-140624564."""
    if feature not in {"gene", "transcript", "cds", "exon", "variation", "regulatory"}:
        raise ValueError("unsupported feature")
    path = f"/overlap/region/{species}/{region.split(':', 1)[-1]}"
    return await _get(path, {"feature": feature})

def main() -> None: mcp.run()
if __name__ == "__main__": main()
