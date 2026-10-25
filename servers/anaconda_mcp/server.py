from __future__ import annotations
import httpx
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("anaconda")
BASE = "https://api.anaconda.org"
async def _get(path: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.get(BASE + path, params=params); r.raise_for_status(); return r.json()
@mcp.tool()
async def anaconda_search(query: str, limit: int = 20) -> list[dict]:
    """Search public Anaconda packages and channels."""
    data = await _get("/search", {"name": query})
    return data[:max(1, min(limit, 100))] if isinstance(data, list) else data
@mcp.tool()
async def anaconda_package(owner: str, package: str) -> dict:
    """Get package metadata, versions, platforms, and download counts."""
    return await _get(f"/package/{owner}/{package}")
@mcp.tool()
async def anaconda_files(owner: str, package: str, version: str | None = None) -> list[dict]:
    """List downloadable conda packages for an Anaconda package."""
    data = await anaconda_package(owner, package)
    files = data.get("files", []) if isinstance(data, dict) else []
    return [x for x in files if not version or x.get("version") == version]
def main() -> None: mcp.run()
if __name__ == "__main__": main()
