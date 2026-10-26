"""GWAS Catalog REST v2 curated associations, studies and variants."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import json_response
from common.http import bounded, identifier, text

mcp = FastMCP("gwas")
BASE = "https://www.ebi.ac.uk/gwas/rest/api/v2"


def _study(value: str) -> str:
    return identifier(value.upper(), r"GCST[0-9]+", "GWAS study accession")


def _variant(value: str) -> str:
    return identifier(value.lower(), r"rs[0-9]+", "rs ID")


def _efo(value: str) -> str:
    return identifier(value, r"[A-Za-z][A-Za-z0-9]*_[0-9]+", "ontology ID")


def _page(limit: int, page: int) -> dict:
    return {"size": bounded(limit), "page": bounded(page, 10000, "page", 0)}


async def _get(path: str, params: dict | None = None) -> dict:
    # v2 has HAL _embedded/_links/page fields; keep them intact for clients.
    data, source = await json_response(f"{BASE}/{path}", params, interval=0.65)
    return {**source, **data}


@mcp.tool()
async def gwas_traits(query: str, limit: int = 20, page: int = 0) -> dict:
    """Find ontology-mapped traits by name; pages start at zero."""
    return await _get("efo-traits", {**_page(limit, page), "efo_trait": text(query)})


@mcp.tool()
async def gwas_studies(trait: str | None = None, efo_id: str | None = None,
                       gene: str | None = None, ancestral_group: str | None = None,
                       limit: int = 20, page: int = 0) -> dict:
    """Find studies and sample/population metadata; use accessions for detailed retrieval."""
    params = _page(limit, page)
    for key, value in {"efo_trait": trait, "mapped_gene": gene, "ancestral_group": ancestral_group}.items():
        if value is not None:
            params[key] = text(value, key, 200)
    if efo_id is not None:
        params["efo_id"] = _efo(efo_id)
    return await _get("studies", params)


@mcp.tool()
async def gwas_study(accession: str) -> dict:
    """Get study metadata and any supplied summary-statistics links; do not download files."""
    return await _get(f"studies/{_study(accession)}")


@mcp.tool()
async def gwas_associations(efo_id: str | None = None, rs_id: str | None = None,
                            accession: str | None = None, gene: str | None = None,
                            show_child_traits: bool = False, limit: int = 20,
                            page: int = 0) -> dict:
    """Query curated top associations, not full genome-wide summary statistics."""
    params = {**_page(limit, page), "show_child_trait": str(show_child_traits).lower(),
              "extended_geneset": "false"}
    if all(value is None for value in (efo_id, rs_id, accession, gene)):
        raise ValueError("Provide efo_id, rs_id, accession or gene")
    for key, value, validate in [("efo_id", efo_id, _efo), ("rs_id", rs_id, _variant),
                                 ("accession_id", accession, _study), ("mapped_gene", gene, text)]:
        if value is not None:
            params[key] = validate(value)
    return await _get("associations", params)


@mcp.tool()
async def gwas_variant(rs_id: str) -> dict:
    """Retrieve one variant's catalog annotation and links to genomic contexts."""
    return await _get(f"single-nucleotide-polymorphisms/{_variant(rs_id)}")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
