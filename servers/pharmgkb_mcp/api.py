"""PharmGKB/ClinPGx drugs, genes, variants and pharmacogenomic annotations."""
from __future__ import annotations

from common.api import choice, local_page, page
from common.http import get_json, identifier, text

# PharmGKB rebranded to ClinPGX: api.pharmgkb.org no longer resolves and
# www.pharmgkb.org redirects to clinpgx.org, which serves the same public v1
# data API documented at https://www.clinpgx.org/page/apiDocs.
BASE = "https://api.clinpgx.org/v1/data"
_TYPES = {"drug": "drug", "gene": "gene", "variant": "variant"}
_ANNOTATIONS = {"clinical": "clinicalAnnotation", "guideline": "guidelineAnnotation",
                "label": "labelAnnotation"}


def _pa_id(value: str, name: str = "accession ID") -> str:
    return identifier(value.upper(), r"PA[0-9]+", f"PharmGKB {name}")


async def pharmgkb_drug(drug_id: str) -> dict:
    """Retrieve a drug by its PharmGKB accession ID (e.g. PA448498)."""
    accession = _pa_id(drug_id)
    rows = await get_json(f"{BASE}/drug", {"accessionId": accession})
    return {"source_url": f"{BASE}/drug?accessionId={accession}",
            "results": rows["data"], "total": len(rows["data"])}


async def pharmgkb_gene(gene_id: str) -> dict:
    """Retrieve a gene by its PharmGKB accession ID (e.g. PA128 for CYP2D6)."""
    accession = _pa_id(gene_id)
    rows = await get_json(f"{BASE}/gene", {"accessionId": accession})
    return {"source_url": f"{BASE}/gene?accessionId={accession}",
            "results": rows["data"], "total": len(rows["data"])}


async def pharmgkb_variant(variant_id: str) -> dict:
    """Retrieve a variant by its PharmGKB accession ID (e.g. PA166155139)."""
    accession = _pa_id(variant_id)
    rows = await get_json(f"{BASE}/variant", {"accessionId": accession})
    return {"source_url": f"{BASE}/variant?accessionId={accession}",
            "results": rows["data"], "total": len(rows["data"])}


async def pharmgkb_search(query: str, object_type: str = "drug", limit: int = 20,
                          offset: int = 0) -> dict:
    """Search drugs by name or genes/variants by symbol, with local pagination.

    The upstream v1 data API returns unpaginated full lists, so paging is
    applied locally on the bounded result set.
    """
    object_type = choice(object_type, set(_TYPES), "object_type")
    term = text(query, "query", 150)
    page(limit, offset)
    rows = await get_json(f"{BASE}/{_TYPES[object_type]}", {"name": term})
    return local_page(rows["data"], limit, offset,
                      source_url=f"{BASE}/{_TYPES[object_type]}?name={term}",
                      object_type=object_type)


async def pharmgkb_clinical_annotations(drug_id: str, limit: int = 20,
                                        offset: int = 0) -> dict:
    """Retrieve clinical annotations for one drug, with local pagination.

    Levels of evidence, allele-phenotype relationships and pediatric flags are
    returned as curated by PharmGKB/ClinPGx.
    """
    accession = _pa_id(drug_id)
    page(limit, offset)
    rows = await get_json(f"{BASE}/clinicalAnnotation",
                          {"relatedChemicals.accessionId": accession})
    return local_page(rows["data"], limit, offset,
                      source_url=f"{BASE}/clinicalAnnotation"
                                 f"?relatedChemicals.accessionId={accession}")


async def pharmgkb_annotations(drug_id: str, annotation_type: str = "guideline",
                               limit: int = 20, offset: int = 0) -> dict:
    """Retrieve dosing guideline or drug-label annotations for one drug.

    annotation_type must be "guideline" (DPWG and other dosing guidelines) or
    "label" (regulatory drug-label annotations). Paging is local.
    """
    annotation_type = choice(annotation_type, set(_ANNOTATIONS), "annotation_type")
    accession = _pa_id(drug_id)
    endpoint = _ANNOTATIONS[annotation_type]
    page(limit, offset)
    rows = await get_json(f"{BASE}/{endpoint}",
                          {"relatedChemicals.accessionId": accession})
    return local_page(rows["data"], limit, offset,
                      source_url=f"{BASE}/{endpoint}"
                                 f"?relatedChemicals.accessionId={accession}",
                      annotation_type=annotation_type)


TOOLS = (
    pharmgkb_drug,
    pharmgkb_gene,
    pharmgkb_variant,
    pharmgkb_search,
    pharmgkb_clinical_annotations,
    pharmgkb_annotations,
)


RESOURCES = ()
