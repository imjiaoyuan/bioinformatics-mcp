"""MCP server exposing safe, structured NCBI Entrez operations."""
from __future__ import annotations

import json
import os
import time
import re
from html.parser import HTMLParser
from collections import OrderedDict
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urljoin

from common.http import bounded, identifier, request, text

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ALLOWED_DATABASES = {
    "pubmed", "pmc", "gene", "protein", "nuccore", "nucleotide", "sra",
    "assembly", "bioproject", "biosample", "clinvar", "omim", "taxonomy",
    "gds", "geoprofiles",
}
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_last_request = 0.0

mcp = FastMCP("ncbi")


def _config() -> tuple[str, str, str | None]:
    email = os.getenv("NCBI_EMAIL")
    tool = os.getenv("NCBI_TOOL", "ncbi-mcp")
    api_key = os.getenv("NCBI_API_KEY")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    return email, tool, api_key


async def _request(endpoint: str, params: dict[str, Any], *, ttl: int = 300) -> Any:
    global _last_request
    email, tool, api_key = _config()
    params = {**params, "email": email, "tool": tool, "retmode": "json"}
    if api_key:
        params["api_key"] = api_key
    key = endpoint + "?" + urlencode(sorted((k, str(v)) for k, v in params.items()))
    now = time.monotonic()
    if key in _cache and now - _cache[key][0] < ttl:
        return _cache[key][1]
    # Stay below the unauthenticated NCBI limit; API-key users can still opt in.
    delay = 0.11 if api_key else 0.35
    wait = delay - (now - _last_request)
    if wait > 0:
        import asyncio
        await asyncio.sleep(wait)
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        response = await client.get(f"{BASE_URL}/{endpoint}", params=params)
    _last_request = time.monotonic()
    if response.status_code == 429:
        raise RuntimeError("NCBI rate limit reached; retry later or configure NCBI_API_KEY")
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    _cache[key] = (time.monotonic(), data)
    _cache.move_to_end(key)
    while len(_cache) > 256:
        _cache.popitem(last=False)
    return data


def _db(database: str) -> str:
    database = database.lower().strip()
    if database not in ALLOWED_DATABASES:
        raise ValueError(f"Unsupported database {database!r}; choose from {sorted(ALLOWED_DATABASES)}")
    return database


@mcp.tool()
async def ncbi_search(database: str, query: str, max_results: int = 20) -> dict[str, Any]:
    """Search an NCBI Entrez database using its query syntax and return IDs."""
    database = _db(database)
    max_results = max(1, min(max_results, 1000))
    data = await _request("esearch.fcgi", {
        "db": database, "term": query, "retmax": max_results, "usehistory": "n",
    })
    result = data.get("esearchresult", {})
    return {"database": database, "query": query, "count": int(result.get("count", 0)),
            "ids": result.get("idlist", []), "translation": result.get("querytranslation")}


@mcp.tool()
async def ncbi_summary(database: str, ids: list[str]) -> dict[str, Any]:
    """Return compact metadata for up to 200 IDs from an NCBI database."""
    database = _db(database)
    if not ids or len(ids) > 200:
        raise ValueError("ids must contain between 1 and 200 identifiers")
    data = await _request("esummary.fcgi", {"db": database, "id": ",".join(ids)})
    return {"database": database, "result": data.get("result", {})}


@mcp.tool()
async def ncbi_fetch(database: str, ids: list[str], format: str = "json") -> dict[str, Any]:
    """Fetch records. Use json/xml for metadata, fasta for sequence records."""
    database = _db(database)
    format = format.lower()
    if format not in {"json", "xml", "fasta", "gb", "gbwithparts"}:
        raise ValueError("format must be json, xml, fasta, gb, or gbwithparts")
    if not ids or len(ids) > 100:
        raise ValueError("ids must contain between 1 and 100 identifiers")
    params = {"db": database, "id": ",".join(ids), "rettype": format if format != "json" else "docsum", "retmode": format if format in {"xml", "json"} else "text"}
    # efetch often returns text, so bypass the JSON helper for non-JSON formats.
    if format == "json":
        return {"database": database, "records": await _request("efetch.fcgi", params)}
    email, tool, api_key = _config()
    params.update(email=email, tool=tool)
    if api_key: params["api_key"] = api_key
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.get(f"{BASE_URL}/efetch.fcgi", params=params)
    response.raise_for_status()
    return {"database": database, "format": format, "content": response.text}


@mcp.tool()
async def ncbi_link(database: str, ids: list[str], target_database: str) -> dict[str, Any]:
    """Find related records in another Entrez database."""
    database, target_database = _db(database), _db(target_database)
    if not ids or len(ids) > 200:
        raise ValueError("ids must contain between 1 and 200 identifiers")
    data = await _request("elink.fcgi", {"db": target_database, "dbfrom": database, "id": ",".join(ids)})
    return {"database": database, "target_database": target_database, "result": data.get("linksets", [])}


@mcp.tool()
async def pubmed_search(
    query: str,
    max_results: int = 20,
    min_date: str | None = None,
    max_date: str | None = None,
    sort: str = "relevance",
    include_summaries: bool = True,
) -> dict[str, Any]:
    """Search PubMed and optionally return citation metadata.

    Dates use YYYY/MM/DD, YYYY/MM, or YYYY format. The query may use normal
    PubMed syntax, for example ``TP53[Title/Abstract] AND review[pt]``.
    """
    max_results = max(1, min(max_results, 200))
    sort = sort if sort in {"relevance", "pub date", "first author", "journal name"} else "relevance"
    params: dict[str, Any] = {
        "db": "pubmed", "term": query, "retmax": max_results,
        "sort": sort, "usehistory": "n",
    }
    if min_date:
        params.update({"mindate": min_date, "datetype": "pdat"})
    if max_date:
        params.update({"maxdate": max_date, "datetype": "pdat"})
    data = await _request("esearch.fcgi", params)
    result = data.get("esearchresult", {})
    ids = result.get("idlist", [])
    response: dict[str, Any] = {
        "query": query, "count": int(result.get("count", 0)), "ids": ids,
        "query_translation": result.get("querytranslation"),
    }
    if include_summaries and ids:
        summary = await ncbi_summary("pubmed", ids)
        response["articles"] = summary["result"]
    return response


@mcp.tool()
async def pubmed_citations(pmids: list[str], include_abstracts: bool = False) -> dict[str, Any]:
    """Fetch citation metadata for PMIDs, optionally including XML abstracts."""
    if not pmids or len(pmids) > 100:
        raise ValueError("pmids must contain between 1 and 100 PMIDs")
    summary = await ncbi_summary("pubmed", pmids)
    response: dict[str, Any] = {"pmids": pmids, "articles": summary["result"]}
    if include_abstracts:
        response["abstract_xml"] = (await ncbi_fetch("pubmed", pmids, "xml"))["content"]
    return response


@mcp.tool()
async def geo_search(query: str, limit: int = 20) -> dict[str, Any]:
    """Search GEO studies/samples with Entrez syntax and return summary metadata."""
    query = text(query)
    bounded(limit)
    result = await ncbi_search("gds", query, limit)
    result["source_url"] = "https://www.ncbi.nlm.nih.gov/gds/?" + urlencode({"term": query})
    result["summaries"] = (await ncbi_summary("gds", result["ids"]))["result"] if result["ids"] else {}
    return result


def _geo_accession(accession: str) -> str:
    return identifier(accession.upper(), r"(?:GSE|GSM)[1-9][0-9]*", "GEO accession")


@mcp.tool()
async def geo_record(accession: str) -> dict[str, Any]:
    """Read GSE/GSM SOFT metadata, including sample characteristics and supplement links."""
    accession = _geo_accession(accession)
    response = await request("GET", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi",
                             params={"acc": accession, "targ": "self", "form": "text", "view": "full"})
    metadata: dict[str, list[str]] = {}
    for line in response.text.splitlines():
        if line.startswith("!") and " = " in line:
            key, value = line[1:].split(" = ", 1)
            metadata.setdefault(key, []).append(value)
    if not metadata:
        raise ValueError(f"No GEO SOFT metadata returned for {accession}")
    return {"accession": accession, "metadata": metadata,
            "source_url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"}


class _DirectoryLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)


@mcp.tool()
async def geo_files(accession: str, limit: int = 30) -> dict[str, Any]:
    """List actual GEO series matrices/supplements or sample supplements; do not download them."""
    accession = _geo_accession(accession)
    bounded(limit)
    kind = "series" if accession.startswith("GSE") else "samples"
    group = re.sub(r"[0-9]{1,3}$", "nnn", accession)
    base = f"https://ftp.ncbi.nlm.nih.gov/geo/{kind}/{group}/{accession}/"
    directories = [base + "suppl/"]
    if kind == "series":
        directories.insert(0, base + "matrix/")
    files: list[str] = []
    for directory in directories:
        try:
            response = await request("GET", directory)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        parser = _DirectoryLinks()
        parser.feed(response.text)
        for href in parser.links:
            url = urljoin(directory, href)
            if url.startswith(directory) and not url.endswith("/") and "?" not in url and url not in files:
                files.append(url)
    return {"accession": accession, "files": files[:limit], "returned": min(len(files), limit),
            "truncated": len(files) > limit, "source_url": base}


@mcp.resource("ncbi://databases")
def databases() -> str:
    """List databases supported by this server."""
    return json.dumps(sorted(ALLOWED_DATABASES))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
