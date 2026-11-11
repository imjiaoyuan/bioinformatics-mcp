"""AlphaFold DB predicted-structure metadata, confidence and model file URLs."""
from __future__ import annotations

import httpx

from common.api import json_response, local_page
from common.http import identifier, identifiers

BASE = "https://alphafold.ebi.ac.uk/api/prediction"
_ACCESSION_PATTERN = r"[A-Z][0-9][A-Z0-9]{3}[0-9](-[0-9]+)?"


def _accession(value: str) -> str:
    return identifier(value.upper(), _ACCESSION_PATTERN, "UniProt accession")


async def _predictions(uniprot: str) -> list:
    data, source = await json_response(f"{BASE}/{uniprot}")
    if not isinstance(data, list):
        raise ValueError("Unexpected AlphaFold DB response")
    return [{**entry, **source} for entry in data]


async def alphafold_prediction(uniprot: str) -> dict:
    """Retrieve AlphaFold DB prediction records for one UniProt accession.

    Returns model entries with sequence, versions, gene, organism and file URLs;
    isoforms appear as separate entries (e.g. P00533-4).
    """
    entries = await _predictions(_accession(uniprot))
    return {"uniprot_accession": uniprot.upper(), "results": entries, "total": len(entries)}


async def alphafold_batch(accessions: list[str], limit: int = 20, offset: int = 0) -> dict:
    """Look up AlphaFold DB predictions for up to 50 UniProt accessions.

    Queries are issued sequentially per accession; unknown accessions are
    skipped and reported in "missing". Results are paged locally.
    """
    values = identifiers(accessions, 50)
    results: list[dict] = []
    missing: list[str] = []
    for value in values:
        accession = _accession(value)
        try:
            entries = await _predictions(accession)
        except (ValueError, httpx.HTTPStatusError):
            missing.append(accession)
            continue
        if entries:
            results.extend(entries)
        else:
            missing.append(accession)
    return local_page(results, limit, offset, missing=missing, requested=len(values))


async def alphafold_confidence(uniprot: str) -> dict:
    """Retrieve per-model confidence summaries for one UniProt accession.

    Includes the global pLDDT metric, the fraction of residues in each
    confidence band and the URLs of the full pLDDT and PAE documents.
    """
    entries = await _predictions(_accession(uniprot))
    summaries = [{
        "entry_id": entry.get("entryId"),
        "global_metric_value": entry.get("globalMetricValue"),
        "fraction_plddt_very_low": entry.get("fractionPlddtVeryLow"),
        "fraction_plddt_low": entry.get("fractionPlddtLow"),
        "fraction_plddt_confident": entry.get("fractionPlddtConfident"),
        "fraction_plddt_very_high": entry.get("fractionPlddtVeryHigh"),
        "plddt_doc_url": entry.get("plddtDocUrl"),
        "pae_doc_url": entry.get("paeDocUrl"),
    } for entry in entries]
    return {"uniprot_accession": uniprot.upper(), "results": summaries, "total": len(summaries)}


async def alphafold_model_urls(uniprot: str) -> dict:
    """List PDB, mmCIF and binary CIF download URLs for predicted models.

    Returns URLs only; download the files separately from alphafold.ebi.ac.uk.
    """
    entries = await _predictions(_accession(uniprot))
    urls = [{
        "entry_id": entry.get("entryId"),
        "pdb_url": entry.get("pdbUrl"),
        "cif_url": entry.get("cifUrl"),
        "bcif_url": entry.get("bcifUrl"),
        "pae_image_url": entry.get("paeImageUrl"),
        "msa_url": entry.get("msaUrl"),
    } for entry in entries]
    return {"uniprot_accession": uniprot.upper(), "results": urls, "total": len(urls)}


TOOLS = (
    alphafold_prediction,
    alphafold_batch,
    alphafold_confidence,
    alphafold_model_urls,
)


RESOURCES = ()
