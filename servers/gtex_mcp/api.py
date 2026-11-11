"""GTEx Portal tissue list, gene search, expression and cis-eQTL data."""
from __future__ import annotations

from common.api import choice, json_response
from common.http import bounded, identifier, text

BASE = "https://gtexportal.org/api/v2"
DATASETS = {"gtex_v8", "gtex_v10", "gtex_v11", "dgtex_v1", "gtex_snrnaseq_pilot"}
TISSUE = r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9-]+)*"
GENCODE = r"[A-Za-z][A-Za-z0-9_.-]*"


def _page(limit: int, page: int) -> dict:
    return {"itemsPerPage": bounded(limit), "page": bounded(page, 10_000, "page", 0)}


def _dataset(dataset_id: str) -> str:
    return choice(dataset_id, DATASETS, "dataset_id")


async def _get(path: str, params: dict) -> dict:
    data, source = await json_response(f"{BASE}/{path}", params)
    return {**source, **data}


async def gtex_service_info() -> dict:
    """Retrieve GTEx Portal API service information and the current release."""
    return await _get("", {})


async def gtex_tissue_list(limit: int = 20, page: int = 0) -> dict:
    """List GTEx tissues with sample counts, eGene/sGene counts and ontology identifiers."""
    return await _get("dataset/tissueSiteDetail", _page(limit, page))


async def gtex_gene_search(gene: str, limit: int = 20, page: int = 0) -> dict:
    """Search GTEx reference genes by symbol, GENCODE ID or Ensembl ID; return coordinates."""
    params = {**_page(limit, page), "geneId": text(gene, "gene", 100)}
    return await _get("reference/gene", params)


async def gtex_median_gene_expression(gencode_id: str, tissue_id: str | None = None,
                                      dataset_id: str = "gtex_v10",
                                      limit: int = 20, page: int = 0) -> dict:
    """Retrieve median gene expression in TPM across tissues for one gene.

    tissue_id is an optional upper-camel-case tissue such as Brain_Cerebellum.
    """
    params = {**_page(limit, page),
              "gencodeId": identifier(gencode_id, GENCODE, "gencode_id"),
              "datasetId": _dataset(dataset_id)}
    if tissue_id is not None:
        params["tissueSiteDetailId"] = identifier(tissue_id, TISSUE, "tissue_id")
    return await _get("expression/medianGeneExpression", params)


async def gtex_gene_expression(gencode_id: str, tissue_id: str,
                               dataset_id: str = "gtex_v10",
                               limit: int = 20, page: int = 0) -> dict:
    """Retrieve per-sample normalized gene expression for one gene in one tissue."""
    params = {**_page(limit, page),
              "gencodeId": identifier(gencode_id, GENCODE, "gencode_id"),
              "tissueSiteDetailId": identifier(tissue_id, TISSUE, "tissue_id"),
              "datasetId": _dataset(dataset_id)}
    return await _get("expression/geneExpression", params)


async def gtex_eqtl(gencode_id: str | None = None, tissue_id: str | None = None,
                    variant_id: str | None = None, dataset_id: str = "gtex_v10",
                    limit: int = 20, page: int = 0) -> dict:
    """Retrieve significant single-tissue cis-eQTLs filtered by gene, tissue or variant.

    Provide at least one filter; gencode_id is a versioned GENCODE ID such as
    ENSG00000065613.9 and variant_id a GTEx variant ID.
    """
    if gencode_id is None and tissue_id is None and variant_id is None:
        raise ValueError("Provide gencode_id, tissue_id or variant_id")
    params = {**_page(limit, page), "datasetId": _dataset(dataset_id)}
    if gencode_id is not None:
        params["gencodeId"] = identifier(gencode_id, GENCODE, "gencode_id")
    if tissue_id is not None:
        params["tissueSiteDetailId"] = identifier(tissue_id, TISSUE, "tissue_id")
    if variant_id is not None:
        params["variantId"] = text(variant_id, "variant_id", 100)
    return await _get("association/singleTissueEqtl", params)


TOOLS = (
    gtex_service_info,
    gtex_tissue_list,
    gtex_gene_search,
    gtex_median_gene_expression,
    gtex_gene_expression,
    gtex_eqtl,
)


RESOURCES = ()
