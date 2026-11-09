"""Ensembl VEP variant consequence annotation over the REST API."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import json_response
from common.http import bounded, identifier, identifiers, text

mcp = FastMCP("vep")
BASE = "https://rest.ensembl.org"

HGVS_PATTERN = r"[A-Za-z0-9_.:>+*\[\]/()-]+"
REGION_PATTERN = r"[A-Za-z0-9_.-]+:[0-9]+-[0-9]+(:[A-Za-z0-9<>*]+/[A-Za-z0-9<>*]+)?"


def _params(**flags: bool | int | None) -> dict:
    """Build bounded common VEP query parameters, negotiating JSON responses."""
    params: dict = {"content-type": "application/json"}
    for name in ("pick", "canonical", "hgvs", "protein", "mane", "refseq",
                 "numbers", "variant_class", "merged"):
        value = flags[name]
        if value:
            params[name] = "1"
    if flags["distance"] is not None:
        params["distance"] = bounded(flags["distance"], 25_000, "distance", 0)
    return params


def _species(value: str) -> str:
    return identifier(value.lower(), r"[a-z][a-z0-9_]*", "species")


async def _get(path: str, params: dict) -> dict:
    data, source = await json_response(f"{BASE}{path}", params)
    return {**source, **data} if isinstance(data, dict) else {**source, "results": data}


async def _post(path: str, params: dict, body: dict) -> dict:
    data, source = await json_response(f"{BASE}{path}", params, body=body)
    return {**source, **data} if isinstance(data, dict) else {**source, "results": data}


@mcp.tool()
async def vep_hgvs(species: str, hgvs: str, pick: bool = False, canonical: bool = False,
                   hgvs_labels: bool = False, protein: bool = False, mane: bool = False,
                   refseq: bool = False, numbers: bool = False, variant_class: bool = False,
                   merged: bool = False, distance: int | None = None) -> dict:
    """Annotate one HGVS notation (g., c. or p.) with variant consequences."""
    validated = text(hgvs, "hgvs", 150)
    if not any(f":{kind}." in validated for kind in ("g", "c", "p", "n", "m", "r")):
        raise ValueError("hgvs must use HGVS notation such as ENST00000366667:c.803C>T or 9:g.22125504G>C")
    identifier(validated, HGVS_PATTERN, "hgvs")
    return await _get(f"/vep/{_species(species)}/hgvs/{validated}",
                      _params(pick=pick, canonical=canonical, hgvs=hgvs_labels,
                              protein=protein, mane=mane, refseq=refseq, numbers=numbers,
                              variant_class=variant_class, merged=merged, distance=distance))


@mcp.tool()
async def vep_hgvs_batch(species: str, hgvs_notations: list[str], pick: bool = False,
                         canonical: bool = False, hgvs_labels: bool = False,
                         protein: bool = False, mane: bool = False, refseq: bool = False,
                         numbers: bool = False, variant_class: bool = False,
                         merged: bool = False, distance: int | None = None) -> dict:
    """Annotate up to 200 HGVS notations with variant consequences via one POST request."""
    values = identifiers(hgvs_notations, 200)
    for value in values:
        identifier(value, HGVS_PATTERN, "hgvs notation")
    params = _params(pick=pick, canonical=canonical, hgvs=hgvs_labels, protein=protein,
                     mane=mane, refseq=refseq, numbers=numbers, variant_class=variant_class,
                     merged=merged, distance=distance)
    return await _post(f"/vep/{_species(species)}/hgvs", params, {"hgvs_notations": values})


@mcp.tool()
async def vep_region(species: str, region: str, pick: bool = False, canonical: bool = False,
                     hgvs_labels: bool = False, protein: bool = False, mane: bool = False,
                     refseq: bool = False, numbers: bool = False, variant_class: bool = False,
                     merged: bool = False, distance: int | None = None) -> dict:
    """Annotate one genomic region set, e.g. 9:22125504-22125504:1/1 or 9:22125504-22125504:G/C."""
    identifier(text(region, "region", 100), REGION_PATTERN, "region set")
    return await _get(f"/vep/{_species(species)}/region/{region}",
                      _params(pick=pick, canonical=canonical, hgvs=hgvs_labels,
                              protein=protein, mane=mane, refseq=refseq, numbers=numbers,
                              variant_class=variant_class, merged=merged, distance=distance))


@mcp.tool()
async def vep_region_batch(species: str, variants: list[str], pick: bool = False,
                           canonical: bool = False, hgvs_labels: bool = False,
                           protein: bool = False, mane: bool = False, refseq: bool = False,
                           numbers: bool = False, variant_class: bool = False,
                           merged: bool = False, distance: int | None = None) -> dict:
    """Annotate up to 200 VCF-style variant lines (chromosome start id ref alt) via one POST request."""
    values = identifiers(variants, 200)
    for value in values:
        fields = value.split()
        if len(fields) < 5:
            raise ValueError("Each variant line must be VCF-like: chromosome start id ref alt")
        for field in fields:
            identifier(field, r"[A-Za-z0-9_<>.:/-]+", "VCF variant field")
    params = _params(pick=pick, canonical=canonical, hgvs=hgvs_labels, protein=protein,
                     mane=mane, refseq=refseq, numbers=numbers, variant_class=variant_class,
                     merged=merged, distance=distance)
    return await _post(f"/vep/{_species(species)}/region", params, {"variants": values})


@mcp.tool()
async def vep_id(species: str, variant_id: str, pick: bool = False, canonical: bool = False,
                 hgvs_labels: bool = False, protein: bool = False, mane: bool = False,
                 refseq: bool = False, numbers: bool = False, variant_class: bool = False,
                 merged: bool = False, distance: int | None = None) -> dict:
    """Annotate one known variant identifier such as rs56116432 or COSM476."""
    identifier(variant_id, r"[A-Za-z][A-Za-z0-9_.-]*", "variant identifier")
    return await _get(f"/vep/{_species(species)}/id/{variant_id}",
                      _params(pick=pick, canonical=canonical, hgvs=hgvs_labels,
                              protein=protein, mane=mane, refseq=refseq, numbers=numbers,
                              variant_class=variant_class, merged=merged, distance=distance))


@mcp.tool()
async def vep_id_batch(species: str, variant_ids: list[str], pick: bool = False,
                       canonical: bool = False, hgvs_labels: bool = False,
                       protein: bool = False, mane: bool = False, refseq: bool = False,
                       numbers: bool = False, variant_class: bool = False,
                       merged: bool = False, distance: int | None = None) -> dict:
    """Annotate up to 200 known variant identifiers via one POST request."""
    values = identifiers(variant_ids, 200)
    for value in values:
        identifier(value, r"[A-Za-z][A-Za-z0-9_.-]*", "variant identifier")
    params = _params(pick=pick, canonical=canonical, hgvs=hgvs_labels, protein=protein,
                     mane=mane, refseq=refseq, numbers=numbers, variant_class=variant_class,
                     merged=merged, distance=distance)
    return await _post(f"/vep/{_species(species)}/id", params, {"ids": values})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
