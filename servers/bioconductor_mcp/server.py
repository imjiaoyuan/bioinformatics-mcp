from __future__ import annotations
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("bioconductor")
DEFAULT_VERSION = os.getenv("BIOC_VERSION", "3.21")

def _base(version: str) -> str:
    if not version.replace(".", "").isdigit():
        raise ValueError("version must look like 3.21")
    return f"https://bioconductor.org/packages/json/{version}"

async def _json(url: str) -> object:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(url); r.raise_for_status(); return r.json()

@mcp.tool()
async def bioconductor_search(query: str, version: str = DEFAULT_VERSION, limit: int = 20) -> list[dict]:
    """Search Bioconductor software and annotation packages by name, title, or description."""
    limit = max(1, min(limit, 100)); q = query.lower()
    result: list[dict] = []
    for repo in ("bioc", "data/annotation", "data/experiment"):
        try: data = await _json(f"{_base(version)}/{repo}/packages.json")
        except httpx.HTTPStatusError: continue
        if isinstance(data, dict): data = list(data.values())
        for item in data if isinstance(data, list) else []:
            text = " ".join(str(item.get(k, "")) for k in ("Package", "Title", "Description", "biocViews")).lower()
            if q in text:
                result.append({k: item.get(k) for k in ("Package", "Version", "Title", "Maintainer", "biocViews")})
                if len(result) >= limit: return result
    return result

@mcp.tool()
async def bioconductor_package(package: str, version: str = DEFAULT_VERSION) -> dict:
    """Get metadata for a named Bioconductor package across standard repositories."""
    for repo in ("bioc", "data/annotation", "data/experiment"):
        try: data = await _json(f"{_base(version)}/{repo}/packages/{package}.json")
        except httpx.HTTPStatusError: continue
        if isinstance(data, dict):
            data["repository"] = repo
            data["release"] = version
            data["web_url"] = f"https://bioconductor.org/packages/{version}/{repo}/html/{package}.html"
            return data
    raise ValueError(f"Package {package!r} was not found in Bioconductor {version}")

@mcp.tool()
async def bioconductor_install(package: str, version: str = DEFAULT_VERSION) -> dict:
    """Generate reproducible R installation commands for a Bioconductor package."""
    await bioconductor_package(package, version)
    return {"r": f'if (!requireNamespace("BiocManager")) install.packages("BiocManager")\nBiocManager::install("{package}", version = "{version}")',
            "release": version, "package": package}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
