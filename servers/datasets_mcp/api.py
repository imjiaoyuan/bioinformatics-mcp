"""NCBI Datasets v2 REST API: genome, gene and taxonomy metadata reports.

Upstream: https://api.ncbi.nlm.nih.gov/datasets/v2 (verified live paths only:
/genome/taxon/{taxon}/dataset_report, /genome/accession/{accession}/dataset_report,
/gene/taxon/{taxon}/dataset_report, /gene/symbol/{symbol}/taxon/{taxon}/dataset_report,
/gene/id/{gene_id}/dataset_report and /taxonomy/taxon/{taxon}/dataset_report).
Only metadata reports are returned; the JSONL download endpoints are out of scope,
so no files are fetched or written and sequence data is never returned.

Taxon arguments accept an NCBI taxid (numeric) or a scientific/common name string;
both forms are accepted upstream. The genome and gene listing endpoints paginate
upstream via page_size/page_token; whole-taxon gene listings are unbounded in
practice, so dataset_genes requires either a gene id or a symbol rather than
allowing whole-genome dumps.
"""
from __future__ import annotations

from typing import Any

import httpx

from common.api import choice
from common.http import bounded, get_json, identifier as valid_id

BASE = "https://api.ncbi.nlm.nih.gov/datasets/v2"
MAX_BYTES = 8_000_000
MAX_UPSTREAM_PAGES = 5  # bounds the page_token walk; page_size is <= 1000
_ASSEMBLY = r"GCF_\d+\.\d+|GCA_\d+\.\d+"
_TAXON = r"[0-9]+|[A-Za-z][A-Za-z0-9_.-]*(?:[ _][A-Za-z0-9_.-]+)*"
_SYMBOL = r"[A-Za-z0-9_.:-]+"


def _taxon(value: str) -> str:
    return valid_id(value.strip(), _TAXON, "taxon (taxid or scientific name)")


async def _reports(path: str, params: dict | None = None) -> tuple[list, dict[str, Any]]:
    data = await get_json(BASE + path, params)
    reports = data.get("reports") or []
    metadata = {key: data[key] for key in ("total_count", "next_page_token", "messages") if data.get(key) is not None}
    return reports, metadata


async def dataset_assemblies(taxon: str, source: str = "any", level: str = "any",
                             limit: int = 20, offset: int = 0) -> dict:
    """List genome assembly dataset reports for a taxon (taxid or name, e.g. 3702 or arabidopsis thaliana).

    Filters: source is any|refseq|genbank, level is any|complete|chromosome|
    scaffold|contig. Results are fetched via upstream page_size/page_token
    pagination (bounded walk) and sliced locally with limit/offset.
    """
    taxon = _taxon(taxon)
    bounded(limit, 200)
    bounded(offset, 100_000, "offset", minimum=0)
    params: dict[str, Any] = {"page_size": min(1000, offset + limit)}
    if source != "any":
        params["filters.assembly_source"] = choice(source, {"refseq", "genbank"}, "source")
    if level != "any":
        params["filters.assembly_level"] = choice(level.lower(),
                                                  {"complete", "chromosome", "scaffold", "contig"}, "level")
    path = f"/genome/taxon/{taxon}/dataset_report"
    reports: list = []
    total_count: int | None = None
    for _ in range(MAX_UPSTREAM_PAGES):
        page_reports, metadata = await _reports(path, params)
        reports.extend(page_reports)
        total_count = metadata.get("total_count", total_count)
        token = metadata.get("next_page_token")
        if not token or len(reports) >= offset + limit:
            break
        params["page_token"] = token
    rows = reports[offset:offset + limit]
    return {"taxon": taxon, "reports": rows, "limit": limit, "offset": offset,
            "total": len(rows), "total_count": total_count,
            "truncated": bool(metadata.get("next_page_token")) or offset + limit < len(reports),
            "pagination": "upstream-token + local slice", "source_url": f"{BASE}{path}"}


async def dataset_assembly(accession: str) -> dict:
    """Retrieve the dataset report for one RefSeq (GCF_) or GenBank (GCA_) assembly accession.

    Returns the full metadata report including organism, assembly level,
    status, bioproject/biosample links and annotation names.
    """
    accession = valid_id(accession.strip().upper(), _ASSEMBLY,
                         "assembly accession (GCF_/GCA_ with version, e.g. GCF_000001735.4)")
    path = f"/genome/accession/{accession}/dataset_report"
    try:
        reports, metadata = await _reports(path)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError(f"Unknown assembly accession at NCBI Datasets: {accession}") from None
        raise
    if not reports:
        raise ValueError(f"Unknown assembly accession at NCBI Datasets: {accession}")
    return {"accession": accession, "report": reports[0], "source_url": f"{BASE}{path}"}


async def dataset_genes(taxon: str, symbol: str | None = None, gene_id: str | None = None,
                        limit: int = 20) -> dict:
    """Retrieve gene dataset reports for a taxon, by gene id (e.g. 830878) or by species-scoped symbol.

    Either symbol or gene_id is REQUIRED: the whole-taxon gene listing is
    unbounded (a whole-genome dump), so this tool refuses it deliberately.
    The taxon should be species-level; upstream returns a warning report when
    the taxon is above species or the symbol is unrecognized, surfaced in
    'messages'.
    """
    taxon = _taxon(taxon)
    bounded(limit, 500)
    if (symbol is None) == (gene_id is None):
        raise ValueError("exactly one of symbol or gene_id is required "
                         "(whole-taxon gene listings are unbounded upstream)")
    if symbol is not None:
        symbol = valid_id(symbol.strip(), _SYMBOL, "gene symbol")
        path = f"/gene/symbol/{symbol}/taxon/{taxon}/dataset_report"
    else:
        gene_id = valid_id(str(gene_id).strip(), r"[0-9]+", "gene id")
        path = f"/gene/id/{gene_id}/dataset_report"
    reports, metadata = await _reports(path)
    rows = reports[:limit]
    return {"taxon": taxon, **({"symbol": symbol} if symbol is not None else {"gene_id": gene_id}),
            "reports": rows, "total": len(rows), "truncated": len(rows) < len(reports),
            **({"messages": metadata["messages"]} if "messages" in metadata else {}),
            "source_url": f"{BASE}{path}"}


async def dataset_taxon(taxon: str) -> dict:
    """Retrieve the taxonomy dataset report for a taxon (names, rank, lineage and children count).

    Accepts an NCBI taxid or a name string, e.g. 3702 or arabidopsis thaliana.
    """
    taxon = _taxon(taxon)
    path = f"/taxonomy/taxon/{taxon}/dataset_report"
    try:
        reports, _ = await _reports(path)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            raise ValueError(f"Unknown taxon at NCBI Datasets: {taxon}") from None
        raise
    if not reports:
        raise ValueError(f"Unknown taxon at NCBI Datasets: {taxon}")
    return {"taxon": taxon, "report": reports[0], "source_url": f"{BASE}{path}"}


TOOLS = (
    dataset_assemblies,
    dataset_assembly,
    dataset_genes,
    dataset_taxon,
)


RESOURCES = ()
