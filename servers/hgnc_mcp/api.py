"""HGNC gene nomenclature: entries by ID or symbol, search, alias lookup.

Upstream: the HGNC REST service at https://rest.genenames.org, a live Solr
front end. Every request must send ``Accept: application/json`` (text or a
missing header can yield non-JSON responses); results arrive as a Solr
``response`` envelope with ``numFound``/``start``/``docs``. The search
endpoint ignores ``rows``/``start`` query parameters, so pagination is
performed locally over the returned docs. No files are written to disk.
"""
from __future__ import annotations

from typing import Any

from common.api import local_page
from common.api import json_response
from common.http import identifier, text

BASE_URL = "https://rest.genenames.org"
HEADERS = {"Accept": "application/json"}
MAX_DOCS = 100

_DOC_FIELDS = (
    "hgnc_id", "symbol", "name", "status", "locus_group", "locus_type",
    "location", "alias_symbol", "prev_symbol", "alias_name", "prev_name",
    "ensembl_gene_id", "entrez_id", "uniprot_ids", "vega_id", "refseq_accession",
    "date_approved_reserved", "date_modified", "date_name_changed",
)


async def _fetch_json(path: str) -> tuple[dict[str, Any], str]:
    body, source = await json_response(f"{BASE_URL}{path}", headers=HEADERS, ttl=600)
    return body.get("response") or {}, source["source_url"]


def _doc(entry: dict[str, Any]) -> dict[str, Any]:
    return {field: entry[field] for field in _DOC_FIELDS if field in entry}


def _hits(envelope: dict[str, Any], url: str) -> list[dict[str, Any]]:
    docs = envelope.get("docs") or []
    if not docs:
        raise ValueError("No matching HGNC entry; check the identifier or symbol")
    return [_doc(doc) for doc in docs]


def _query(value: str) -> str:
    """Pass Lucene syntax through, but reject characters that would corrupt the request path.

    httpx percent-encodes backslashes, so pre-escaping Lucene specials with
    ``\\`` is not viable; the upstream endpoint accepts raw fielded syntax
    (verified: ``status:Approved AND name:"..."``). Unsafe URL characters are
    rejected outright.
    """
    value = text(value, "query", 150)
    if any(character in value for character in "?#%&+;\\<>"):
        raise ValueError("query must not contain ? # % & + ; \\ < > characters")
    return value


async def hgnc_entry(hgnc_id: str) -> dict:
    """Retrieve one HGNC gene entry by its numeric HGNC ID, e.g. 1097 or HGNC:1097.

    Returns the current symbol, name, status, locus, aliases, external
    database references (Ensembl, NCBI Gene, UniProt, VEGA) and record dates.
    """
    match = identifier(hgnc_id.replace("HGNC:", "", 1) if hgnc_id.upper().startswith("HGNC:")
                       else hgnc_id, r"[0-9]{1,7}", "HGNC ID (numeric, optionally 'HGNC:' prefixed)")
    envelope, url = await _fetch_json(f"/fetch/hgnc_id/HGNC:{match}")
    return {"source_url": url, **_hits(envelope, url)[0]}


async def hgnc_symbol(symbol: str) -> dict:
    """Retrieve one HGNC gene entry by its current approved symbol, e.g. TP53.

    The lookup is case-insensitive upstream; unknown symbols raise.
    """
    clean = identifier(symbol, r"[A-Za-z0-9@#._-]{1,30}", "gene symbol")
    envelope, url = await _fetch_json(f"/fetch/symbol/{clean}")
    return {"source_url": url, **_hits(envelope, url)[0]}


async def hgnc_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search HGNC records with a query string or a fielded Lucene query.

    Fielded terms use Lucene syntax, e.g. ``status:Approved AND symbol:TP53``
    or ``locus_type:"RNA, microRNA"``. ``limit``/``offset`` paginate locally;
    ``total`` reflects the upstream ``numFound``. Broad queries may transfer
    large payloads upstream before local slicing.
    """
    query = _query(query)
    envelope, url = await _fetch_json(f"/search/{query}")
    total = int(envelope.get("numFound") or 0)
    rows = [_doc(doc) for doc in envelope.get("docs") or []][:MAX_DOCS]
    page = local_page(rows, limit, offset, source_url=url, query=query,
                      docs_fetched=len(rows), pagination="local (upstream ignores rows/start; docs capped at 100)")
    page["total"] = total
    return page


async def hgnc_aliases(symbol: str, limit: int = 20, offset: int = 0) -> dict:
    """Collect alias_symbol, prev_symbol, alias_name and prev_name for one symbol.

    Normalizes the four alias fields into a single sorted list for
    symbol-disambiguation; unknown symbols raise.
    """
    entry = await hgnc_symbol(symbol)
    aliases = sorted({alias for field in ("alias_symbol", "prev_symbol", "alias_name", "prev_name")
                      for alias in entry.get(field) or []})
    page = local_page(aliases, limit, offset, source_url=entry["source_url"],
                      hgnc_id=entry["hgnc_id"], symbol=entry["symbol"])
    page["total"] = len(aliases)
    return page


TOOLS = (
    hgnc_entry,
    hgnc_symbol,
    hgnc_search,
    hgnc_aliases,
)


def _fields() -> dict:
    """List the HGNC doc fields returned by this server and its fetch endpoints."""
    return {"upstream": BASE_URL,
            "endpoints": ["/fetch/hgnc_id/HGNC:{id}", "/fetch/symbol/{symbol}", "/search/{query}"],
            "returned_doc_fields": list(_DOC_FIELDS),
            "pagination": "upstream ignores rows/start; results are paginated locally (docs capped at 100)"}


RESOURCES = (
    ("hgnc://fields", _fields),
)
