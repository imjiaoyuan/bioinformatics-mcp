"""Enrichr enrichment analysis against 230+ gene set libraries.

Uses the public Enrichr API at https://maayanlab.cloud/Enrichr (Ma'ayan Lab,
Mount Sinai). Results are enrichment statistics over public libraries; cite
Enrichr (Chen et al. 2013, Xie et al. 2021) in derived publications.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

from common.api import json_response, local_page, page
from common.http import identifier, identifiers, request, text

BASE = "https://maayanlab.cloud/Enrichr"

# Submissions store a transient gene list server-side, so this tool is not read-only.
MUTATING = ("enrichr_submit_genes",)


async def enrichr_libraries(limit: Annotated[int, Field(ge=1, le=300)] = 100,
                            offset: Annotated[int, Field(ge=0, le=1_000)] = 0) -> dict:
    """List available gene set libraries with term counts, gene coverage and sources."""
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/datasetStatistics")
    statistics = data.get("statistics", [])
    rows = [{"library_name": row.get("libraryName"), "num_terms": row.get("numTerms"),
             "genes_per_term": row.get("genesPerTerm"), "gene_coverage": row.get("geneCoverage"),
             "link": row.get("link")} for row in statistics]
    return {**source, **local_page(rows, paging["limit"], paging["offset"])}


async def enrichr_submit_genes(genes: list[str],
                               description: str = "bioinformatics-mcp query") -> dict:
    """Submit a gene list (symbols, up to 1000) to Enrichr; returns the userListId for enrichment.

    The submitted list is stored server-side and is retrievable by the returned userListId.
    """
    symbols = [identifier(gene.upper(), r"[A-Za-z0-9][A-Za-z0-9_.+-]*", "gene symbol")
               for gene in identifiers(genes, 1000)]
    description = text(description, "description", 200)
    response = await request("POST", f"{BASE}/addList", retryable=True,
                             files={"list": (None, "\n".join(symbols)),
                                    "description": (None, description)})
    data = response.json()
    if "userListId" not in data:
        raise ValueError("Unexpected Enrichr response format")
    return {"source_url": str(response.request.url), "user_list_id": data["userListId"],
            "short_id": data.get("shortId"), "gene_count": len(symbols),
            "genes": symbols, "description": description}


async def enrichr_enrich(user_list_id: str, library: str,
                         limit: Annotated[int, Field(ge=1, le=100)] = 20,
                         offset: Annotated[int, Field(ge=0, le=1_000_000)] = 0) -> dict:
    """Compute enrichment of a submitted gene list (from enrichr_submit_genes) against one library.

    Returns ranked terms with p-value, z-score, combined score and overlapping genes.
    """
    list_id = identifier(user_list_id, r"[0-9]+", "user list id")
    library_name = identifier(library, r"[A-Za-z0-9_.-]+", "library name")
    paging = page(limit, offset)
    data, source = await json_response(f"{BASE}/enrich", {"userListId": list_id,
                                                          "backgroundType": library_name})
    if not isinstance(data, dict) or library_name not in data:
        raise ValueError(f"No enrichment results for library {library_name}; check enrichr_libraries")
    rows = [{"rank": row.get("rank"), "term": row.get("term"), "p_value": row.get("p-value"),
             "z_score": row.get("z-score"), "combined_score": row.get("combined-score"),
             "overlapping_genes": row.get("overlapping-genes"), "adjusted_p_value": row.get("adj. p-value")}
            for row in data[library_name]]
    return {**source, **local_page(rows, paging["limit"], paging["offset"]), "library": library_name,
            "user_list_id": list_id}


TOOLS = (
    enrichr_libraries,
    enrichr_submit_genes,
    enrichr_enrich,
)
