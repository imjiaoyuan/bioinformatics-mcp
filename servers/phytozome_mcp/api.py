"""Phytozome plant genome comparative resource (JGI Genome Portal).

Requires a free JGI Genome Portal account registered at
https://phytozome-next.jgi.doe.gov/ and provided through the environment as
``JGI_EMAIL`` and ``JGI_PASSWORD``; the Phytozome v3 API authenticates with
HTTP Basic credentials. Credentials are only used to build the Authorization
header and are never logged: shared HTTP logging redacts authorization
material, and response URLs are sanitized.

Endpoint assumptions (live verification without credentials is impossible, so
parsers are defensive): the documented v3 endpoints are ``GET /pz/v3/organism``
(organism catalog, best requested with ``compressed=false``), ``GET
/pz/v3/gene/{gene_id}`` (gene detail) and ``GET /pz/v3/gene/search`` (keyword
or taxon-scoped gene search). The exact JSON envelopes may differ between
revisions, so list extraction accepts a bare list or a dict wrapper with
typical keys (``data``, ``results``, ``organisms``, ``genes``, ``hits``,
``features``, ``response``) and unknown shapes are passed through under a
``raw`` key instead of raising. No files are downloaded; download tools return
URL strings only, and actual file access requires JGI login in a browser or
authorized client.
"""
from __future__ import annotations

import base64
import os
from typing import Annotated, Any

from pydantic import Field

from common.api import local_page, page
from common.http import bounded, identifier, request, safe_url, text

BASE = "https://phytozome-next.jgi.doe.gov/pz/v3"
PORTAL = "https://phytozome-next.jgi.doe.gov"
ORGANISM_PATTERN = r"[A-Za-z][A-Za-z0-9_.]+"
LIST_KEYS = ("data", "results", "organisms", "genes", "hits", "features", "response", "records")


def _credential(name: str, maximum: int) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(
            f"{name} is required; Phytozome v3 requires a free JGI Genome Portal account "
            "(register at https://phytozome-next.jgi.doe.gov/) and its credentials in "
            "JGI_EMAIL and JGI_PASSWORD"
        )
    return text(value, name, maximum)


def _auth_headers() -> dict[str, str]:
    email = _credential("JGI_EMAIL", 200)
    password = _credential("JGI_PASSWORD", 200)
    token = base64.b64encode(f"{email}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


async def _get(path: str, params: dict | None = None) -> tuple[Any, str]:
    try:
        response = await request("GET", f"{BASE}/{path}", params=params,
                                 headers=_auth_headers(), max_bytes=50_000_000)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 401:
            raise ValueError(
                "Invalid JGI credentials: Phytozome rejected the JGI_EMAIL/JGI_PASSWORD pair; "
                "check the account at https://phytozome-next.jgi.doe.gov/"
            ) from None
        raise
    return response.json(), safe_url(response.url)


def _rows(data: Any) -> list[dict] | None:
    """Extract a list of records from a typical envelope; None when unknown."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in LIST_KEYS:
            value = data.get(key)
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                return [row for row in value if isinstance(row, dict)]
    return None


def _passthrough(data: Any, source_url: str, **metadata: Any) -> dict:
    return {"source_url": source_url, **metadata, "raw": data}


def _field(row: dict, *names: str) -> Any:
    """First non-empty value among tolerant field namings, else None."""
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _match(row: dict, needle: str) -> bool:
    haystack = " ".join(str(value) for value in row.values() if isinstance(value, (str, int))).lower()
    return needle in haystack


async def phytozome_organisms(query: str = "",
                              limit: Annotated[int, Field(ge=1, le=100)] = 20,
                              offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """List Phytozome organisms, filtered locally by scientific name or keyword.

    Fetches the organism catalog once per call (``compressed=false``) and
    applies case-insensitive substring filtering and pagination locally when
    ``query`` is given; the ``query`` may be a scientific name, common name or
    free keyword matched against catalog fields.
    """
    needle = ""
    if query:
        needle = text(query, "query", 150).lower()
    page(limit, offset)
    data, source_url = await _get("organism", {"compressed": "false"})
    rows = _rows(data)
    if rows is None:
        return _passthrough(data, source_url, endpoint="organism")
    if needle:
        rows = [row for row in rows if _match(row, needle)]
    return local_page([{key: value for key, value in row.items()} for row in rows],
                      limit, offset, source_url=source_url, query=query or None)


async def phytozome_organism(organism_id: str) -> dict:
    """Retrieve metadata for one organism by its Phytozome id or organismName.

    ``organism_id`` may be the numeric/short organism id or the ``organismName``
    (e.g. ``Athaliana``); unknown shapes are passed through under ``raw``.
    """
    value = identifier(organism_id, ORGANISM_PATTERN, "organism_id")
    data, source_url = await _get(f"organism/{value}")
    rows = _rows(data)
    if rows:
        return {"source_url": source_url, "organism_id": value, **rows[0]}
    if isinstance(data, dict):
        return {"source_url": source_url, "organism_id": value, **data}
    return _passthrough(data, source_url, organism_id=value)


async def phytozome_gene(gene_id: str) -> dict:
    """Retrieve gene metadata by its Phytozome gene/transcript identifier.

    Returns transcript id, genomic location, synonyms and GO terms when the
    upstream record provides them; unknown record shapes are passed through
    under ``raw`` rather than raising.
    """
    value = identifier(gene_id, r"[A-Za-z0-9_.:-]+", "gene_id")
    data, source_url = await _get(f"gene/{value}")
    if not isinstance(data, dict):
        return _passthrough(data, source_url, gene_id=value)
    record = {
        "gene_id": value,
        "transcript_id": _field(data, "transcript_id", "transcriptId", "transcript"),
        "location": _field(data, "location", "chr", "chromosome") if data else None,
        "chromosome": _field(data, "chromosome", "chr", "chrName"),
        "start": _field(data, "start", "startIdx", "start_pos"),
        "end": _field(data, "end", "endIdx", "end_pos"),
        "strand": _field(data, "strand", "orientation"),
        "synonyms": data.get("synonyms") or data.get("alias") or data.get("aliases"),
        "go_terms": data.get("go_terms") or data.get("GO") or data.get("go"),
        "gene_name": _field(data, "geneName", "gene_name", "name", "displayName"),
        "organism": _field(data, "organism", "organismName", "scientific_name"),
    }
    record = {key: value for key, value in record.items() if value is not None}
    record.update({"source_url": source_url, "raw": data})
    return record


async def phytozome_gene_search(keyword: str, organism: str | None = None,
                                limit: Annotated[int, Field(ge=1, le=100)] = 20,
                                offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Search Phytozome genes by keyword, optionally scoped to one organism.

    ``keyword`` is matched by the upstream gene search service (gene names,
    descriptions or annotations depending on the release); ``organism`` is an
    optional Phytozome organism id or organismName. Pagination is applied
    locally over the bounded upstream response.
    """
    needle = text(keyword, "keyword", 150)
    paging = page(limit, offset)
    params: dict[str, Any] = {"keyword": needle}
    if organism is not None:
        params["organism"] = identifier(organism, ORGANISM_PATTERN, "organism")
    data, source_url = await _get("gene/search", params)
    rows = _rows(data)
    if rows is None:
        return _passthrough(data, source_url, keyword=needle)
    start = paging["offset"]
    return {"source_url": source_url, "keyword": needle, **paging,
            "results": rows[start:start + paging["limit"]],
            "total": len(rows), "truncated": start + paging["limit"] < len(rows),
            "pagination": "local"}


async def phytozome_download_info(organism: str) -> dict:
    """Return download portal URLs for one organism; performs no downloads.

    Returns the Phytozome info page URL (``/info/{organism}``) where genome
    files are listed; actual file downloads require logging in with a JGI
    Genome Portal account in the browser or an authorized client, so only URL
    strings are returned here.
    """
    value = identifier(organism, ORGANISM_PATTERN, "organism")
    return {
        "organism": value,
        "info_url": f"{PORTAL}/info/{value}",
        "directory_note": (
            "Genome files are listed on the info page; downloads require JGI Genome "
            "Portal login and are not performed by this tool."
        ),
        "source_url": f"{PORTAL}/info/{value}",
    }


TOOLS = (
    phytozome_organisms,
    phytozome_organism,
    phytozome_gene,
    phytozome_gene_search,
    phytozome_download_info,
)


def _endpoints() -> dict:
    """Describe the Phytozome v3 endpoints and parameter constraints."""
    return {"upstream": BASE,
            "endpoints": {"phytozome_organisms": "GET /organism?compressed=false (catalog filtered and paginated locally)",
                          "phytozome_organism": "GET /organism/{organism_id}",
                          "phytozome_gene": "GET /gene/{gene_id}",
                          "phytozome_gene_search": "GET /gene/search?keyword[&organism] (paginated locally)",
                          "phytozome_download_info": "info page URL only; downloads require JGI login"},
            "constraints": {"limit": "1-100", "offset": "0-1000000",
                            "organism": "Phytozome organismId or organismName (e.g. Athaliana)"},
            "requires": "JGI_EMAIL and JGI_PASSWORD environment credentials"}


RESOURCES = (
    ("phytozome://endpoints", _endpoints),
)
