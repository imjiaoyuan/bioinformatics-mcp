"""Variant records via Ensembl Variation REST and NCBI dbSNP E-utilities.

Ensembl serves consequence, mappings and population frequencies for dbSNP
rs IDs; NCBI dbSNP serves validation, genes and clinical significance via
Entrez esearch/esummary (db "snp"). Known upstream quirk: Ensembl currently
returns an empty ``populations`` list for many variants while population
data is being reprocessed, so variation_populations may legitimately
return zero rows.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote

from common.api import local_page, page
from common.http import identifier, identifiers, request, safe_url, text

ENSEMBL = "https://rest.ensembl.org"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

RSID = re.compile(r"rs[0-9]+")


def _rsid(value: str, name: str = "rsid") -> str:
    """Accept rs IDs with or without the leading "rs" and normalize to lowercase."""
    stripped = str(value).strip().lower().removeprefix("rs")
    return identifier(f"rs{stripped}", rf"{RSID.pattern}", name)


def _species(value: str) -> str:
    return identifier(value.strip().lower(), r"[a-z0-9_]+", "species")


async def _variation(rsid: str, species: str) -> dict:
    # Ensembl throttles unauthenticated clients; keep the shared interval.
    response = await request("GET", f"{ENSEMBL}/variation/{species}/{rsid}",
                             params={"content-type": "application/json"}, interval=0.35)
    return {**response.json(), "source_url": safe_url(response.url)}


def _mappings(data: dict) -> list[dict]:
    return [{"assembly": mapping.get("assembly_name"), "chromosome": mapping.get("seq_region_name"),
             "start": mapping.get("start"), "end": mapping.get("end"),
             "allele_string": mapping.get("allele_string"), "strand": mapping.get("strand"),
             "location": mapping.get("location")}
            for mapping in data.get("mappings", [])]


def _grch38(mappings: list[dict]) -> dict | None:
    return next((mapping for mapping in mappings if mapping["assembly"] == "GRCh38"),
                mappings[0] if mappings else None)


async def variation_entry(rsid: str, species: str = "human") -> dict:
    """Retrieve one dbSNP variant summary from Ensembl Variation.

    Returns the rs ID, most severe consequence, variant class, clinical
    significance, minor allele/MAF, evidence flags and chromosome
    locations per assembly (GRCh38 mapping highlighted when present).
    """
    rsid = _rsid(rsid)
    species = _species(species)
    data = await _variation(rsid, species)
    mappings = _mappings(data)
    return {"source_url": data["source_url"], "rsid": data.get("name", rsid), "species": species,
            "most_severe_consequence": data.get("most_severe_consequence"),
            "variant_class": data.get("var_class"), "clinical_significance": data.get("clinical_significance"),
            "minor_allele": data.get("minor_allele"), "maf": data.get("MAF"), "ambiguity": data.get("ambiguity"),
            "evidence": data.get("evidence", []), "source": data.get("source"),
            "synonyms": data.get("synonyms", []), "mappings": mappings,
            "grch38_location": _grch38(mappings)}


async def variation_populations(rsid: str, species: str = "human",
                                limit: int = 20, offset: int = 0) -> dict:
    """List population allele frequencies for one dbSNP variant from Ensembl.

    Frequencies are returned as one row per study/population; rows are
    sliced locally with explicit pagination metadata. Ensembl is
    progressively reprocessing population data, so some variants
    currently return zero rows.
    """
    rsid = _rsid(rsid)
    species = _species(species)
    data = await _variation(rsid, species)
    rows = [{"population": item.get("population") or item.get("population_name"),
             "sample_size": item.get("pop_samplesize"),
             "allele_frequencies": item.get("freqs", {})}
            for item in data.get("populations", [])]
    return local_page(rows, limit, offset, source_url=data["source_url"],
                      rsid=data.get("name", rsid), most_severe_consequence=data.get("most_severe_consequence"))


async def variation_batch(rs_ids: list[str], species: str = "human") -> dict:
    """Retrieve summaries for 1-20 dbSNP variants sequentially from Ensembl.

    Each rs ID is fetched independently; individual failures are retained
    in ``errors`` with ``partial``/``all_failed`` flags so one bad ID does
    not discard the rest.
    """
    values = [_rsid(value) for value in identifiers([str(value) for value in rs_ids], 20)]
    species = _species(species)
    entries: list[dict] = []
    errors: dict[str, str] = {}
    for rsid in values:
        try:
            data = await _variation(rsid, species)
            mappings = _mappings(data)
            entries.append({"rsid": data.get("name", rsid),
                            "most_severe_consequence": data.get("most_severe_consequence"),
                            "variant_class": data.get("var_class"),
                            "clinical_significance": data.get("clinical_significance"),
                            "minor_allele": data.get("minor_allele"), "maf": data.get("MAF"),
                            "mappings": mappings, "grch38_location": _grch38(mappings),
                            "source_url": data["source_url"]})
        except Exception as exc:  # retain per-item errors for batch tolerance
            errors[rsid] = str(exc)
    return {"species": species, "requested": len(values), "entries": entries, "errors": errors,
            "partial": bool(errors), "all_failed": bool(values) and len(errors) == len(values),
            "source_url": f"{ENSEMBL}/variation/{species}"}


def _config() -> dict[str, str]:
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    config = {"email": email, "tool": "variation-mcp"}
    if api_key := os.environ.get("NCBI_API_KEY"):
        config["api_key"] = api_key
    return config


async def _entrez(endpoint: str, params: dict[str, str]) -> dict:
    # Stay below the unauthenticated NCBI limit; API-key users can go faster.
    interval = 0.11 if "api_key" in (config := _config()) else 0.35
    response = await request("GET", f"{EUTILS}/{endpoint}.fcgi",
                             params={**params, **config, "retmode": "json"}, interval=interval)
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    return {**data, "source_url": safe_url(response.url)}


def _summary(summary: dict) -> dict:
    """Extract one dbSNP docsum: organism, validation, genes and position."""
    return {"uid": summary.get("uid"), "snp_id": summary.get("snp_id"),
            "tax_id": summary.get("tax_id"), "organism": "Homo sapiens" if str(summary.get("tax_id")) == "9606" else None,
            "snp_class": summary.get("snp_class"), "allele_origin": summary.get("allele_origin") or None,
            "validated": [value for value in (summary.get("validated") or "").split(",") if value],
            "functional_class": [value for value in (summary.get("fxn_class") or "").split(",") if value],
            "genes": [{"symbol": gene.get("name"), "gene_id": gene.get("gene_id")}
                      for gene in summary.get("genes", [])],
            "chromosome": summary.get("chr"), "accession": summary.get("acc"),
            "position": summary.get("chrpos"), "spdi": summary.get("spdi"),
            "clinical_significance": summary.get("clinical_significance") or None,
            "mapweight": summary.get("map_weight"), "created": summary.get("createdate"),
            "updated": summary.get("updatedate")}


async def dbsnp_summary(rs_ids: list[str]) -> dict:
    """Retrieve NCBI dbSNP summaries for 1-20 rs IDs in one esummary call.

    Returns organism/tax ID, validation status, functional class, genes,
    chromosome position, SPDI and clinical significance per rs ID. In
    current dbSNP docsums the organism is reported as a taxonomy ID and
    MAPWEIGHT has been retired from the schema.
    """
    values = [_rsid(value) for value in identifiers([str(value) for value in rs_ids], 20)]
    uids = ",".join(value.removeprefix("rs") for value in values)
    data = await _entrez("esummary", {"db": "snp", "id": uids})
    result = data.get("result", {})
    rows = [_summary(result[uid]) for value in values
            if (uid := value.removeprefix("rs")) in result and isinstance(result.get(uid), dict)]
    missing = [value for value in values if value.removeprefix("rs") not in result]
    return {"requested": len(values), "results": rows, "missing": missing,
            "partial": bool(missing), "source_url": data["source_url"]}


async def dbsnp_search(term: str, limit: int = 20, offset: int = 0) -> dict:
    """Search dbSNP rs IDs with Entrez syntax, e.g. ``AGT[gene]``.

    Returns matching UIDs and the total hit count with explicit
    upstream pagination metadata.
    """
    query = text(term, "term")
    paging = page(limit, offset)
    data = await _entrez("esearch", {"db": "snp", "term": query,
                                     "retmax": paging["limit"], "retstart": paging["offset"]})
    result = data.get("esearchresult", {})
    return {**paging, "term": query, "count": int(result.get("count", "0")),
            "uids": result.get("idlist", []),
            "source_url": f"{EUTILS}/esearch.fcgi?db=snp&term={quote(query)}"}


TOOLS = (
    variation_entry,
    variation_populations,
    variation_batch,
    dbsnp_summary,
    dbsnp_search,
)


def _sources() -> dict:
    """Describe the variant data sources and their parameter constraints."""
    return {"ensembl_variation": {"base": ENSEMBL,
                                  "endpoints": ["/variation/{species}/{rsid}"],
                                  "id_format": "dbSNP rs IDs (rs prefix optional); species as scientific_name slug"},
            "ncbi_dbsnp": {"base": EUTILS,
                           "endpoints": ["esearch (db=snp)", "esummary (db=snp)"],
                           "requires": "NCBI_EMAIL (NCBI_API_KEY optional)",
                           "batch_size": "1-20 rs IDs per call"}}


RESOURCES = (
    ("variation://sources", _sources),
)
