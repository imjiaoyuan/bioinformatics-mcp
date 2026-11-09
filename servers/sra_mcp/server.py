"""NCBI SRA run metadata search via Entrez esearch/esummary.

Overlaps with the ncbi (general Entrez) and ena (ENA Portal API) servers: use
this server for SRA-specific run/experiment summaries parsed from Entrez
docsums, the ncbi server for other Entrez databases, and the ena server for
ENA-native metadata and accession reports.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

from common.api import page
from common.http import identifier, request, text
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("sra")
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _config() -> dict[str, str]:
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    config = {"email": email, "tool": "sra-mcp"}
    if api_key := os.environ.get("NCBI_API_KEY"):
        config["api_key"] = api_key
    return config


def _run_accession(value: str) -> str:
    return identifier(value.upper(), r"(?:SRR|ERR|DRR)[0-9]+", "SRA run accession")


async def _get(endpoint: str, params: dict[str, Any]) -> dict:
    """GET one E-utility endpoint with a polite interval and traceable URL."""
    # Stay below the unauthenticated NCBI limit; API-key users can go faster.
    interval = 0.11 if "api_key" in (config := _config()) else 0.35
    response = await request("GET", f"{BASE}/{endpoint}.fcgi",
                             params={**params, **config, "retmode": "json"},
                             interval=interval)
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    return {**data, "source_url": str(response.url)}


async def _search_ids(term: str, limit: int, offset: int) -> tuple[str, list[str]]:
    data = await _get("esearch", {"db": "sra", "term": term, **page(limit, offset)})
    result = data.get("esearchresult", {})
    return result.get("count", "0"), result.get("idlist", [])


def _parse_xml(fragment: str) -> dict[str, Any] | None:
    """Parse one upstream docsum XML fragment into attributes and text."""
    try:
        root = ET.fromstring(fragment.strip())
    except ET.ParseError:
        return None
    parsed: dict[str, Any] = {k: v for k, v in root.attrib.items()}
    if root.text and root.text.strip():
        parsed["text"] = root.text.strip()
    for child in root:
        entry: dict[str, Any] = dict(child.attrib)
        if child.text and child.text.strip():
            entry["text"] = child.text.strip()
        parsed.setdefault(child.tag, []).append(entry)
    return parsed


def _summarize(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract SRA docsum fields; expxml and runs carry nested XML fragments."""
    record: dict[str, Any] = {"uid": summary.get("uid"),
                              "createdate": summary.get("createdate"),
                              "updatedate": summary.get("updatedate")}
    if expxml := _parse_xml(summary.get("expxml", "")):
        record.update({"title": expxml.get("text"),
                      "platform": expxml.get("Platform"),
                      "instrument_model": expxml.get("instrument_model"),
                      "experiment": expxml.get("Experiment"),
                      "study": expxml.get("Study"),
                      "sample": expxml.get("Sample"),
                      "organism": expxml.get("Organism"),
                      "bioproject": expxml.get("Bioproject"),
                      "biosample": expxml.get("Biosample"),
                      "library": expxml.get("Library_descriptor"),
                      "submitter": expxml.get("Submitter"),
                      "statistics": expxml.get("Statistics")})
    record["runs"] = [run for run in (_parse_xml(line) for line in
                                      (summary.get("runs", "").replace("><", ">\n<").splitlines()))
                      if run and "acc" in run]
    return record


@mcp.tool()
async def sra_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search NCBI SRA runs/experiments with Entrez syntax; return matching UIDs and counts.

    Use standard SRA fields such as ``organism="Homo sapiens"`` or
    ``strategy[Filter]``; combine terms with AND/OR.
    """
    count, ids = await _search_ids(text(query), limit, offset)
    return {"query": query, "count": int(count), "uids": ids,
            "source_url": f"{BASE}/esearch.fcgi?db=sra&term={quote(query)}"}


@mcp.tool()
async def sra_run_metadata(run_accession: str) -> dict:
    """Retrieve metadata for one SRA/ERA/DRA run accession (SRR/ERR/DRR).

    Returns study, experiment, sample, organism, library layout, statistics
    and contained runs; sequence data is not downloaded.
    """
    accession = _run_accession(run_accession)
    _, uids = await _search_ids(accession, 1, 0)
    if not uids:
        raise ValueError(f"No SRA record found for run accession {accession}")
    data = await _get("esummary", {"db": "sra", "id": uids[0]})
    summary = data.get("result", {}).get(uids[0])
    if not summary:
        raise RuntimeError(f"SRA returned no docsum for {accession}")
    return {**_summarize(summary), "run_accession": accession, "source_url": data["source_url"]}


@mcp.tool()
async def sra_studies(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Search SRA and group matching records into distinct studies (SRP/ERP/DRP).

    Returns one entry per study with organism and experiment counts; runs are
    not returned here, use sra_search or sra_run_metadata for those.
    """
    count, uids = await _search_ids(text(query), limit, offset)
    studies: dict[str, dict[str, Any]] = {}
    if uids:
        data = await _get("esummary", {"db": "sra", "id": ",".join(uids)})
        result = data.get("result", {})
        for uid in uids:
            summary = result.get(uid)
            if not summary:
                continue
            record = _summarize(summary)
            study = (record.get("study") or [{}])[0]
            accession = study.get("acc")
            if not accession:
                continue
            entry = studies.setdefault(accession, {"study_accession": accession,
                                                   "title": study.get("name"),
                                                   "organisms": set(), "experiments": set()})
            if organisms := record.get("organism"):
                entry["organisms"].update(o.get("ScientificName") for o in organisms)
            if experiments := record.get("experiment"):
                entry["experiments"].update(e.get("acc") for e in experiments)
    rows = [{"study_accession": entry["study_accession"], "title": entry["title"],
             "organisms": sorted(name for name in entry["organisms"] if name),
             "experiments": sorted(entry["experiments"])}
            for entry in studies.values()]
    return {**page(limit, offset), "query": query, "count": int(count), "total": len(rows),
            "results": rows, "truncated": offset + limit < len(rows), "pagination": "local",
            "source_url": f"{BASE}/esearch.fcgi?db=sra&term={quote(query)}"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
