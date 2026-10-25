from __future__ import annotations
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pdb")
SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
CORE = "https://data.rcsb.org/rest/v1/core"

@mcp.tool()
async def pdb_search(query: str, max_results: int = 20) -> dict:
    """Search RCSB PDB by text, gene, protein, ligand, or PDB query syntax."""
    max_results = max(1, min(max_results, 100))
    payload = {"query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
               "return_type": "entry", "request_options": {"paginate": {"start": 0, "rows": max_results}}}
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(SEARCH, json=payload); r.raise_for_status(); data = r.json()
    return {"query": query, "total_count": data.get("total_count", 0),
            "entries": [{"pdb_id": x.get("identifier"), "score": x.get("score")} for x in data.get("result_set", [])]}

@mcp.tool()
async def pdb_entry(pdb_id: str) -> dict:
    """Get structured metadata for a PDB entry (for example 4HHB)."""
    pdb_id = pdb_id.strip().upper()
    if len(pdb_id) != 4: raise ValueError("pdb_id must be a four-character PDB identifier")
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.get(f"{CORE}/entry/{pdb_id}"); r.raise_for_status()
    return r.json()

@mcp.tool()
async def pdb_download_url(pdb_id: str, format: str = "cif") -> dict:
    """Return an official download URL for PDB/mmCIF/structure files."""
    pdb_id = pdb_id.strip().lower()
    if len(pdb_id) != 4: raise ValueError("pdb_id must be a four-character PDB identifier")
    if format not in {"cif", "pdb", "bcif"}: raise ValueError("format must be cif, pdb, or bcif")
    suffix = "cif" if format == "cif" else ("pdb" if format == "pdb" else "bcif")
    return {"pdb_id": pdb_id.upper(), "format": format, "url": f"https://files.rcsb.org/download/{pdb_id}.{suffix}"}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
