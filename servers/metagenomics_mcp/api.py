"""MG-RAST metagenome metadata and annotations via the public MG-RAST API.

Upstream caveats (verified 2026-11 against https://api.metagenomics.anl.gov):
- Anonymous access works for project/sample/metagenome lookups, but private or
  nonexistent objects return HTTP 401 with {"ERROR": "insufficient permissions"}
  while truly unknown identifiers return HTTP 404 with {"ERROR": "... does not
  exist"}; both are surfaced as explicit errors, never as empty results.
- The top-level /metagenome listing always reports total_count 0 anonymously,
  so only direct metagenome lookup is exposed.
- Annotation profiles use the streaming /annotation/sequence endpoint (the
  aggregated /matrix endpoint submits asynchronous jobs that stall anonymously),
  so the byte-bounded per-read dump is fetched once and paginated locally.
No files are downloaded; every response size is bounded.
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from common.api import bounded, choice, local_page, page
from common.http import identifier, request, safe_url, text

BASE = "https://api.metagenomics.anl.gov"
MAX_BYTES = 10_000_000

PROJECT_ID = re.compile(r"mgp[0-9]+")
METAGENOME_ID = re.compile(r"mgm[0-9]+(\.[0-9]+)?")
SAMPLE_ID = re.compile(r"mgs[0-9]+")

ORGANISM_SOURCES = {"RefSeq", "GenBank", "IMG", "SEED", "TrEMBL", "SwissProt",
                    "PATRIC", "KEGG", "eggNOG", "RDP", "Greengenes", "LSU", "SSU", "ITS"}
FUNCTION_SOURCES = {"Subsystems", "NOG", "COG", "KO"}


async def _get(path: str, params: dict | None = None, max_bytes: int = MAX_BYTES) -> tuple[Any, dict]:
    """Fetch JSON while mapping upstream error shapes to explicit errors."""
    try:
        response = await request("GET", f"{BASE}{path}", params=params, max_bytes=max_bytes)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise ValueError(f"MG-RAST resource does not exist: {path}") from None
        if status in {401, 403}:
            raise ValueError(f"MG-RAST resource is not publicly accessible: {path}") from None
        raise
    data = response.json()
    if isinstance(data, dict) and "ERROR" in data:
        raise ValueError(f"MG-RAST API error: {data['ERROR']}")
    return data, {"source_url": safe_url(response.url)}


def _project_id(value: str) -> str:
    return identifier(value.lower(), PROJECT_ID.pattern, "MG-RAST project ID (mgp...)")


def _metagenome_id(value: str) -> str:
    return identifier(value.lower(), METAGENOME_ID.pattern, "MG-RAST metagenome ID (mgm...)")


def _sample_id(value: str) -> str:
    return identifier(value.lower(), SAMPLE_ID.pattern, "MG-RAST sample ID (mgs...)")


async def mgrast_projects(pi: str | None = None, name: str | None = None,
                          limit: int = 20, offset: int = 0) -> dict:
    """List public MG-RAST projects, optionally filtered by PI or name keyword.

    Upstream prev/next links are preserved verbatim; paging is server-side.
    """
    params: dict[str, Any] = dict(page(limit, offset))
    for key, value in (("pi", pi), ("name", name)):
        if value is not None:
            params[key] = text(value, key, 150)
    data, meta = await _get("/project", params)
    return {**meta, "projects": data.get("data", []),
            "total_count": data.get("total_count"), "limit": data.get("limit"),
            "offset": data.get("offset"), "prev": data.get("prev"), "next": data.get("next")}


async def mgrast_project(project_id: str) -> dict:
    """Retrieve one public MG-RAST project by its mgp identifier.

    Returns status, PI, name and full metadata; unknown or private IDs raise.
    """
    data, meta = await _get(f"/project/{_project_id(project_id)}")
    return {**meta, **data}


async def mgrast_metagenome(metagenome_id: str) -> dict:
    """Retrieve MG-RAST metagenome metadata (pipeline, sample, library, project).

    The identifier may carry a version suffix, e.g. mgm4447943.3 or mgm4447943.
    """
    data, meta = await _get(f"/metagenome/{_metagenome_id(metagenome_id)}")
    return {**meta, **data}


async def mgrast_sample(sample_id: str) -> dict:
    """Retrieve MG-RAST sample metadata by its mgs identifier."""
    data, meta = await _get(f"/sample/{_sample_id(sample_id)}")
    return {**meta, **data}


async def mgrast_annotation(metagenome_id: str, annotation_type: str = "organism",
                            source: str = "RefSeq", evalue: int = 5,
                            limit: int = 20, offset: int = 0) -> dict:
    """Fetch per-read annotations (organism or function) for one metagenome.

    Uses the streaming MG-RAST annotation endpoint with an explicit e-value
    exponent cutoff (e.g. evalue=5 means e-5), bounds the response locally and
    paginates the parsed rows client-side. Large metagenomes may exceed the
    response bound; the error then asks to narrow the query.
    """
    metagenome_id = _metagenome_id(metagenome_id)
    annotation_type = choice(annotation_type, {"organism", "function"}, "annotation_type")
    sources = ORGANISM_SOURCES if annotation_type == "organism" else FUNCTION_SOURCES
    source = choice(source, sources, "source")
    evalue = bounded(evalue, 100, "evalue")
    params = {"id": metagenome_id, "type": annotation_type, "source": source, "evalue": evalue}
    try:
        response = await request("GET", f"{BASE}/annotation/sequence/{metagenome_id}",
                                 params=params, max_bytes=MAX_BYTES)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise ValueError(f"MG-RAST metagenome does not exist: {metagenome_id}") from None
        if status in {401, 403}:
            raise ValueError(f"MG-RAST metagenome is not publicly accessible: {metagenome_id}") from None
        raise
    body = response.text
    rows = []
    for line in body.splitlines():
        if not line.strip() or line.startswith("sequence id"):
            continue
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        rows.append({"id": fields[0], "md5": fields[1], "annotations": fields[3].split("; ")})
    return local_page(rows, limit, offset, source_url=safe_url(response.url),
                      metagenome_id=metagenome_id, annotation_type=annotation_type,
                      source=source, evalue=f"e-{evalue}")


TOOLS = (
    mgrast_projects,
    mgrast_project,
    mgrast_metagenome,
    mgrast_sample,
    mgrast_annotation,
)


RESOURCES = ()
