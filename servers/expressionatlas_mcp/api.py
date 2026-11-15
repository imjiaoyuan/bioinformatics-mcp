"""Expression Atlas (EBI Gene Expression Atlas) experiment catalogue and details.

Upstream caveats: the Expression Atlas JSON API has no query parameters on the
experiment listing, so the full catalogue (~2.6 MB, several thousand entries)
is fetched once per process with a bounded response size, kept in memory and
filtered/paginated locally; results therefore reflect that catalogue snapshot,
not a live database view. The JSON API's gene-level expression endpoint
(/gxa/json/genes/{gene}) returned HTTP 404 when live-verified, so no
gene-expression tools are exposed. No HTML scraping and no files are written
to disk.
"""
from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field

from common.api import local_page, page
from common.http import identifier, request, text

EXPERIMENTS_URL = "https://www.ebi.ac.uk/gxa/json/experiments"
DETAIL_URL = "https://www.ebi.ac.uk/gxa/json/experiments/{accession}"
WEB_BASE = "https://www.ebi.ac.uk/gxa/experiments/{accession}"
MAX_BYTES = 64_000_000
ACCESSION_PATTERN = r"E-[A-Z]{4}-[0-9]+"

Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0, le=1_000_000)]

_experiments: list[dict[str, Any]] | None = None
_source_url: str | None = None
_lock = asyncio.Lock()


async def _load() -> tuple[list[dict[str, Any]], str]:
    global _experiments, _source_url
    if _experiments is not None:
        return _experiments, _source_url or EXPERIMENTS_URL
    async with _lock:
        if _experiments is None:
            response = await request("GET", EXPERIMENTS_URL, max_bytes=MAX_BYTES)
            payload = response.json()
            _experiments = payload.get("experiments") or []
            _source_url = str(response.url)
    return _experiments, _source_url or EXPERIMENTS_URL


def _reset_cache() -> None:
    """Test hook: drop the per-process catalogue snapshot."""
    global _experiments, _source_url
    _experiments = None
    _source_url = None


def _match(entry: dict[str, Any], species: str | None, assay: str | None, query: str | None) -> bool:
    if species is not None:
        if entry.get("species", "").lower().replace(" ", "_") != species:
            return False
    if assay is not None:
        haystack = " ".join(entry.get("technologyType") or []) + " " + entry.get("rawExperimentType", "")
        if assay not in haystack.lower():
            return False
    if query is not None:
        haystack = " ".join([entry.get("experimentAccession", ""), entry.get("experimentDescription", ""),
                             *(entry.get("experimentalFactors") or []),
                             *(entry.get("arrayDesignNames") or [])])
        if query not in haystack.lower():
            return False
    return True


def _factors(detail: dict[str, Any]) -> list[dict[str, str]]:
    """Distinct (propertyName, testValue) factor pairs from the assay-group headers."""
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for header in detail.get("columnHeaders") or []:
        for prop in (header.get("assayGroupSummary") or {}).get("properties") or []:
            if prop.get("contrastPropertyType") != "FACTOR" or not prop.get("testValue"):
                continue
            key = (prop.get("propertyName", ""), prop["testValue"])
            seen.setdefault(key, {"factor": key[0], "value": key[1]})
    return sorted(seen.values(), key=lambda item: (item["factor"], item["value"]))


def _assay_groups(detail: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for header in detail.get("columnHeaders") or []:
        summary = header.get("assayGroupSummary") or {}
        groups.append({"assay_group_id": header.get("assayGroupId"),
                       "factor_value": header.get("factorValue"),
                       "factor_value_ontology_term_id": header.get("factorValueOntologyTermId"),
                       "replicates": summary.get("replicates")})
    return groups


async def atlas_experiments(species: str | None = None, assay: str | None = None,
                            query: str | None = None, limit: Limit = 20, offset: Offset = 0) -> dict:
    """List Expression Atlas experiments filtered locally by species, assay type or free text.

    species uses snake_case scientific names, e.g. homo_sapiens or oryza_sativa.
    assay is a case-insensitive substring of the technology type, e.g.
    "rna-seq", "microarray" or "proteomics"; query matches accession,
    description, experimental factors and array design names. The catalogue is
    a snapshot fetched once per process (~2.6 MB) and filtered and paginated
    locally, so new experiments may be missing until the server restarts.
    All of species, assay and query are optional; omit them to list everything.
    """
    species_key = text(species, "species", 100).lower() if species is not None else None
    assay_key = text(assay, "assay", 100).lower() if assay is not None else None
    needle = text(query, "query", 150).lower() if query is not None else None
    page(limit, offset)
    experiments, source_url = await _load()
    matched = []
    for entry in experiments:
        if _match(entry, species_key, assay_key, needle):
            matched.append({"experiment_accession": entry.get("experimentAccession"),
                            "description": entry.get("experimentDescription"),
                            "species": entry.get("species"),
                            "kingdom": entry.get("kingdom"),
                            "experiment_type": entry.get("experimentType"),
                            "raw_experiment_type": entry.get("rawExperimentType"),
                            "technology_type": entry.get("technologyType") or [],
                            "number_of_assays": entry.get("numberOfAssays"),
                            "experimental_factors": entry.get("experimentalFactors") or [],
                            "array_design_names": entry.get("arrayDesignNames") or []})
    return local_page(matched, limit, offset, source_url=source_url,
                      snapshot_url=EXPERIMENTS_URL, species=species_key,
                      assay=assay_key, query=needle)


async def atlas_experiment(accession: str) -> dict:
    """Retrieve one Expression Atlas experiment's detail by accession, e.g. E-MTAB-2836.

    Returns the description, species, assay type, assay groups with replicate
    counts, experimental factors and array designs. Array designs and curated
    factors are joined from the per-process catalogue snapshot when available;
    the detail payload itself has no array information.
    """
    accession = identifier(accession.upper(), ACCESSION_PATTERN, "accession")
    detail_url = DETAIL_URL.format(accession=accession)
    response = await request("GET", detail_url, max_bytes=MAX_BYTES)
    detail = response.json()
    experiment = detail.get("experiment") or {}
    config = detail.get("config") or {}
    groups = _assay_groups(detail)
    factors = _factors(detail)
    result: dict[str, Any] = {
        "source_url": str(response.url),
        "web_url": WEB_BASE.format(accession=accession),
        "experiment_accession": experiment.get("accession", accession),
        "description": experiment.get("description"),
        "species": experiment.get("species", config.get("species")),
        "experiment_type": experiment.get("type"),
        "number_of_assay_groups": len(groups),
        "total_replicates": sum(group["replicates"] or 0 for group in groups),
        "factors": factors,
        "assay_groups": groups,
        "disclaimer": config.get("disclaimer") or None,
    }
    experiments, _ = await _load()
    for entry in experiments:
        if entry.get("experimentAccession") == accession:
            result["experimental_factors"] = entry.get("experimentalFactors") or []
            result["array_designs"] = entry.get("arrayDesignNames") or []
            result["number_of_assays"] = entry.get("numberOfAssays")
            result["technology_type"] = entry.get("technologyType") or []
            break
    else:
        result["experimental_factors"] = []
        result["array_designs"] = []
    return result


TOOLS = (
    atlas_experiments,
    atlas_experiment,
)


def atlas_catalogue() -> dict:
    """Describe the Expression Atlas endpoints and filter conventions used by atlas_* tools."""
    return {"experiments_url": EXPERIMENTS_URL,
            "detail_url": DETAIL_URL,
            "accession_pattern": ACCESSION_PATTERN,
            "filters": {"species": "snake_case scientific name, e.g. homo_sapiens",
                        "assay": "case-insensitive substring of the technology type",
                        "query": "substring over accession, description, factors, array designs"},
            "paging": {"limit": "1-100", "offset": "0-1000000"},
            "note": "Catalogue is a per-process snapshot filtered and paginated locally."}


RESOURCES = (
    ("expressionatlas://catalogue", atlas_catalogue),
)
