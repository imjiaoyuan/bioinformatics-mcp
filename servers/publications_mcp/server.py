from __future__ import annotations
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("publications")
CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
EUROPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
PUBLISHERS = {"cell": "Cell", "nature": "Nature", "pnas": "Proceedings of the National Academy of Sciences", "science": "Science"}

async def _get(url: str, params: dict | None = None) -> dict:
    headers = {"User-Agent": "bioinformatics-mcp/0.1 (mailto:" + os.getenv("NCBI_EMAIL", "") + ")"}
    async with httpx.AsyncClient(timeout=60, headers=headers, follow_redirects=True) as c:
        r = await c.get(url, params=params); r.raise_for_status(); return r.json()

def _clean(item: dict) -> dict:
    return {"title": (item.get("title") or [None])[0], "doi": item.get("DOI"),
            "published": item.get("published-print") or item.get("published-online") or item.get("issued"),
            "authors": [{"given": a.get("given"), "family": a.get("family")} for a in item.get("author", [])],
            "journal": (item.get("container-title") or [None])[0], "publisher": item.get("publisher"),
            "url": item.get("URL"), "type": item.get("type")}

@mcp.tool()
async def publication_search(query: str, publisher: str | None = None, year_from: int | None = None,
                             year_to: int | None = None, limit: int = 20) -> dict:
    """Search Cell, Nature, PNAS, Science, or all scholarly publications."""
    limit = max(1, min(limit, 100)); params = {"query": query, "rows": limit, "select": "DOI,title,author,published,container-title,publisher,URL,type"}
    filters = []
    if year_from: filters.append(f"from-pub-date:{year_from}-01-01")
    if year_to: filters.append(f"until-pub-date:{year_to}-12-31")
    if filters: params["filter"] = ",".join(filters)
    data = await _get(f"{CROSSREF}/works", params); items = data.get("message", {}).get("items", [])
    if publisher in PUBLISHERS:
        needle = PUBLISHERS[publisher].lower()
        items = [x for x in items if needle in (x.get("publisher", "") + " " + " ".join(x.get("container-title", []))).lower()]
    return {"query": query, "publisher": publisher, "total": len(items), "articles": [_clean(x) for x in items]}

@mcp.tool()
async def publication_by_doi(doi: str) -> dict:
    """Get authoritative Crossref metadata for a DOI."""
    doi = doi.strip().removeprefix("https://doi.org/")
    return _clean((await _get(f"{CROSSREF}/works/{doi}"))["message"])

@mcp.tool()
async def publication_related(doi: str, limit: int = 20) -> list[dict]:
    """Find related works using OpenAlex concepts and citation graph."""
    doi = doi.strip().removeprefix("https://doi.org/")
    data = await _get(f"{OPENALEX}/works/https://doi.org/{doi}")
    ids = data.get("related_works", [])[:max(1, min(limit, 50))]
    results = []
    for wid in ids:
        try:
            x = await _get(f"{OPENALEX}/{wid}"); results.append({"title": x.get("title"), "doi": x.get("doi"), "year": x.get("publication_year"), "url": x.get("id")})
        except httpx.HTTPError: continue
    return results

@mcp.tool()
async def publication_europepmc(query: str, limit: int = 20) -> dict:
    """Search Europe PMC for abstracts, PMIDs and open-access full-text links."""
    data = await _get(f"{EUROPMC}/search", {"query": query, "format": "json", "pageSize": max(1, min(limit, 100))})
    return {"hit_count": data.get("hitCount", 0), "articles": data.get("resultList", {}).get("result", [])}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
