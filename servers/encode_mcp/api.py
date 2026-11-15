"""ENCODE Portal experiments, files, biosample types and antibody targets.

Upstream quirks and caveats:
- The ENCODE Portal API (https://www.encodeproject.org) is public JSON REST,
  no key required; every request must send ``Accept: application/json`` and a
  ``format=json`` parameter or the portal returns HTML.
- Responses can be very large (a bare search is hundreds of KB), so every
  search carries an explicit ``limit`` and responses are byte-bounded.
- The search endpoint does NOT support offset paging (``start`` is rejected
  with HTTP 404), so result pages are sliced locally from a bounded fetch and
  truncation is reported explicitly.
- ENCODE data is made available under the CC0 public-domain dedication for
  most released data; ENCODE asks users to cite the portal and respect the
  terms at https://www.encodeproject.org/about/data-use-policy/. No files are
  downloaded here, only URLs are returned.
"""
from __future__ import annotations

from typing import Any

from common.api import choice, local_page, page
from common.http import identifier, request, text

BASE = "https://www.encodeproject.org"
HEADERS = {"Accept": "application/json"}
SEARCH_MAX_BYTES = 2_000_000
DETAIL_MAX_BYTES = 6_000_000
MAX_FETCH = 500
STATUSES = {"released", "revoked", "archived", "in progress", "submitted", "all"}
ACCESSION = r"ENCSR[A-Z0-9]{6}"
FILE_ACCESSION = r"ENCFF[A-Z0-9]{6}"


def _experiment_id(value: str) -> str:
    return identifier(value.upper(), ACCESSION, "experiment accession")


def _url(path: str | None) -> str | None:
    if path is None:
        return None
    return BASE + path if path.startswith("/") else path


async def _get(path: str, params: dict[str, Any] | None = None,
               max_bytes: int = SEARCH_MAX_BYTES) -> tuple[dict[str, Any], dict]:
    query = {"format": "json", **(params or {})}
    query = {key: value for key, value in query.items() if value is not None}
    response = await request("GET", f"{BASE}{path}", params=query, headers=HEADERS,
                             max_bytes=max_bytes)
    return response.json(), {"source_url": str(response.url)}


def _hits(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    return payload.get("@graph") or [], int(payload.get("total") or 0)


def _experiment_summary(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession": hit.get("accession"),
        "assay_title": hit.get("assay_title"),
        "biosample_summary": hit.get("biosample_summary"),
        "status": hit.get("status"),
        "url": _url(hit.get("@id")),
    }


def _file_row(file: dict[str, Any]) -> dict[str, Any]:
    return {
        "accession": file.get("accession"),
        "file_format": file.get("file_format"),
        "output_type": file.get("output_type"),
        "file_size": file.get("file_size"),
        "md5sum": file.get("md5sum"),
        "href": _url(file.get("href")),
        "url": _url(file.get("@id")),
        "status": file.get("status"),
    }


def _file_counts(files: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for file in files:
        key = file.get("file_format") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


async def encode_search(query: str | None = None, assay: str | None = None,
                        biosample: str | None = None, target: str | None = None,
                        organism: str | None = None, status: str = "released",
                        limit: int = 20, offset: int = 0) -> dict:
    """Search ENCODE experiments with optional assay, biosample, target and organism filters.

    At least one of query, assay, biosample, target or organism is required.
    `query` is a free-text portal search term; `assay` matches assay_title
    exactly (e.g. "total RNA-seq"); `biosample` matches
    biosample_ontology.term_name (e.g. "GM12878"); `target` matches the
    target label (e.g. "CTCF"); `organism` matches the scientific name
    (e.g. "Homo sapiens"). Pagination is LOCAL: ENCODE search does not accept
    an offset/start parameter, so a single bounded fetch of offset+limit rows
    (capped at 500) is sliced here and truncation is flagged. result_count is
    the upstream total for the filter combination.
    """
    filters = [value for value in (query, assay, biosample, target, organism) if value is not None]
    if not filters:
        raise ValueError("at least one of query, assay, biosample, target or organism is required")
    offset = page(limit, offset)["offset"]
    rows_wanted = page(limit, offset)["limit"] + offset
    if rows_wanted > MAX_FETCH:
        raise ValueError(f"offset+limit must not exceed {MAX_FETCH}; lower the offset")
    status = choice(status, STATUSES, "status")
    params: dict[str, Any] = {"type": "Experiment", "limit": rows_wanted,
                              "status": status}
    if query:
        params["searchterm"] = text(query, "query", 200)
    if assay:
        params["assay_title"] = text(assay, "assay", 200)
    if biosample:
        params["biosample_ontology.term_name"] = text(biosample, "biosample", 200)
    if target:
        params["target.label"] = identifier(target, r"[A-Za-z0-9][A-Za-z0-9_.()-]*", "target")
    if organism:
        params["organism.scientific_name"] = text(organism, "organism", 200)
    payload, source = await _get("/search/", params)
    hits, total = _hits(payload)
    return local_page([_experiment_summary(hit) for hit in hits], limit, offset,
                      **source, result_count=total)


async def encode_experiment(accession: str) -> dict:
    """Retrieve one ENCODE experiment's detail by accession (e.g. ENCSR000AEI).

    Returns description, assay, biosample and organism, targets, replicate
    counts, controlled_by references and file counts by format. Accessions
    must match ENCSR[A-Z0-9]{6}.
    """
    accession = _experiment_id(accession)
    payload, source = await _get(f"/experiments/{accession}/", max_bytes=DETAIL_MAX_BYTES)
    replicates = payload.get("replicates") or []
    organism = None
    for replicate in replicates:
        found = (((replicate.get("library") or {}).get("biosample") or {})
                 .get("organism") or {}).get("scientific_name")
        if found:
            organism = found
            break
    return {
        **source,
        "accession": payload.get("accession"),
        "url": _url(payload.get("@id")),
        "status": payload.get("status"),
        "assay_title": payload.get("assay_title"),
        "description": payload.get("description"),
        "biosample_summary": payload.get("biosample_summary"),
        "biosample_term": (payload.get("biosample_ontology") or {}).get("term_name"),
        "organism": organism,
        "targets": sorted({target.get("label") for target in payload.get("targets") or []
                           if target.get("label")}),
        "replicate_counts": {"biological": payload.get("bio_replicate_count"),
                             "technical": payload.get("tech_replicate_count")},
        "controlled_by": [_url(item) for item in payload.get("controlled_by") or []]
        if isinstance(payload.get("controlled_by"), list) else payload.get("controlled_by"),
        "references": sorted({item.get("identifier") or _url(item.get("@id"))
                              for item in payload.get("references") or []}),
        "file_counts": _file_counts(payload.get("files") or []),
    }


async def encode_files(accession: str, file_type: str | None = None,
                       limit: int = 20, offset: int = 0) -> dict:
    """List the files of one ENCODE experiment by accession, optionally by format.

    Returns each file's accession, format, size, download href URL and md5sum
    when present. URLs only - no file data is downloaded. `file_type` filters
    case-insensitively on the file format (e.g. "fastq", "bigWig"). Paging is
    LOCAL over the files embedded in the experiment detail.
    """
    accession = _experiment_id(accession)
    needle = None
    if file_type is not None:
        needle = text(file_type, "file_type", 100).lower()
    payload, source = await _get(f"/experiments/{accession}/", max_bytes=DETAIL_MAX_BYTES)
    rows = [_file_row(file) for file in payload.get("files") or []
            if needle is None or needle == (file.get("file_format") or "").lower()]
    return local_page(rows, limit, offset, **source, accession=accession,
                      url=_url(payload.get("@id")), file_type=file_type)


async def encode_biosamples(term: str, limit: int = 20, offset: int = 0) -> dict:
    """Search ENCODE biosample types by term name substring, e.g. "GM12878" or "liver".

    Returns term_name, classification, @id URL and status per hit. Pagination
    is LOCAL (ENCODE search does not accept an offset parameter).
    """
    term = text(term, "term", 200)
    payload, source = await _get("/search/", {"type": "BiosampleType",
                                              "term_name": term, "limit": MAX_FETCH})
    hits, total = _hits(payload)
    rows = [{"term_name": hit.get("term_name"),
             "classification": hit.get("classification"),
             "status": hit.get("status"),
             "url": _url(hit.get("@id"))} for hit in hits]
    return local_page(rows, limit, offset, **source, term=term, result_count=total)


async def encode_target(label: str) -> dict:
    """Look up ENCODE antibody targets by label, e.g. "CTCF" or "H3K4me3".

    Returns the matching targets with organism, investigated-as roles and
    @id URLs, suitable for use with encode_search(target=...).
    """
    label = identifier(label, r"[A-Za-z0-9][A-Za-z0-9_.()-]*", "target label")
    payload, source = await _get("/search/", {"type": "Target", "label": label,
                                              "limit": MAX_FETCH})
    hits, total = _hits(payload)
    rows = [{"label": hit.get("label"),
             "organism": ((hit.get("organism") or {}).get("scientific_name")),
             "investigated_as": hit.get("investigated_as") or [],
             "status": hit.get("status"),
             "url": _url(hit.get("@id"))} for hit in hits]
    return {**source, "label": label, "results": rows, "total": total}


TOOLS = (
    encode_search,
    encode_experiment,
    encode_files,
    encode_biosamples,
    encode_target,
)


RESOURCES = ()
