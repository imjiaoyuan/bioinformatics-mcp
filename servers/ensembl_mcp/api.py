from __future__ import annotations
import re
from typing import Annotated, Literal

from pydantic import Field

from common.api import json_response
from common.http import bounded, identifier as valid_id, identifiers, request, text

BASE = "https://rest.ensembl.org"

# Ensembl stable IDs, e.g. ENSG00000141510, ENST00000471234, ENSP00000269305,
# plant locus/transcript styles (Os01g0100100, Os01t0100500-01), FlyBase IDs
# (FBgn0000055), WormBase genes (WBGene00004804), yeast systematic IDs (YAL060W),
# or dbSNP rs IDs.
_ID = r"(?:ENS[A-Z]{0,4}[GTPE]\d{11}(?:\.\d+)?|[A-Za-z]{2,5}\d{1,3}[GgTtPp]\d{7}(?:[.-]\d+)?|FB[a-z]{2}\d{7}|WBGene\d{8}|[A-Za-z]{3}\d{3}[A-Za-z](?:-\d+)?|RS\d{8})"
_REGION = r"[A-Za-z0-9_.-]+:\d{1,12}(?:[.:]\d{1,12})?(?:-[.:]?\d{1,12})?(?:\?.*)?"
# Variant names: dbSNP rs IDs (rs699), EVA contig-style IDs (vcZ240K4H) and
# 1001 Genomes temporary IDs (tmp_1_3651_C_G) — deliberately not the stable-ID
# pattern, which must stay untouched.
_VARIANT = r"[A-Za-z][A-Za-z0-9_.:|-]{1,120}"

def _stable_id(value: str, name: str = "identifier") -> str:
    return valid_id(value.strip(), _ID, name)

def _species_name(value: str) -> str:
    return valid_id(value.strip().lower(), r"[a-z0-9_]+", "species")

def _region(value: str) -> str:
    # Accept an optional "species:" prefix such as "human:17:1-100"; a leading
    # numeric token is a chromosome, not a species, and must be preserved.
    value = value.strip()
    head, separator, rest = value.partition(":")
    if separator and not head.isdigit():
        value = rest
    return valid_id(value, _REGION, "region")

async def _get(path: str, params: dict | None = None, *, ttl: int = 0) -> dict | list:
    data, _ = await json_response(BASE + path, {**(params or {}), "content-type": "application/json"}, ttl=ttl)
    return data

async def ensembl_lookup(identifier: str, expand: bool = False) -> dict:
    """Look up an Ensembl gene, transcript, variant, or other stable ID."""
    return await _get(f"/lookup/id/{_stable_id(identifier)}", {"expand": 1 if expand else 0}, ttl=300)

_SYMBOL = r"[A-Za-z0-9_.:|-]+"

async def ensembl_lookup_symbol(symbol: str, species: str = "oryza_sativa") -> dict:
    """Look up a gene by its species-scoped symbol (e.g. PHYB for arabidopsis_thaliana, adh for fly)."""
    symbol = valid_id(symbol.strip(), _SYMBOL, "symbol")
    species = _species_name(species)
    path = f"/lookup/symbol/{species}/{symbol}"
    data = await _get(path, {"expand": 0})
    return {"symbol": symbol, "species": species, "gene": data, "source_url": BASE + path}

async def ensembl_xrefs(identifier: str) -> list:
    """Find external database cross-references for an Ensembl identifier."""
    return await _get(f"/xrefs/id/{_stable_id(identifier)}", ttl=300)

OverlapFeature = Literal["gene", "transcript", "cds", "exon", "variation", "regulatory"]


async def ensembl_overlap(region: str, feature: OverlapFeature = "gene", species: str = "human") -> list:
    """Return Ensembl features overlapping a region such as  human:7:140424943-140624564."""
    if feature not in {"gene", "transcript", "cds", "exon", "variation", "regulatory"}:
        raise ValueError("unsupported feature")
    return await _get(f"/overlap/region/{_species_name(species)}/{_region(region)}", {"feature": feature})

async def ensembl_species(query: str = "rice", division: str = "EnsemblPlants",
                          limit: Annotated[int, Field(ge=1, le=500)] = 30) -> dict:
    """Find supported species and their assembly/release identifiers, defaulting to plants.

    Divisions: EnsemblPlants, EnsemblFungi, EnsemblMetazoa, EnsemblBacteria (the
    bacteria listing is very large, so it is fetched with a raised byte bound and
    results are still sliced locally with truncation flags).
    """
    bounded(limit, 500)
    division = valid_id(division)
    query = text(query, "query", 100).lower()
    url = f"{BASE}/info/species"
    # EnsemblBacteria lists >30k species (~10 MB JSON); raise the byte bound for
    # this division only, then slice locally to keep tool output bounded.
    max_bytes = 24_000_000 if division.lower() == "ensemblbacteria" else 8_000_000
    response = await request("GET", url, params={"division": division,
                                                "content-type": "application/json"},
                             max_bytes=max_bytes)
    data = response.json()
    matches = [s for s in data.get("species", []) if query in " ".join(
        str(s.get(k, "")) for k in ("name", "display_name", "common_name", "aliases")).lower()]
    return {"species": matches[:limit], "results": matches[:limit], "limit": limit,
            "offset": 0, "total": len(matches), "truncated": len(matches) > limit,
            "pagination": "local",
            "source_url": f"{BASE}/info/species?division={division}"}

async def ensembl_lookup_batch(ids: list[str], species: str = "oryza_sativa") -> dict:
    """Look up up to 100 IDs in one species; preserve nulls for unmapped IDs and assembly metadata."""
    values = [valid_id(i) for i in identifiers(ids, 100)]
    species = _species_name(species)
    url = f"{BASE}/lookup/id"
    response = await request("POST", url, params={"species": species, "content-type": "application/json"},
                             json={"ids": values}, retryable=True)
    return {"species": species, "records": response.json(), "source_url": url}

async def ensembl_sequence(identifier: str,
                           sequence_type: Literal["genomic", "cdna", "cds", "protein"] = "genomic",
                           max_length: Annotated[int, Field(ge=1, le=1_000_000)] = 100000) -> dict:
    """Fetch a stable-ID sequence with assembly/version descriptors; use transcript/translation IDs for protein."""
    identifier = _stable_id(identifier)
    bounded(max_length, 1_000_000, "max_length")
    if sequence_type not in {"genomic", "cdna", "cds", "protein"}:
        raise ValueError("sequence_type must be genomic, cdna, cds or protein")
    data = await _get(f"/sequence/id/{identifier}", {"type": sequence_type})
    records = data if isinstance(data, list) else [data]
    if sum(len(r.get("seq", "")) for r in records) > max_length:
        raise ValueError("Sequence exceeds max_length; use a smaller feature or increase max_length")
    return {"sequences": records, "source_url": f"{BASE}/sequence/id/{identifier}?type={sequence_type}"}

async def ensembl_homologs(identifier: str, species: str = "oryza_sativa",
                           target_species: str | None = None,
                           homology_type: Literal["orthologues", "paralogues", "all"] = "orthologues",
                           compara: Literal["plants", "fungi", "metazoa"] = "plants",
                           limit: Annotated[int, Field(ge=1, le=200)] = 20) -> dict:
    """Get orthologs/paralogs using a Genomes Compara database (plants, fungi or metazoa)."""
    identifier, species = _stable_id(identifier), _species_name(species)
    compara = valid_id(compara.strip().lower())
    if compara not in {"plants", "fungi", "metazoa"}:
        raise ValueError("compara must be plants, fungi or metazoa; EnsemblBacteria provides no homology service")
    bounded(limit, 200)
    if homology_type not in {"orthologues", "paralogues", "all"}:
        raise ValueError("homology_type must be orthologues, paralogues or all")
    params = {"type": homology_type, "compara": compara, "sequence": "none"}
    if target_species is not None:
        params["target_species"] = _species_name(target_species)
    path = f"/homology/id/{species}/{identifier}"
    data = await _get(path, params)
    rows = [h for item in data.get("data", []) for h in item.get("homologies", [])]
    return {"identifier": identifier, "species": species, "homologies": rows[:limit],
            "results": rows[:limit], "limit": limit, "offset": 0,
            "total": len(rows), "truncated": len(rows) > limit, "pagination": "local",
            "source_url": BASE + path}


async def ensembl_variation(species: str, variant_id: str) -> dict:
    """Fetch variant details for any Ensembl species (verified for rice EVA ids,
    arabidopsis 1001 Genomes ids and human rs ids; rs ids are species-scoped)."""
    species = _species_name(species)
    variant_id = valid_id(variant_id.strip(), _VARIANT, "variant_id")
    path = f"/variation/{species}/{variant_id}"
    data = await _get(path)
    return {"species": species, "variant": data, "source_url": BASE + path}

async def ensembl_region_variants(species: str, region: str,
                                  limit: Annotated[int, Field(ge=1, le=200)] = 20,
                                  offset: Annotated[int, Field(ge=0, le=10_000)] = 0) -> dict:
    """List variation features in a genomic region (verified for arabidopsis_thaliana,
    saccharomyces_cerevisiae and oryza_sativa; drosophila_melanogaster returns an
    empty list in live probing). Results are paginated locally with limit/offset."""
    # Validate every argument before the network call (project convention).
    species = _species_name(species)
    region = _region(region)
    bounded(limit, 200)
    bounded(offset, 10_000, "offset", minimum=0)
    path = f"/overlap/region/{species}/{region}"
    rows = await _get(path, {"feature": "variation"})
    page = rows[offset:offset + limit]
    return {"species": species, "region": region, "variants": page, "results": page,
            "limit": limit, "total": len(rows),
            "offset": offset, "truncated": offset + limit < len(rows),
            "pagination": "local",
            "source_url": f"{BASE}{path}?feature=variation"}


TOOLS = (
    ensembl_lookup,
    ensembl_lookup_symbol,
    ensembl_xrefs,
    ensembl_overlap,
    ensembl_species,
    ensembl_lookup_batch,
    ensembl_sequence,
    ensembl_homologs,
    ensembl_variation,
    ensembl_region_variants,
)


def _allowed_values() -> dict:
    """List Ensembl REST enum values accepted by this server's tools."""
    return {"overlap_features": ["gene", "transcript", "cds", "exon", "variation", "regulatory"],
            "sequence_types": ["genomic", "cdna", "cds", "protein"],
            "homology_types": ["orthologues", "paralogues", "all"],
            "compara_databases": ["plants", "fungi", "metazoa"],
            "divisions": ["Ensembl", "EnsemblPlants", "EnsemblFungi", "EnsemblMetazoa", "EnsemblBacteria"],
            "limits": {"ensembl_species.limit": 500, "ensembl_homologs.limit": 200,
                       "ensembl_region_variants.limit": 200, "ensembl_region_variants.offset": 10000,
                       "ensembl_sequence.max_length": 1_000_000}}


RESOURCES = (
    ("ensembl://features", _allowed_values),
)
