"""Human Protein Atlas gene expression, pathology and subcellular location.

Results come from the public HPA search API. Human Protein Atlas content is
subject to the HPA licence and copyright terms
(https://www.proteinatlas.org/about/licence); cite the resource when
redistributing results.
"""
from __future__ import annotations

from common.api import json_response, local_page
from common.http import identifier, text

BASE = "https://www.proteinatlas.org/search"

_SUMMARY_KEYS = ("Gene", "Gene synonym", "Ensembl", "Gene description", "Uniprot",
                 "Chromosome", "Position", "Protein class", "Biological process",
                 "Molecular function", "Disease involvement", "Evidence",
                 "HPA evidence", "UniProt evidence", "NeXtProt evidence", "Antibody")
_TISSUE_KEYS = ("RNA tissue specificity", "RNA tissue distribution",
                "RNA tissue specificity score", "RNA tissue specific nTPM",
                "Protein tissue specificity", "Protein tissue distribution",
                "Protein tissue specificity score", "Protein tissue specific Intensity",
                "Reliability (IH)", "Tissue expression cluster",
                "RNA tissue cell type enrichment")
_CELL_KEYS = ("RNA single cell type specificity", "RNA single cell type distribution",
              "RNA single cell type specificity score",
              "RNA single cell type specific nCPM", "RNA single cell type group specificity",
              "RNA single cell type group distribution",
              "RNA single cell type group specificity score",
              "RNA single cell type group specific nCPM", "RNA cell line specificity",
              "RNA cell line distribution", "RNA cell line specificity score",
              "RNA cell line specific nTPM", "Protein cell type specificity",
              "Protein cell type distribution", "Protein cell type specificity score",
              "Protein cell type specific Intensity", "Single cell expression cluster",
              "Cell line expression cluster")
_SUBCELL_KEYS = ("Subcellular location", "Subcellular main location",
                 "Subcellular additional location", "Reliability (IF)",
                 "Secretome location", "Secretome function", "CCD Protein",
                 "CCD Transcript")
_PATHOLOGY_KEYS = ("RNA cancer specificity", "RNA cancer distribution",
                   "RNA cancer specificity score", "RNA cancer specific pTPM",
                   "Blood concentration - Conc. blood IM [pg/L]",
                   "Blood concentration - Conc. blood MS [pg/L]")


def _gene(value: str) -> str:
    return identifier(value.upper(), r"[A-Za-z0-9][A-Za-z0-9_.+-]*", "gene")


async def _rows(query: str) -> tuple[list, str]:
    data, source = await json_response(f"{BASE}/{query}", {"format": "json", "compress": "no"})
    if not isinstance(data, list):
        raise ValueError("Unexpected Human Protein Atlas response format")
    return data, source["source_url"]


def _pick(row: dict, keys: tuple[str, ...], source: str, gene: str) -> dict:
    result = {key: row[key] for key in keys if key in row}
    prognostics = {key[len("Cancer prognostics - "):]: value for key, value in row.items()
                   if key.startswith("Cancer prognostics - ")}
    if prognostics:
        result["cancer_prognostics"] = prognostics
    result.update({"gene": gene, "source_url": source,
                   "gene_url": f"https://www.proteinatlas.org/{gene}"})
    return result


async def _record(gene: str, keys: tuple[str, ...]) -> dict:
    rows, source = await _rows(f"Gene:{_gene(gene)}")
    target = _gene(gene)
    for row in rows:
        if row.get("Gene") == target or row.get("Ensembl") == target:
            return _pick(row, keys, source, target)
    raise ValueError(f"No Human Protein Atlas record matches gene {target}")


async def hpa_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search Human Protein Atlas genes by name, synonym or annotation term.

    Slices the byte-bounded upstream result locally; consult the licence
    (https://www.proteinatlas.org/about/licence) before redistributing content.
    """
    rows, source = await _rows(text(query, "query", 500))
    return {**local_page(rows, limit, offset), "source_url": source}


async def hpa_gene(gene: str) -> dict:
    """Retrieve one gene's core record: identifiers, description and evidence.

    Respect the Human Protein Atlas copyright terms when reusing content.
    """
    return await _record(gene, _SUMMARY_KEYS)


async def hpa_tissue_expression(gene: str) -> dict:
    """Retrieve tissue-level RNA and protein expression for one gene."""
    return await _record(gene, _TISSUE_KEYS)


async def hpa_cell_expression(gene: str) -> dict:
    """Retrieve single-cell type, cell-group and cell-line expression for one gene."""
    return await _record(gene, _CELL_KEYS)


async def hpa_subcellular_location(gene: str) -> dict:
    """Retrieve subcellular main and additional locations for one gene."""
    return await _record(gene, _SUBCELL_KEYS)


async def hpa_pathology(gene: str) -> dict:
    """Retrieve cancer specificity, prognostics and blood concentration for one gene."""
    return await _record(gene, _PATHOLOGY_KEYS)


TOOLS = (
    hpa_search,
    hpa_gene,
    hpa_tissue_expression,
    hpa_cell_expression,
    hpa_subcellular_location,
    hpa_pathology,
)


RESOURCES = ()
