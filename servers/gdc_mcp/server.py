"""Public NCI GDC projects, cases and file discovery, including TCGA."""
from __future__ import annotations

import csv
import io
import json

from mcp.server.fastmcp import FastMCP

from common.api import choice, json_response, page
from common.http import identifier, identifiers, text

mcp = FastMCP("gdc")
BASE = "https://api.gdc.cancer.gov"
FILE_FIELDS = "file_id,file_name,file_size,md5sum,state,access,data_type,data_category,data_format,analysis.workflow_type,cases.case_id,cases.submitter_id,cases.project.project_id,cases.samples.submitter_id,cases.samples.sample_type"


def _uuid(value: str) -> str:
    return identifier(value.lower(), r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "file UUID")


def _filters(values: dict) -> dict:
    return {"op": "and", "content": [
        {"op": "in", "content": {"field": field, "value": [text(value, field)]}}
        for field, value in values.items() if value is not None]}


async def _search(endpoint: str, filters: dict, fields: str, limit: int, offset: int,
                  expand: str | None = None) -> dict:
    paging = page(limit, offset)
    params = {"size": limit, "from": offset, "fields": fields, "format": "JSON"}
    if filters["content"]:
        params["filters"] = json.dumps(filters)
    if expand is not None:
        params["expand"] = expand
    data, source = await json_response(f"{BASE}/{endpoint}", params)
    result = data["data"]
    total = result["pagination"]["total"]
    return {**source, **paging, "results": result["hits"], "total": total,
            "truncated": offset + len(result["hits"]) < total,
            "pagination": result["pagination"], "warnings": data.get("warnings", {})}


@mcp.tool()
async def gdc_projects(program: str | None = "TCGA", primary_site: str | None = None,
                       limit: int = 20, offset: int = 0) -> dict:
    """List projects, optionally filtered by program and primary site."""
    return await _search("projects", _filters({"program.name": program, "primary_site": primary_site}),
                         "project_id,name,program.name,primary_site,disease_type", limit, offset)


@mcp.tool()
async def gdc_cases(project_id: str, sample_type: str | None = None,
                    limit: int = 20, offset: int = 0) -> dict:
    """Retrieve case, demographic, diagnosis and sample metadata for a project."""
    project_id = identifier(project_id)
    return await _search("cases", _filters({"project.project_id": project_id,
                         "samples.sample_type": sample_type}),
                         "case_id,submitter_id,project.project_id", limit, offset,
                         expand="demographic,diagnoses,samples")


@mcp.tool()
async def gdc_files(project_id: str, data_type: str | None = None,
                    workflow: str | None = None, access: str = "open",
                    limit: int = 20, offset: int = 0) -> dict:
    """Find files; file counts do not represent distinct patients or samples."""
    choice(access, {"open", "controlled"}, "access")
    return await _search("files", _filters({"cases.project.project_id": identifier(project_id),
                         "data_type": data_type, "analysis.workflow_type": workflow,
                         "access": access}), FILE_FIELDS, limit, offset)


@mcp.tool()
async def gdc_file(file_id: str) -> dict:
    """Read file metadata and sample/aliquot relationships without downloading data."""
    data, source = await json_response(f"{BASE}/files/{_uuid(file_id)}",
                                      {"expand": "cases.samples.portions.analytes.aliquots"})
    return {**source, **data}


@mcp.tool()
async def gdc_manifest(file_ids: list[str]) -> dict:
    """Build a TSV manifest for at most 100 file UUIDs; report unresolved IDs."""
    ids = list(dict.fromkeys(_uuid(value) for value in identifiers(file_ids, 100)))
    filters = {"op": "and", "content": [{"op": "in", "content": {"field": "file_id", "value": ids}}]}
    result = await _search("files", filters, FILE_FIELDS, 100, 0)
    rows = result["results"]
    out = io.StringIO()
    writer = csv.writer(out, delimiter="\t", lineterminator="\n")
    writer.writerow(["id", "filename", "md5", "size", "state"])
    for row in rows:
        writer.writerow([row["file_id"], row["file_name"], row.get("md5sum", ""), row.get("file_size", ""), row.get("state", "")])
    return {**result, "manifest": out.getvalue(),
            "missing_ids": sorted(set(ids) - {r["file_id"] for r in rows})}


@mcp.tool()
async def gdc_download_url(file_id: str) -> dict:
    """Return the data endpoint only after verifying that the file is open access."""
    file_id = _uuid(file_id)
    result = await gdc_file(file_id)
    if result["data"].get("access") != "open":
        raise ValueError("This file is controlled access; authorized GDC download tooling is required")
    return {**result, "download_url": f"{BASE}/data/{file_id}"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
