from __future__ import annotations
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP

from common.http import bounded, identifier, text

mcp = FastMCP("publications")
CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
EUROPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
PUBLISHERS = {"cell": "Cell", "nature": "Nature", "pnas": "Proceedings of the National Academy of Sciences", "science": "Science"}


def _doi(value: str) -> str:
    value = text(value, "doi", 512).removeprefix("https://doi.org/").removeprefix("http://doi.org/").removeprefix("doi:")
    if not re.fullmatch(r"10\.[0-9]{4,9}/\S+", value):
        raise ValueError("doi must look like 10.1234/example-suffix")
    return value


def _year(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1400 <= value <= 3000:
        raise ValueError(f"{name} must be a four-digit year between 1400 and 3000")
    return value


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
    query = text(query)
    if publisher is not None and publisher not in PUBLISHERS:
        raise ValueError(f"publisher must be one of {', '.join(sorted(PUBLISHERS))} or null")
    limit = bounded(limit, 100)
    params = {"query": query, "rows": limit, "select": "DOI,title,author,published,container-title,publisher,URL,type"}
    filters = []
    if year_from is not None: filters.append(f"from-pub-date:{_year(year_from, 'year_from')}-01-01")
    if year_to is not None: filters.append(f"until-pub-date:{_year(year_to, 'year_to')}-12-31")
    if filters: params["filter"] = ",".join(filters)
    data = await _get(f"{CROSSREF}/works", params)
    message = data.get("message", {})
    items = message.get("items", [])
    filtered = items
    if publisher is not None:
        needle = PUBLISHERS[publisher].lower()
        filtered = [x for x in items if needle in (x.get("publisher", "") + " " + " ".join(x.get("container-title", []))).lower()]
    return {"query": query, "publisher": publisher, "total_matches": message.get("total-results"),
            "total": len(filtered), "filtered": publisher is not None and len(filtered) < len(items),
            "articles": [_clean(x) for x in filtered]}

@mcp.tool()
async def publication_by_doi(doi: str) -> dict:
    """Get authoritative Crossref metadata for a DOI."""
    return _clean((await _get(f"{CROSSREF}/works/{_doi(doi)}"))["message"])

@mcp.tool()
async def publication_related(doi: str, limit: int = 20) -> list[dict]:
    """Find related works using OpenAlex concepts and citation graph."""
    doi = _doi(doi)
    limit = bounded(limit, 50)
    data = await _get(f"{OPENALEX}/works/https://doi.org/{doi}")
    ids = data.get("related_works", [])[:limit]
    results = []
    for wid in ids:
        try:
            x = await _get(f"{OPENALEX}/{wid}"); results.append({"title": x.get("title"), "doi": x.get("doi"), "year": x.get("publication_year"), "url": x.get("id")})
        except httpx.HTTPError: continue
    return results

@mcp.tool()
async def publication_europepmc(query: str, limit: int = 20) -> dict:
    """Search Europe PMC for abstracts, PMIDs and open-access full-text links."""
    return {"hit_count": (data := await _get(f"{EUROPMC}/search", {"query": text(query), "format": "json", "pageSize": bounded(limit, 100)})).get("hitCount", 0),
            "articles": data.get("resultList", {}).get("result", [])}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
