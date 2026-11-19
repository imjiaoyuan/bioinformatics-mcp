"""gnomAD population allele frequencies and gene constraint via the browser GraphQL API.

Queries https://gnomad.broadinstitute.org/api (no auth). gnomAD data are
distributed under a BSD-like licence (see gnomad.broadinstitute.org/about);
cite gnomAD v4/Karczewski et al. in derived work.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from common.api import choice, json_response
from common.http import bounded, identifier, text

BASE = "https://gnomad.broadinstitute.org/api"

_Datasets = Literal["gnomad_r4", "gnomad_r3", "gnomad_r2_1", "exac"]
_ReferenceGenomes = Literal["GRCh38", "GRCh37"]

_VARIANT_SELECTION = ("variantId rsid chrom pos ref alt reference_genome "
                      "genome {ac an af ac_hom} exome {ac an af ac_hom}")
_GENE_SELECTION = ("gene_id symbol hgnc_id name chrom start stop "
                   "mane_select_transcript {ensembl_id refseq_id} "
                   "gnomad_constraint {oe_mis_upper oe_lof_upper mis_z lof_z pLI}")


async def _query(selection: str, declaration: str, variables: dict) -> dict:
    result, source = await json_response(
        BASE, body={"query": f"query({declaration}) {{ {selection} }}", "variables": variables},
        interval=0.6)
    errors = result.get("errors") if isinstance(result, dict) else None
    if errors:
        message = errors[0].get("message", "unknown gnomAD error") if isinstance(errors[0], dict) else str(errors[0])
        raise ValueError(f"gnomAD query failed: {message}")
    return {**source, "data": result.get("data") if isinstance(result, dict) else None}


def _variant_id(value: str) -> str:
    value = text(value, "variant_id", 100)
    parts = value.split("-")
    if len(parts) != 4 or not parts[1].isdigit() or not parts[2] or not parts[3]:
        raise ValueError("variant_id must be formatted as chrom-pos-ref-alt, e.g. 1-55039763-C-A")
    identifier(parts[0], r"[0-9]+|[XYM]", "variant_id chromosome")
    for part in (parts[2], parts[3]):
        identifier(part, r"[A-Za-z]+", "variant_id allele")
    return value


async def gnomad_variant(variant_id: str, dataset: _Datasets = "gnomad_r4") -> dict:
    """Retrieve one variant's allele counts and frequencies for exome and genome subsets.

    ``variant_id`` uses the chrom-pos-ref-alt form (GRCh38 for gnomad_r4/r3,
    GRCh37 for gnomad_r2_1/exac); ``dataset`` selects the gnomAD release.
    """
    choice(dataset, {"gnomad_r4", "gnomad_r3", "gnomad_r2_1", "exac"}, "dataset")
    return await _query(f"variant(variantId: $v, dataset: $d) {{ {_VARIANT_SELECTION} }}",
                        "$v: String!, $d: DatasetId!",
                        {"v": _variant_id(variant_id), "d": dataset})


async def gnomad_gene(gene_symbol: str, reference_genome: _ReferenceGenomes = "GRCh38") -> dict:
    """Retrieve one gene's coordinates, MANE transcript and gnomAD constraint metrics."""
    choice(reference_genome, {"GRCh38", "GRCh37"}, "reference_genome")
    symbol = text(gene_symbol.upper(), "gene_symbol", 50)
    identifier(symbol, r"[A-Za-z0-9][A-Za-z0-9_.-]*", "gene_symbol")
    return await _query(f"gene(gene_symbol: $g, reference_genome: $rg) {{ {_GENE_SELECTION} }}",
                        "$g: String!, $rg: ReferenceGenomeId!",
                        {"g": symbol, "rg": reference_genome})


async def gnomad_gene_search(query: str, reference_genome: _ReferenceGenomes = "GRCh38",
                             limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict:
    """Search gnomAD genes by symbol prefix or other text; returns Ensembl IDs and symbols."""
    choice(reference_genome, {"GRCh38", "GRCh37"}, "reference_genome")
    search = text(query, "query", 100)
    bounded(limit)
    result = await _query("gene_search(query: $q, reference_genome: $rg) {ensembl_id ensembl_version symbol}",
                          "$q: String!, $rg: ReferenceGenomeId!",
                          {"q": search, "rg": reference_genome})
    rows = (result["data"] or {}).get("gene_search", [])
    return {**result, "results": rows[:limit], "total": len(rows), "truncated": len(rows) > limit}


TOOLS = (
    gnomad_variant,
    gnomad_gene,
    gnomad_gene_search,
)
