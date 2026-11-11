"""UniProtKB search, annotated records, sequences and asynchronous ID mapping."""
from __future__ import annotations

import asyncio

from common.http import bounded, get_json, identifier, identifiers, request, text

BASE = "https://rest.uniprot.org"
FIELDS = "accession,id,protein_name,gene_names,organism_name,length,cc_function,cc_subcellular_location"


def _accession(value: str) -> str:
    return identifier(value.upper(), r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[0-9]+)?", "UniProt accession")


def _job(value: str) -> str:
    return identifier(value, r"[A-Za-z0-9_-]{1,100}", "mapping job ID")


async def uniprot_search(query: str, limit: int = 20, cursor: str | None = None) -> dict:
    """Search UniProtKB, e.g. organism_id:4530 AND protein_name:heat; return next-page link."""
    params = {"query": text(query), "format": "json", "size": bounded(limit), "fields": FIELDS}
    if cursor is not None:
        params["cursor"] = text(cursor, "cursor", 2000)
    response = await request("GET", f"{BASE}/uniprotkb/search", params=params)
    return {"results": response.json().get("results", []), "total": response.headers.get("x-total-results"),
            "next_url": response.links.get("next", {}).get("url"), "source_url": str(response.url)}


async def uniprot_entry(accession: str) -> dict:
    """Get a UniProtKB record including functional comments, locations and cross-references."""
    accession = _accession(accession)
    url = f"{BASE}/uniprotkb/{accession}.json"
    return {"record": await get_json(url), "source_url": url}


def _function_summary(record: dict) -> dict:
    """Keep curated claims, warnings and evidence together; never infer missing function."""
    accession = record["primaryAccession"]
    source_url = f"https://www.uniprot.org/uniprotkb/{accession}/entry"
    comments = record.get("comments", [])
    functions = [row for comment in comments if comment.get("commentType") == "FUNCTION"
                 for row in comment.get("texts", [])]
    cautions = [comment for comment in comments if comment.get("commentType") in {"CAUTION", "SEQUENCE CAUTION"}]
    features = record.get("features", [])
    go = [row for row in record.get("uniProtKBCrossReferences", []) if row.get("database") == "GO"]
    # Attach citations to the actual statements/features, including contradictory phenotypes.
    cited_pmids: set[str] = set()

    def collect_evidence(value: object) -> None:
        if isinstance(value, dict):
            if value.get("source") == "PubMed" and value.get("id"):
                cited_pmids.add(value["id"])
            for item in value.values():
                collect_evidence(item)
        elif isinstance(value, list):
            for item in value:
                collect_evidence(item)

    collect_evidence([comments, features[:100], go[:100]])
    references = []
    for reference in record.get("references", []):
        citation = reference.get("citation", {})
        ids = {row["database"]: row["id"] for row in citation.get("citationCrossReferences", [])}
        pmid = ids.get("PubMed")
        if pmid not in cited_pmids:
            continue
        references.append({"pmid": pmid, "doi": ids.get("DOI"), "title": citation.get("title"),
                           "journal": citation.get("journal"), "year": citation.get("publicationDate"),
                           "cited_for": reference.get("referencePositions", []),
                           "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"})
    protein = record.get("proteinDescription", {})
    recommended = protein.get("recommendedName") or next(iter(protein.get("submissionNames", [])), {})
    names = []
    for gene in record.get("genes", []):
        names.append({"primary": gene.get("geneName", {}).get("value"),
                      "synonyms": [row["value"] for row in gene.get("synonyms", [])],
                      "locus_names": [row["value"] for row in gene.get("orderedLocusNames", [])]})
    return {"accession": accession, "entry_id": record.get("uniProtkbId"),
            "protein_name": recommended.get("fullName", {}).get("value"),
            "genes": names, "organism": record.get("organism"),
            "reviewed": record.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
            "length": record.get("sequence", {}).get("length"),
            "protein_existence": record.get("proteinExistence"), "annotation_score": record.get("annotationScore"),
            "functions": functions, "cautions": cautions,
            "annotations": [c for c in comments if c.get("commentType") not in {"FUNCTION", "CAUTION", "SEQUENCE CAUTION"}],
            "features": features[:100], "features_truncated": len(features) > 100,
            "go_annotations": go[:100], "go_annotations_truncated": len(go) > 100,
            "references": references[:100], "references_truncated": len(references) > 100,
            "warnings": [] if functions else ["No FUNCTION annotation in UniProt; do not infer a function from the gene name"],
            "source_url": source_url, "record_url": f"{BASE}/uniprotkb/{accession}.json"}


async def uniprot_function(gene: str, taxon_id: int | None = None, reviewed_only: bool = True,
                           limit: int = 5) -> dict:
    """Find a gene's curated function, cautions, GO terms, features and supporting publications.

    Example: gene="MYB52", taxon_id=3702 (Arabidopsis thaliana).
    Uses exact gene-name/alias matching, then reads full UniProt entries so CAUTION
    and contradictory phenotype evidence are preserved. taxon_id is the NCBI taxid.
    Without an organism, return candidates and require species selection rather than
    assuming human or combining ortholog functions. reviewed_only=False includes
    unreviewed entries, whose claims may be predicted. At most five entries are read.
    Original annotation language and evidence codes are retained for faithful summaries.
    """
    gene = identifier(gene, r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", "gene symbol")
    bounded(limit, 5)
    if not isinstance(reviewed_only, bool):
        raise ValueError("reviewed_only must be boolean")
    clauses = [f'gene_exact:"{gene}"']
    if taxon_id is not None:
        clauses.append(f"organism_id:{bounded(taxon_id, 10_000_000, 'taxon_id')}")
    if reviewed_only:
        clauses.append("reviewed:true")
    search = await uniprot_search(" AND ".join(clauses), limit=limit)
    rows = search["results"][:limit]
    total_value = search.get("total")
    total = int(total_value) if total_value is not None and str(total_value).isdigit() else None
    results = await asyncio.gather(*(uniprot_entry(row["primaryAccession"]) for row in rows),
                                   return_exceptions=True)
    entries, errors = [], []
    for row, result in zip(rows, results):
        if isinstance(result, Exception):
            errors.append({"accession": row["primaryAccession"], "type": type(result).__name__,
                           "message": "Full UniProt entry could not be retrieved"})
        else:
            entries.append(_function_summary(result["record"]))
    truncated = bool(search.get("next_url")) or (total is not None and total > len(rows))
    selection_required = bool(rows) and (taxon_id is None or len(rows) > 1 or truncated)
    warnings = []
    if taxon_id is None:
        warnings.append("Organism unspecified; choose a species before attributing a function to the gene")
    if not rows:
        warnings.append("No matching entries; check gene/species or set reviewed_only=False to include unreviewed records")
    elif selection_required:
        warnings.append("Candidate entries are separate records; their functions must not be merged")
    return {"gene": gene, "taxon_id": taxon_id, "reviewed_only": reviewed_only,
            "query": " AND ".join(clauses), "total": total, "returned": len(entries),
            "selection_required": selection_required,
            "selected_accession": entries[0]["accession"] if len(entries) == 1 and not selection_required and not errors else None,
            "entries": entries, "partial": bool(errors), "errors": errors, "warnings": warnings,
            "truncated": truncated, "next_url": search.get("next_url"), "source_url": search["source_url"]}


async def uniprot_sequence(accession: str) -> dict:
    """Retrieve one protein/isoform sequence in FASTA format."""
    accession = _accession(accession)
    url = f"{BASE}/uniprotkb/{accession}.fasta"
    return {"accession": accession, "fasta": (await request("GET", url)).text, "source_url": url}


async def uniprot_mapping_submit(ids: list[str], from_database: str = "GeneID",
                                 to_database: str = "UniProtKB", taxon_id: int | None = None) -> dict:
    """Submit up to 1000 IDs. Database codes follow UniProt ID Mapping configuration."""
    values = identifiers(ids)
    if any("," in value or any(c.isspace() for c in value) for value in values):
        raise ValueError("Each ID must be one identifier without commas or whitespace")
    data = {"ids": ",".join(values), "from": identifier(from_database), "to": identifier(to_database)}
    if taxon_id is not None:
        data["taxId"] = str(bounded(taxon_id, 10_000_000, "taxon_id"))
    url = f"{BASE}/idmapping/run"
    return {**(await request("POST", url, data=data)).json(), "source_url": url}


async def uniprot_mapping_status(job_id: str) -> dict:
    """Check one mapping job without polling; results/failedIds mean the job is ready."""
    url = f"{BASE}/idmapping/status/{_job(job_id)}"
    result = await get_json(url)
    return {"job_id": job_id, "jobStatus": result.get("jobStatus", "FINISHED"),
            "results": bool(result.get("results")), "failed_count": len(result.get("failedIds", [])),
            "source_url": url}


async def uniprot_mapping_results(job_id: str, limit: int = 100, cursor: str | None = None) -> dict:
    """Retrieve one bounded page of a completed ID-mapping job, preserving failed IDs."""
    params = {"format": "json", "size": bounded(limit, 500)}
    if cursor is not None:
        params["cursor"] = text(cursor, "cursor", 2000)
    response = await request("GET", f"{BASE}/idmapping/results/{_job(job_id)}", params=params)
    result = response.json()
    rows = []
    for row in result.get("results", [])[:limit]:
        target = row.get("to")
        if isinstance(target, dict) and "primaryAccession" in target:
            target = {k: target[k] for k in ("primaryAccession", "uniProtkbId") if k in target}
        rows.append({"from": row.get("from"), "to": target})
    return {**result, "results": rows, "next_url": response.links.get("next", {}).get("url"),
            "source_url": str(response.url)}


TOOLS = (
    uniprot_search,
    uniprot_entry,
    uniprot_function,
    uniprot_sequence,
    uniprot_mapping_submit,
    uniprot_mapping_status,
    uniprot_mapping_results,
)


RESOURCES = ()
