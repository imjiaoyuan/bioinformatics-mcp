"""UniProtKB search, annotated records, sequences and asynchronous ID mapping."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.http import bounded, get_json, identifier, identifiers, request, text

mcp = FastMCP("uniprot")
BASE = "https://rest.uniprot.org"
FIELDS = "accession,id,protein_name,gene_names,organism_name,length,cc_function,cc_subcellular_location"


def _accession(value: str) -> str:
    return identifier(value.upper(), r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})(?:-[0-9]+)?", "UniProt accession")


def _job(value: str) -> str:
    return identifier(value, r"[A-Za-z0-9_-]{1,100}", "mapping job ID")


@mcp.tool()
async def uniprot_search(query: str, limit: int = 20, cursor: str | None = None) -> dict:
    """Search UniProtKB, e.g. organism_id:4530 AND protein_name:heat; return next-page link."""
    params = {"query": text(query), "format": "json", "size": bounded(limit), "fields": FIELDS}
    if cursor is not None:
        params["cursor"] = text(cursor, "cursor", 2000)
    response = await request("GET", f"{BASE}/uniprotkb/search", params=params)
    return {"results": response.json().get("results", []), "total": response.headers.get("x-total-results"),
            "next_url": response.links.get("next", {}).get("url"), "source_url": str(response.url)}


@mcp.tool()
async def uniprot_entry(accession: str) -> dict:
    """Get a UniProtKB record including functional comments, locations and cross-references."""
    accession = _accession(accession)
    url = f"{BASE}/uniprotkb/{accession}.json"
    return {"record": await get_json(url), "source_url": url}


@mcp.tool()
async def uniprot_sequence(accession: str) -> dict:
    """Retrieve one protein/isoform sequence in FASTA format."""
    accession = _accession(accession)
    url = f"{BASE}/uniprotkb/{accession}.fasta"
    return {"accession": accession, "fasta": (await request("GET", url)).text, "source_url": url}


@mcp.tool()
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


@mcp.tool()
async def uniprot_mapping_status(job_id: str) -> dict:
    """Check one mapping job without polling; results/failedIds mean the job is ready."""
    url = f"{BASE}/idmapping/status/{_job(job_id)}"
    result = await get_json(url)
    return {"job_id": job_id, "jobStatus": result.get("jobStatus", "FINISHED"),
            "results": bool(result.get("results")), "failed_count": len(result.get("failedIds", [])),
            "source_url": url}


@mcp.tool()
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
