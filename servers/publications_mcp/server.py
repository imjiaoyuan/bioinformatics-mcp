from __future__ import annotations
import asyncio
import os
import re
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP

from common.http import bounded, identifier, request, text

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
    contact = os.getenv("NCBI_EMAIL")
    agent = "bioinformatics-mcp/0.1" + (f" (mailto:{contact})" if contact else "")
    return (await request("GET", url, params=params, headers={"User-Agent": agent})).json()


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
async def publication_related(doi: str, limit: int = 20) -> dict:
    """Find related OpenAlex works; distinguish empty results from partial/failed retrievals.

    Returns articles, errors, partial, and truncation metadata. Individual failures
    do not discard successful records. No abstract/full-text similarity is inferred.
    """
    doi = _doi(doi)
    limit = bounded(limit, 50)
    data = await _get(f"{OPENALEX}/works/https://doi.org/{doi}")
    related = data.get("related_works")
    if not isinstance(related, list) or any(not isinstance(wid, str) for wid in related):
        raise ValueError("OpenAlex returned no valid related_works list")
    related = list(dict.fromkeys(related))
    ids = related[:limit]

    async def fetch_work(value: str) -> dict:
        if not isinstance(value, str):
            raise ValueError("Invalid OpenAlex work ID")
        parsed = urlsplit(value)
        if parsed.scheme and (parsed.scheme != "https" or parsed.netloc not in {"openalex.org", "api.openalex.org"}):
            raise ValueError("Invalid OpenAlex work URL")
        wid = identifier(parsed.path.rstrip("/").rsplit("/", 1)[-1], r"W[1-9][0-9]*", "OpenAlex work ID")
        x = await _get(f"{OPENALEX}/works/{wid}")
        return {"title": x.get("title"), "doi": x.get("doi"), "year": x.get("publication_year"),
                "url": x.get("id") or f"https://openalex.org/{wid}"}

    records = await asyncio.gather(*(fetch_work(wid) for wid in ids), return_exceptions=True)
    articles, errors = [], []
    for wid, result in zip(ids, records):
        if isinstance(result, Exception):
            error = {"id": wid, "type": type(result).__name__, "message": "Related work retrieval failed"}
            if isinstance(result, httpx.HTTPStatusError):
                error["status_code"] = result.response.status_code
            errors.append(error)
        else:
            articles.append(result)
    return {"doi": doi, "articles": articles, "returned": len(articles), "total_related": len(related),
            "errors": errors, "partial": bool(errors), "all_requests_failed": bool(ids) and len(errors) == len(ids),
            "truncated": len(related) > len(ids), "source_url": f"{OPENALEX}/works/https://doi.org/{doi}"}

@mcp.tool()
async def publication_europepmc(query: str, limit: int = 20) -> dict:
    """Search Europe PMC for abstracts, PMIDs and open-access full-text links."""
    return {"hit_count": (data := await _get(f"{EUROPMC}/search", {"query": text(query), "format": "json", "pageSize": bounded(limit, 100)})).get("hitCount", 0),
            "articles": data.get("resultList", {}).get("result", [])}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
