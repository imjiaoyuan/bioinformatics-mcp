"""DISGENET gene-disease and variant-disease associations.

Requires a free academic DISGENET_API_KEY registered at
https://disgenet.com/ and provided through the environment. The REST API
authenticates with the raw key in the ``Authorization`` header, is rate
limited (HTTP 429 with ``x-rate-limit-retry-after-seconds``) and restricts
commercial use; academic users must respect the DISGENET license terms.
"""
from __future__ import annotations

import os
from typing import Annotated, Literal

from pydantic import Field

from common.api import choice, page
from common.http import bounded, identifier, request, safe_url, text

BASE = "https://www.disgenet.org/api"

BASE = "https://api.disgenet.com/api/v1"
MAX_BYTES = 8_000_000
SOURCES = {"all", "curated", "befree", "animal_models"}

Source = Literal["all", "curated", "befree", "animal_models"]
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0, le=1_000_000)]


def _key() -> str:
    key = os.environ.get("DISGENET_API_KEY")
    if not key:
        raise ValueError(
            "DISGENET_API_KEY is required; register a free academic API key at https://disgenet.com/"
        )
    return text(key, "DISGENET_API_KEY", 200)


def _cui(value: str) -> str:
    return identifier(value.upper(), r"C[0-9]+", "disease CUI")


async def _get(path: str, params: dict) -> dict:
    """Issue a bounded GET with the API-key Authorization header; retry one 429 once."""
    response = await request("GET", f"{BASE}/{path}", params=params,
                             headers={"Authorization": _key(), "accept": "application/json"},
                             retryable=True, retry_after_header="x-rate-limit-retry-after-seconds",
                             retry_after_cap=30.0)
    return {"source_url": safe_url(response.url), **response.json()}


def _paging(limit: int, offset: int) -> dict:
    """Map local limit/offset bounds onto the upstream zero-based page_number."""
    paging = page(limit, offset)
    return {**paging, "page_number": str(paging["offset"] // paging["limit"])}


async def disgenet_gda_summary(sourc: Source = "all") -> dict:
    """Summarize gene-disease association counts by source, gene and disease."""
    return await _get("gda/summary", {"sourc": choice(sourc, SOURCES, "sourc").upper()})


async def disgenet_gene_diseases(ncbi_gene_id: str | None = None, gene_symbol: str | None = None,
                                 disease_cui: str | None = None, limit: Limit = 20,
                                 offset: Offset = 0) -> dict:
    """Retrieve gene-disease associations for one gene or disease, with GDA scores.

    Provide ``ncbi_gene_id`` (Entrez Gene ID), ``gene_symbol`` or ``disease_cui``
    (UMLS CUI). Scores are source-specific evidence weights, not effect sizes.
    """
    which = [v for v in (ncbi_gene_id, gene_symbol, disease_cui) if v is not None]
    if not which:
        raise ValueError("Provide ncbi_gene_id, gene_symbol or disease_cui")
    params = _paging(limit, offset)
    if ncbi_gene_id is not None:
        params["gene_ncbi_id"] = identifier(ncbi_gene_id, r"[0-9]+", "ncbi_gene_id")
    if gene_symbol is not None:
        params["gene_symbol"] = identifier(gene_symbol, r"[A-Za-z0-9_.@-]+", "gene_symbol")
    if disease_cui is not None:
        params["diseaseid"] = _cui(disease_cui)
    return await _get("gda/gene", params)


async def disgenet_disease_genes(disease_cui: str, limit: Limit = 20, offset: Offset = 0) -> dict:
    """Retrieve the genes associated with one disease by UMLS CUI, with GDA scores."""
    return await _get("gda/disease", {**_paging(limit, offset), "diseaseid": _cui(disease_cui)})


async def disgenet_vda_summary(sourc: Source = "all") -> dict:
    """Summarize variant-disease association counts by source, variant and disease."""
    return await _get("vda/summary", {"sourc": choice(sourc, SOURCES, "sourc").upper()})


async def disgenet_variant_diseases(snp_id: str | None = None, vdb_id: str | None = None,
                                    disease_cui: str | None = None, limit: Limit = 20,
                                    offset: Offset = 0) -> dict:
    """Retrieve variant-disease associations by dbSNP rsID, DISGENET variant ID or disease.

    Provide ``snp_id`` (rs number), ``vdb_id`` (DISGENET variant identifier) or
    ``disease_cui`` (UMLS CUI).
    """
    which = [v for v in (snp_id, vdb_id, disease_cui) if v is not None]
    if not which:
        raise ValueError("Provide snp_id, vdb_id or disease_cui")
    params = _paging(limit, offset)
    if snp_id is not None:
        params["snp_id"] = identifier(snp_id.lower(), r"rs[0-9]+", "snp_id")
    if vdb_id is not None:
        params["vdb_id"] = identifier(vdb_id, r"[0-9]+", "vdb_id")
    if disease_cui is not None:
        params["diseaseid"] = _cui(disease_cui)
    return await _get("vda/variant", params)


async def disgenet_disease_variants(disease_cui: str, limit: Limit = 20, offset: Offset = 0) -> dict:
    """Retrieve the variants associated with one disease by UMLS CUI, with VDA scores."""
    return await _get("vda/disease", {**_paging(limit, offset), "diseaseid": _cui(disease_cui)})


TOOLS = (
    disgenet_gda_summary,
    disgenet_gene_diseases,
    disgenet_disease_genes,
    disgenet_vda_summary,
    disgenet_variant_diseases,
    disgenet_disease_variants,
)


def disgenet_sources() -> dict:
    """List the association source filters accepted by disgenet_* tools."""
    return {"sources": sorted(SOURCES),
            "identifiers": {"gene": "Entrez Gene ID, symbol or UMLS CUI (C....)",
                            "variant": "dbSNP rsID, DISGENET vdb_id or UMLS CUI"},
            "env": ["DISGENET_API_KEY (required)"],
            "paging": {"limit": "1-100", "offset": "0-1000000 (mapped upstream to page_number)"}}


RESOURCES = (
    ("disgenet://sources", disgenet_sources),
)
