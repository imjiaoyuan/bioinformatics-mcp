"""MSigDB gene set collections, gene set details and curated gene members."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import local_page
from common.http import identifier, identifiers, request, text

mcp = FastMCP("msigdb")
BASE = "https://www.gsea-msigdb.org/gsea/msigdb"

SPECIES = {"human", "mouse"}

# Documented MSigDB collection catalog (H/C1-C9 human, M1-M5 mouse); the
# collection listing pages themselves are HTML-only, so catalog metadata is
# curated here instead of scraped, with the source page kept for traceability.
COLLECTIONS = {
    "human": [
        {"name": "H", "description": "Hallmark gene sets"},
        {"name": "C1", "description": "Positional gene sets", "subcollections": []},
        {"name": "C2", "description": "Curated gene sets",
         "subcollections": ["CGP", "CP", "CP:BIOCARTA", "CP:KEGG_LEGACY", "CP:KEGG_MEDICUS",
                            "CP:PID", "CP:REACTOME", "CP:WIKIPATHWAYS"]},
        {"name": "C3", "description": "Regulatory target gene sets",
         "subcollections": ["MIR", "MIR:MIRDB", "MIR:MIR_LEGACY", "TFT", "TFT:GTRD", "TFT:TFT_LEGACY"]},
        {"name": "C4", "description": "Computational gene sets",
         "subcollections": ["3CA", "CGN", "CM"]},
        {"name": "C5", "description": "Ontology gene sets",
         "subcollections": ["GO", "GO:BP", "GO:CC", "GO:MF", "HPO"]},
        {"name": "C6", "description": "Oncogenic signature gene sets"},
        {"name": "C7", "description": "Immunologic signature gene sets",
         "subcollections": ["IMMUNESIGDB", "VAX"]},
        {"name": "C8", "description": "Cell type signature gene sets"},
        {"name": "C9", "description": "Computational perturbation signature gene sets"},
    ],
    "mouse": [
        {"name": "M1", "description": "Hallmark-like mouse gene sets"},
        {"name": "M2", "description": "Curated mouse gene sets",
         "subcollections": ["M2:CP", "M2:CP:REACTOME", "M2:CP:WIKIPATHWAYS"]},
        {"name": "M3", "description": "Regulatory target mouse gene sets",
         "subcollections": ["M3:MIR", "M3:MIR:MIRDB", "M3:TFT", "M3:TFT:GTRD"]},
        {"name": "M4", "description": "Computational mouse gene sets",
         "subcollections": ["M4:CGN", "M4:CM"]},
        {"name": "M5", "description": "Cell type and ontology mouse gene sets",
         "subcollections": ["M5:GO:BP", "M5:GO:CC", "M5:GO:MF", "M5:HPO"]},
    ],
}


def _species(value: str) -> str:
    value = text(value.lower(), "species", 20)
    if value not in SPECIES:
        raise ValueError(f"species must be one of {', '.join(sorted(SPECIES))}")
    return value


def _name(value: str) -> str:
    return identifier(value.upper(), r"[A-Z0-9_]+", "gene set name")


async def _gene_set_entry(species: str, name: str) -> tuple[dict | None, str]:
    url = f"{BASE}/{species}/geneset/{name}.json"
    response = await request("GET", url)
    if "json" not in response.headers.get("content-type", ""):
        # Unknown names redirect to the "no such gene set" HTML page.
        return None, str(response.url)
    entry = response.json().get(name)
    return entry, str(response.url)


def _summary(name: str, entry: dict, source_url: str) -> dict:
    return {"gene_set": name, "systematic_name": entry.get("systematicName"),
            "collection": entry.get("collection"), "pmid": entry.get("pmid"),
            "exact_source": entry.get("exactSource"), "msigdb_url": entry.get("msigdbURL"),
            "external_details_url": entry.get("externalDetailsURL", []),
            "filtered_by_similarity": entry.get("filteredBySimilarity", []),
            "external_names_for_similar_terms": entry.get("externalNamesForSimilarTerms", []),
            "genes": entry.get("geneSymbols", []), "source_url": source_url}


@mcp.tool()
async def msigdb_gene_set(species: str, gene_set: str) -> dict:
    """Retrieve one gene set's collection, systematic name, PMID, links and genes."""
    return await _fetch_gene_set(species, gene_set)


@mcp.tool()
async def msigdb_gene_set_genes(species: str, gene_set: str, limit: int = 100,
                                offset: int = 0) -> dict:
    """List the curated gene members of one gene set with local pagination."""
    result = await _fetch_gene_set(species, gene_set)
    genes = result.pop("genes")
    page = local_page(genes, limit, offset)
    return {**result, **page}


@mcp.tool()
async def msigdb_gene_sets(species: str, gene_sets: list[str]) -> dict:
    """Retrieve summaries for 1-25 named gene sets in one species."""
    _species(species)
    names = [_name(value) for value in identifiers(gene_sets, 25)]
    results = []
    for name in names:
        entry, source_url = await _gene_set_entry(species, _name(name))
        if entry is None:
            results.append({"gene_set": _name(name), "found": False, "source_url": source_url})
        else:
            results.append({**_summary(_name(name), entry, source_url), "found": True})
    return {"species": species, "results": results,
            "source_url": f"{BASE}/{species}/geneset/"}


@mcp.tool()
async def msigdb_collections(species: str) -> dict:
    """List the documented MSigDB collections and subcollections for one species."""
    _species(species)
    return {"species": species, "collections": COLLECTIONS[species],
            "source_url": f"{BASE}/{species}/collections.jsp"}


async def _fetch_gene_set(species: str, gene_set: str) -> dict:
    species = _species(species)
    name = _name(gene_set)
    entry, source_url = await _gene_set_entry(species, name)
    if entry is None:
        raise ValueError(f"Gene set {name} was not found in the MSigDB {species} database")
    return _summary(name, entry, source_url)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
