"""ENA study, sample and run search with FASTQ download metadata."""
from __future__ import annotations

from urllib.parse import urlencode

from mcp.server.fastmcp import FastMCP

from common.http import bounded, get_json, identifier, request, text

mcp = FastMCP("ena")
BASE = "https://www.ebi.ac.uk/ena/portal/api"
RESULTS = {"read_run", "read_study", "read_experiment", "sample", "study", "assembly"}
RUN_FIELDS = "run_accession,study_accession,sample_accession,scientific_name,library_strategy,library_layout,fastq_ftp,fastq_md5,fastq_bytes"


def _result(result: str) -> str:
    if result not in RESULTS:
        raise ValueError(f"result must be one of {sorted(RESULTS)}")
    return result


def _accession(accession: str) -> str:
    return identifier(accession.upper(), r"(?:[SED]R[APRSX][0-9]+|PRJ(?:NA|EB|DB|DA|EA)[0-9]+|SAM[END][A-Z]?[0-9]+)", "ENA accession")


@mcp.tool()
async def ena_search(query: str, result: str = "read_run", limit: int = 20, offset: int = 0) -> dict:
    """Search ENA with Portal query syntax, e.g. tax_tree(4530) AND library_strategy=\"RNA-Seq\"."""
    params = {"query": text(query), "result": _result(result), "format": "json",
              "limit": bounded(limit), "offset": bounded(offset, 100000, "offset", 0)}
    if result == "read_run":
        params["fields"] = RUN_FIELDS
    records = await get_json(f"{BASE}/search", params)
    return {"records": records, "source_url": f"{BASE}/search?{urlencode(params)}"}


@mcp.tool()
async def ena_record(accession: str) -> dict:
    """Retrieve the public ENA XML record for a study, sample, experiment or run."""
    accession = _accession(accession)
    url = f"https://www.ebi.ac.uk/ena/browser/api/xml/{accession}"
    response = await request("GET", url)
    return {"accession": accession, "xml": response.text, "source_url": url}


@mcp.tool()
async def ena_fastq(accession: str, limit: int = 20) -> dict:
    """List public run FASTQ URLs, MD5 checksums and byte sizes; do not download reads."""
    accession = _accession(accession)
    params = {"accession": accession, "result": "read_run", "fields": RUN_FIELDS,
              "format": "json", "limit": bounded(limit)}
    records = await get_json(f"{BASE}/filereport", params)
    runs = []
    for record in records[:limit]:
        row = dict(record)
        paths = (row.get("fastq_ftp") or "").split(";")
        checksums = (row.get("fastq_md5") or "").split(";")
        sizes = (row.get("fastq_bytes") or "").split(";")
        row["files"] = [{"url": path if path.startswith("https://") else "https://" + path.removeprefix("ftp://"),
                         "md5": checksums[i] if i < len(checksums) else None,
                         "bytes": int(sizes[i]) if i < len(sizes) and sizes[i].isdigit() else None}
                        for i, path in enumerate(paths) if path]
        runs.append(row)
    return {"accession": accession, "runs": runs,
            "source_url": f"{BASE}/filereport?{urlencode(params)}"}


@mcp.tool()
async def ena_fields(result: str = "read_run") -> dict:
    """List supported ENA search fields for a record type."""
    params = {"result": _result(result), "format": "json"}
    return {"fields": await get_json(f"{BASE}/searchFields", params),
            "source_url": f"{BASE}/searchFields?{urlencode(params)}"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
