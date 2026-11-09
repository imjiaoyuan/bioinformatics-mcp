"""DISGENET gene-disease and variant-disease associations.

Requires a free academic DISGENET_API_KEY registered at
https://disgenet.com/ and provided through the environment. The REST API
authenticates with the raw key in the ``Authorization`` header, is rate
limited (HTTP 429 with ``x-rate-limit-retry-after-seconds``) and restricts
commercial use; academic users must respect the DISGENET license terms.
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

from common.api import choice, page
from common.http import bounded, identifier, text

mcp = FastMCP("disgenet")
BASE = "https://api.disgenet.com/api/v1"
MAX_BYTES = 8_000_000
SOURCES = {"all", "curated", "befree", "animal_models"}


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
    for attempt in range(2):
        await asyncio.sleep(0.35 if attempt == 0 else 0)
        async with httpx.AsyncClient(timeout=45, follow_redirects=True,
                                     headers={"Authorization": _key(),
                                              "accept": "application/json",
                                              "User-Agent": "bioinformatics-mcp/0.1"}) as client:
            async with client.stream("GET", f"{BASE}/{path}", params=params) as response:
                if response.status_code == 429 and attempt == 0:
                    try:
                        delay = min(30.0, max(1.0, float(
                            response.headers.get("x-rate-limit-retry-after-seconds", "1"))))
                    except ValueError:
                        delay = 1.0
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Response is too large; narrow the query or reduce the limit")
                    chunks.append(chunk)
                await response.aclose()
                return {"source_url": str(response.request.url),
                        **json.loads(b"".join(chunks))}
    raise RuntimeError("Request retry exhausted")


def _paging(limit: int, offset: int) -> dict:
    """Map local limit/offset bounds onto the upstream zero-based page_number."""
    paging = page(limit, offset)
    return {**paging, "page_number": str(paging["offset"] // paging["limit"])}


@mcp.tool()
async def disgenet_gda_summary(sourc: str = "all") -> dict:
    """Summarize gene-disease association counts by source, gene and disease."""
    return await _get("gda/summary", {"sourc": choice(sourc, SOURCES, "sourc").upper()})


@mcp.tool()
async def disgenet_gene_diseases(ncbi_gene_id: str | None = None, gene_symbol: str | None = None,
                                 disease_cui: str | None = None, limit: int = 20,
                                 offset: int = 0) -> dict:
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


@mcp.tool()
async def disgenet_disease_genes(disease_cui: str, limit: int = 20, offset: int = 0) -> dict:
    """Retrieve the genes associated with one disease by UMLS CUI, with GDA scores."""
    return await _get("gda/disease", {**_paging(limit, offset), "diseaseid": _cui(disease_cui)})


@mcp.tool()
async def disgenet_vda_summary(sourc: str = "all") -> dict:
    """Summarize variant-disease association counts by source, variant and disease."""
    return await _get("vda/summary", {"sourc": choice(sourc, SOURCES, "sourc").upper()})


@mcp.tool()
async def disgenet_variant_diseases(snp_id: str | None = None, vdb_id: str | None = None,
                                    disease_cui: str | None = None, limit: int = 20,
                                    offset: int = 0) -> dict:
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


@mcp.tool()
async def disgenet_disease_variants(disease_cui: str, limit: int = 20, offset: int = 0) -> dict:
    """Retrieve the variants associated with one disease by UMLS CUI, with VDA scores."""
    return await _get("vda/disease", {**_paging(limit, offset), "diseaseid": _cui(disease_cui)})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
