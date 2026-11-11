"""BioGRID genetic and protein interaction networks.

Requires a free BIOGRID_API_KEY access key registered at
https://webservice.thebiogrid.org/ and provided through the environment.
The REST service returns JSON with an ``accesskey`` query parameter and is
rate limited; shared clients must register their own key.
"""
from __future__ import annotations

import os

from common.api import choice, json_response
from common.http import bounded, identifier, identifiers, text

BASE = "https://webservice.thebiogrid.org"


def _key() -> str:
    key = os.environ.get("BIOGRID_API_KEY")
    if not key:
        raise ValueError(
            "BIOGRID_API_KEY is required; register a free access key at https://webservice.thebiogrid.org/"
        )
    return text(key, "BIOGRID_API_KEY", 100)


def _pipe(values: list[str]) -> str:
    """Join validated gene, evidence or PubMed terms into the upstream pipe list."""
    return "|".join(identifiers(values))


def _bool(value: bool) -> str:
    return "true" if value else "false"


async def _get(path: str, params: dict) -> dict:
    params["accesskey"] = _key()
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


async def biogrid_interactions(genes: list[str] | None = None, tax_id: str | None = None,
                               evidence_list: list[str] | None = None,
                               pubmed_list: list[str] | None = None,
                               search_ids: bool = False, search_names: bool = True,
                               include_interactors: bool = True,
                               throughput: str = "any", limit: int = 20,
                               start: int = 0) -> dict:
    """Retrieve curated interactions for genes by official symbol or identifier.

    Provide ``genes`` (official symbols, Entrez Gene or systematic IDs matched via
    ``search_names``/``search_ids``), or ``pubmed_list`` to fetch interactions from
    specific publications. Results follow the upstream .tab2 fields; the REST
    service caps one page at 10,000 rows, so page further with ``start``.
    """
    if genes is None and pubmed_list is None:
        raise ValueError("Provide genes or pubmed_list")
    params = {"start": bounded(start, 10_000, "start", 0), "max": bounded(limit),
              "format": "json", "includeInteractors": _bool(include_interactors),
              "throughputTag": choice(throughput, {"any", "low", "high"}, "throughput")}
    if genes is not None:
        params["geneList"] = _pipe(genes)
        params["searchIds"] = _bool(search_ids)
        params["searchNames"] = _bool(search_names)
    if tax_id is not None:
        params["taxId"] = text(tax_id, "tax_id", 100)
    if evidence_list is not None:
        params["evidenceList"] = _pipe(evidence_list)
        params["includeEvidence"] = "true"
    if pubmed_list is not None:
        params["pubmedList"] = _pipe(pubmed_list)
    return await _get("interactions/", params)


async def biogrid_interaction(interaction_id: str) -> dict:
    """Retrieve one interaction record by its BioGRID interaction ID."""
    return await _get(f"interaction/{identifier(interaction_id, r'[0-9]+', 'interaction_id')}",
                      {"format": "json"})


async def biogrid_evidence() -> dict:
    """List supported experimental evidence (experimental system) names."""
    return await _get("evidence/", {"format": "json"})


async def biogrid_organisms() -> dict:
    """List organisms supported by the tax_id filter."""
    return await _get("organisms/", {"format": "json"})


async def biogrid_identifiers() -> dict:
    """List additional identifier types supported by cross-reference search."""
    return await _get("identifiers/", {"format": "json"})


async def biogrid_version() -> dict:
    """Report the BioGRID release version served by the REST endpoint."""
    data, source = await json_response(f"{BASE}/version", {"accesskey": _key()})
    return {"source_url": source["source_url"],
            "version": data if isinstance(data, str) else str(data)}


TOOLS = (
    biogrid_interactions,
    biogrid_interaction,
    biogrid_evidence,
    biogrid_organisms,
    biogrid_identifiers,
    biogrid_version,
)


RESOURCES = ()
