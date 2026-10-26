"""Public cBioPortal studies, clinical data and selected molecular measurements."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response
from common.http import bounded, identifier, identifiers, request, text

mcp = FastMCP("cbioportal")
BASE = "https://www.cbioportal.org/api"


def _page(limit: int, page: int) -> dict:
    return {"pageSize": bounded(limit), "pageNumber": bounded(page, 10000, "page", 0),
            "projection": "DETAILED"}


async def _list(path: str, params: dict, body: dict | None = None) -> dict:
    response = await request("GET" if body is None else "POST", f"{BASE}/{path}",
                             params=params, json=body, retryable=body is not None)
    rows = response.json()
    total = response.headers.get("total-count")
    # A full page only signals a possible next page when the API omits a total.
    limit, index = params.get("pageSize"), params.get("pageNumber", 0)
    return {"source_url": str(response.url), "results": rows,
            "total": int(total) if total is not None else None,
            "limit": limit, "page": index,
            "has_more": (index * limit + len(rows) < int(total) if total is not None else None) if limit else False,
            "may_have_more": len(rows) == limit if limit else False}


def _selection(sample_ids: list[str], gene_ids: list[int]) -> dict:
    samples = list(dict.fromkeys(identifier(value) for value in identifiers(sample_ids, 100)))
    if not gene_ids or len(gene_ids) > 100:
        raise ValueError("gene_ids must contain 1-100 Entrez gene IDs")
    genes = list(dict.fromkeys(bounded(value, 2_147_483_647, "Entrez gene ID") for value in gene_ids))
    if len(samples) * len(genes) > 1000:
        raise ValueError("Select at most 1000 sample-gene pairs")
    return {"sampleIds": samples, "entrezGeneIds": genes}


@mcp.tool()
async def cbioportal_studies(query: str | None = None, limit: int = 20, page: int = 0) -> dict:
    """List public studies, optionally searching study name and cancer type."""
    params = _page(limit, page)
    if query is not None:
        params["keyword"] = text(query)
    return await _list("studies", params)


@mcp.tool()
async def cbioportal_samples(study_id: str, limit: int = 20, page: int = 0) -> dict:
    """List samples with patient identifiers and sample types."""
    return await _list(f"studies/{identifier(study_id)}/samples", _page(limit, page))


@mcp.tool()
async def cbioportal_clinical(study_id: str, attribute_id: str | None = None,
                             level: str = "SAMPLE", limit: int = 20, page: int = 0) -> dict:
    """Retrieve clinical values at SAMPLE or PATIENT level, retaining attribute identifiers."""
    params = {**_page(limit, page), "clinicalDataType": choice(level, {"SAMPLE", "PATIENT"}, "level")}
    if attribute_id is not None:
        params["attributeId"] = identifier(attribute_id)
    return await _list(f"studies/{identifier(study_id)}/clinical-data", params)


@mcp.tool()
async def cbioportal_molecular_profiles(study_id: str, limit: int = 20, page: int = 0) -> dict:
    """Discover molecular profiles; inspect datatype, alteration type and description before use."""
    return await _list(f"studies/{identifier(study_id)}/molecular-profiles", _page(limit, page))


@mcp.tool()
async def cbioportal_mutations(profile_id: str, sample_ids: list[str], gene_ids: list[int],
                               limit: int = 20, page: int = 0) -> dict:
    """Fetch mutations for explicit samples and Entrez genes with upstream pagination."""
    profile_id = identifier(profile_id)
    body = _selection(sample_ids, gene_ids)
    params = _page(limit, page)
    profile, source = await json_response(f"{BASE}/molecular-profiles/{profile_id}")
    if profile.get("molecularAlterationType") != "MUTATION_EXTENDED":
        raise ValueError("profile_id must identify a MUTATION_EXTENDED profile")
    result = await _list(f"molecular-profiles/{profile_id}/mutations/fetch", params, body)
    return {**result, "profile": profile, "profile_source_url": source["source_url"]}


@mcp.tool()
async def cbioportal_molecular_data(profile_id: str, sample_ids: list[str], gene_ids: list[int]) -> dict:
    """Read numeric measurements for at most 1000 sample-gene pairs.

    Values retain the selected profile's scale; no conversion to counts/TPM is implied.
    """
    profile_id = identifier(profile_id)
    body = _selection(sample_ids, gene_ids)
    profile, source = await json_response(f"{BASE}/molecular-profiles/{profile_id}")
    choice(profile.get("molecularAlterationType"),
           {"MRNA_EXPRESSION", "COPY_NUMBER_ALTERATION", "PROTEIN_LEVEL", "METHYLATION"},
           "profile molecularAlterationType")
    result = await _list(f"molecular-profiles/{profile_id}/molecular-data/fetch",
                         {"projection": "DETAILED"}, body)
    return {**result, "profile": profile, "profile_source_url": source["source_url"],
            "requested_pairs": len(body["sampleIds"]) * len(body["entrezGeneIds"])}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
