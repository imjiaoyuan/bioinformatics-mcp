from __future__ import annotations

import httpx
from urllib.parse import urlencode
from mcp.server.fastmcp import FastMCP

from common.http import bounded, get_json, identifier, text
from common.cncb import search_payload

mcp = FastMCP("cncb-ngdc")
BASE = "https://ngdc.cncb.ac.cn/gwh/api/public"
NGDC = "https://ngdc.cncb.ac.cn"
BIG_SEARCH = "https://ngdc.cncb.ac.cn/search/api/specific"

# Searchable BIG Search database ids that hold biology data records; the full
# NGDC list has 102 ids including literature and tools not useful here.
SEARCHABLE_DATABASES = {
    "gsa": "GSA raw reads and submitted data",
    "gwh": "Genome Warehouse assemblies",
    "bioproject": "BioProject studies",
    "biosample": "BioSample specimens",
    "omix": "OmicsGear processed omics data",
    "hra": "Human Ribosomal RNA atlas",
    "gvm": "Genome Variation Map",
    "gwas": "GWAS Atlas",
    "methbank": "MethBank epigenomes",
    "lncbook": "LncBook non-coding RNA",
}


def _digits(value: str) -> str:
    return identifier(value.strip(), r"[1-9][0-9]{0,11}", "numeric genome ID")


def _accession(value: str) -> str:
    return identifier(value.strip().upper(), r"(?:GWH_[A-Z]+[0-9]{2,}|PRJ[CN][0-9]+|SAM[CEN][0-9]+|SAMN[0-9]+|[A-Z]{2}[0-9]{6,}(?:\.[0-9]+)?)", "accession")


def _genbase(value: str) -> str:
    return identifier(value.strip().upper(), r"[A-Z]{2}_?[0-9]{5,}(?:\.[0-9]+)?", "GenBase accession")


async def _get(path: str):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(BASE + path); r.raise_for_status(); return r.json()


async def _get_url(url: str, params: dict | None = None):
    return await get_json(url, params)


@mcp.tool()
async def cncb_genome(genome_id: str) -> dict:
    """Get a Genome Warehouse genome record by numeric ID."""
    return await _get(f"/genome/{_digits(genome_id)}")

@mcp.tool()
async def cncb_assembly(accession: str) -> dict:
    """Get a GWH assembly record by accession."""
    return await _get(f"/assembly/{_accession(accession)}")

@mcp.tool()
async def cncb_bioproject(accession: str) -> dict:
    """Get a GWH BioProject record by accession."""
    return await _get(f"/bioProject/{_accession(accession)}")

@mcp.tool()
async def cncb_biosample(accession: str) -> dict:
    """Get a GWH BioSample record by accession."""
    return await _get(f"/bioSample/{_accession(accession)}")

@mcp.tool()
async def cncb_genbase_fasta(accession: str) -> dict:
    """Retrieve a nucleotide or protein sequence from CNCB GenBase as FASTA."""
    accession = _genbase(accession)
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.get(f"{NGDC}/genbase/api/file/fasta", params={"acc": accession})
        r.raise_for_status()
    return {"accession": accession, "fasta": r.text}

@mcp.tool()
async def cncb_icg_record(record_type: str, accession: str) -> dict:
    """Get an Internal Control Genes (ICG) species, project, gene, or publication record."""
    paths = {"species": "species", "project": "project", "gene": "gene", "publication": "publication"}
    if record_type not in paths:
        raise ValueError("record_type must be species, project, gene, or publication")
    return await _get_url(f"{NGDC}/icg/api/json/{paths[record_type]}/{_accession(accession)}")

@mcp.tool()
async def cncb_search(query: str, database: str = "gsa", limit: int = 10) -> dict:
    """Keyword-search CNCB-NGDC records (BIG Search), e.g. GSA raw-data studies.

    Use this to find Chinese-archive submissions that do not always appear in
    NCBI/ENA: query with species or keywords like "rice", "hepatocellular",
    or an accession such as PRJCA000126. Returns accessions (CRA runs,
    GWH genomes, PRJCA projects, SAMC samples), titles, types and record URLs.
    """
    query = text(query, maximum=200)
    database = database.strip().lower()
    if database not in SEARCHABLE_DATABASES:
        raise ValueError(f"Unsupported database {database!r}; choose from {sorted(SEARCHABLE_DATABASES)}")
    bounded(limit)
    data = await _get_url(BIG_SEARCH, params={"db": database, "q": query,
                                              "start": 0, "length": limit})
    rows, total = search_payload(data)
    records = [{"id": row.get("id"), "type": row.get("type"), "title": row.get("title"),
                "url": row.get("url"), "db": row.get("dbId")} for row in rows]
    return {"query": query, "database": database, "count": total,
            "records": records, "returned": len(records),
            "source_url": f"{NGDC}/search/specific?" + urlencode({"db": database, "q": query})}


@mcp.tool()
async def cncb_database_catalog() -> dict:
    """Return the official CNCB-NGDC database directory URL and major categories."""
    return {"url": f"{NGDC}/databases", "organization": "CNCB-NGDC",
            "categories": ["raw data", "genome and variation", "gene expression", "non-coding RNA",
                            "epigenome", "single-cell", "biodiversity", "health and disease", "literature and tools"]}

def main() -> None: mcp.run()
if __name__ == "__main__": main()
