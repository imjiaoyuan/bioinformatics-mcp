from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from common.http import bounded, get_json, identifier as valid_id, identifiers, request, text

mcp = FastMCP("ensembl")
BASE = "https://rest.ensembl.org"

async def _get(path: str, params: dict | None = None) -> dict | list:
    return await get_json(BASE + path, {**(params or {}), "content-type": "application/json"})

@mcp.tool()
async def ensembl_lookup(identifier: str, expand: bool = False) -> dict:
    """Look up an Ensembl gene, transcript, variant, or other stable ID."""
    return await _get(f"/lookup/id/{identifier.strip()}", {"expand": 1 if expand else 0})

@mcp.tool()
async def ensembl_xrefs(identifier: str) -> list:
    """Find external database cross-references for an Ensembl identifier."""
    return await _get(f"/xrefs/id/{identifier.strip()}")

@mcp.tool()
async def ensembl_overlap(region: str, feature: str = "gene", species: str = "human") -> list:
    """Return Ensembl features overlapping a region such as  human:7:140424943-140624564."""
    if feature not in {"gene", "transcript", "cds", "exon", "variation", "regulatory"}:
        raise ValueError("unsupported feature")
    path = f"/overlap/region/{species}/{region.split(':', 1)[-1]}"
    return await _get(path, {"feature": feature})

@mcp.tool()
async def ensembl_species(query: str = "rice", division: str = "EnsemblPlants", limit: int = 30) -> dict:
    """Find supported species and their assembly/release identifiers, defaulting to plants."""
    bounded(limit, 500)
    valid_id(division)
    query = text(query, "query", 100).lower()
    data = await _get("/info/species", {"division": division})
    matches = [s for s in data.get("species", []) if query in " ".join(
        str(s.get(k, "")) for k in ("name", "display_name", "common_name", "aliases")).lower()]
    return {"species": matches[:limit], "total": len(matches), "truncated": len(matches) > limit,
            "source_url": f"{BASE}/info/species?division={division}"}


@mcp.tool()
async def ensembl_lookup_batch(ids: list[str], species: str = "oryza_sativa") -> dict:
    """Look up up to 100 IDs in one species; preserve nulls for unmapped IDs and assembly metadata."""
    values = [valid_id(i) for i in identifiers(ids, 100)]
    species = valid_id(species)
    url = f"{BASE}/lookup/id"
    response = await request("POST", url, params={"species": species, "content-type": "application/json"},
                             json={"ids": values}, retryable=True)
    return {"species": species, "records": response.json(), "source_url": url}


@mcp.tool()
async def ensembl_sequence(identifier: str, sequence_type: str = "genomic", max_length: int = 100000) -> dict:
    """Fetch a stable-ID sequence with assembly/version descriptors; use transcript/translation IDs for protein."""
    identifier = valid_id(identifier)
    bounded(max_length, 1_000_000, "max_length")
    if sequence_type not in {"genomic", "cdna", "cds", "protein"}:
        raise ValueError("sequence_type must be genomic, cdna, cds or protein")
    data = await _get(f"/sequence/id/{identifier}", {"type": sequence_type})
    records = data if isinstance(data, list) else [data]
    if sum(len(r.get("seq", "")) for r in records) > max_length:
        raise ValueError("Sequence exceeds max_length; use a smaller feature or increase max_length")
    return {"sequences": records, "source_url": f"{BASE}/sequence/id/{identifier}?type={sequence_type}"}


@mcp.tool()
async def ensembl_homologs(identifier: str, species: str = "oryza_sativa",
                          target_species: str | None = None, homology_type: str = "orthologues",
                          compara: str = "plants", limit: int = 20) -> dict:
    """Get plant orthologs/paralogs using the plants Compara database, without sequence alignments."""
    identifier, species, compara = valid_id(identifier), valid_id(species), valid_id(compara)
    bounded(limit, 200)
    if homology_type not in {"orthologues", "paralogues", "all"}:
        raise ValueError("homology_type must be orthologues, paralogues or all")
    params = {"type": homology_type, "compara": compara, "sequence": "none"}
    if target_species is not None:
        params["target_species"] = valid_id(target_species)
    path = f"/homology/id/{species}/{identifier}"
    data = await _get(path, params)
    rows = [h for item in data.get("data", []) for h in item.get("homologies", [])]
    return {"identifier": identifier, "species": species, "homologies": rows[:limit],
            "total": len(rows), "truncated": len(rows) > limit, "source_url": BASE + path}


def main() -> None: mcp.run()
if __name__ == "__main__": main()
