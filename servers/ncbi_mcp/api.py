"""MCP server exposing safe, structured NCBI Entrez operations."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import time
import re
import shlex
import xml.etree.ElementTree as ET
from dataclasses import replace
from html.parser import HTMLParser
from collections import OrderedDict
from typing import Any
from urllib.parse import quote_plus
from urllib.parse import urlencode
from urllib.parse import urljoin
from urllib.parse import quote

from common.http import bounded, identifier, identifiers, request, text
from common.ena import RUN_FIELDS as ENA_RUN_FIELDS, files_from_record
from common.geo import soft_samples
from common.cncb import search_payload
from common.sample_matching import condition_query_terms, tissue_query_terms
from common.discovery import (Filters, filters as discovery_filters, assess, pair_candidates,
                              ena_query, ena_literal, platform_clause)

import httpx

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ALLOWED_DATABASES = {
    "pubmed", "pmc", "gene", "protein", "nuccore", "nucleotide", "sra",
    "assembly", "bioproject", "biosample", "clinvar", "omim", "taxonomy",
    "gds", "geoprofiles",
}
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def _config() -> tuple[str, str, str | None]:
    email = os.getenv("NCBI_EMAIL")
    tool = os.getenv("NCBI_TOOL", "ncbi-mcp")
    api_key = os.getenv("NCBI_API_KEY")
    if not email:
        raise ValueError("NCBI_EMAIL must be set (for example researcher@example.org)")
    return email, tool, api_key


async def _request(endpoint: str, params: dict[str, Any], *, ttl: int = 300) -> Any:
    email, tool, api_key = _config()
    params = {**params, "email": email, "tool": tool, "retmode": "json"}
    if api_key:
        params["api_key"] = api_key
    key = endpoint + "?" + urlencode(sorted((k, str(v)) for k, v in params.items()))
    now = time.monotonic()
    if key in _cache and now - _cache[key][0] < ttl:
        return _cache[key][1]
    response = await request("GET", f"{BASE_URL}/{endpoint}", params=params,
                             interval=0.11 if api_key else 0.35)
    data = response.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"NCBI error: {data['error']}")
    _cache[key] = (time.monotonic(), data)
    _cache.move_to_end(key)
    while len(_cache) > 256:
        _cache.popitem(last=False)
    return data


def _db(database: str) -> str:
    database = database.lower().strip()
    if database not in ALLOWED_DATABASES:
        raise ValueError(f"Unsupported database {database!r}; choose from {sorted(ALLOWED_DATABASES)}")
    return database


async def ncbi_search(database: str, query: str, max_results: int = 20, offset: int = 0) -> dict[str, Any]:
    """Search an NCBI Entrez database using its query syntax and return IDs."""
    database = _db(database)
    max_results = max(1, min(max_results, 1000))
    bounded(offset, 100000, "offset", 0)
    data = await _request("esearch.fcgi", {
        "db": database, "term": query, "retmax": max_results, "retstart": offset, "usehistory": "n",
    })
    result = data.get("esearchresult", {})
    return {"database": database, "query": query, "count": int(result.get("count", 0)),
            "ids": result.get("idlist", []), "translation": result.get("querytranslation")}


async def ncbi_summary(database: str, ids: list[str]) -> dict[str, Any]:
    """Return compact metadata for up to 200 IDs from an NCBI database."""
    database = _db(database)
    if not ids or len(ids) > 200:
        raise ValueError("ids must contain between 1 and 200 identifiers")
    data = await _request("esummary.fcgi", {"db": database, "id": ",".join(ids)})
    return {"database": database, "result": data.get("result", {})}


async def ncbi_fetch(database: str, ids: list[str], format: str = "json") -> dict[str, Any]:
    """Fetch records. Use json/xml for metadata, fasta for sequence records."""
    database = _db(database)
    format = format.lower()
    if format not in {"json", "xml", "fasta", "gb", "gbwithparts"}:
        raise ValueError("format must be json, xml, fasta, gb, or gbwithparts")
    if not ids or len(ids) > 100:
        raise ValueError("ids must contain between 1 and 100 identifiers")
    params = {"db": database, "id": ",".join(ids), "rettype": format if format != "json" else "docsum", "retmode": format if format in {"xml", "json"} else "text"}
    # efetch often returns text, so bypass the JSON helper for non-JSON formats.
    if format == "json":
        return {"database": database, "records": await _request("efetch.fcgi", params)}
    email, tool, api_key = _config()
    params.update(email=email, tool=tool)
    if api_key: params["api_key"] = api_key
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.get(f"{BASE_URL}/efetch.fcgi", params=params)
    response.raise_for_status()
    return {"database": database, "format": format, "content": response.text}


async def ncbi_link(database: str, ids: list[str], target_database: str) -> dict[str, Any]:
    """Find related records in another Entrez database."""
    database, target_database = _db(database), _db(target_database)
    if not ids or len(ids) > 200:
        raise ValueError("ids must contain between 1 and 200 identifiers")
    data = await _request("elink.fcgi", {"db": target_database, "dbfrom": database, "id": ",".join(ids)})
    return {"database": database, "target_database": target_database, "result": data.get("linksets", [])}


async def pubmed_search(
    query: str,
    max_results: int = 20,
    min_date: str | None = None,
    max_date: str | None = None,
    sort: str = "relevance",
    include_summaries: bool = True,
) -> dict[str, Any]:
    """Search PubMed and optionally return citation metadata.

    Dates use YYYY/MM/DD, YYYY/MM, or YYYY format. The query may use normal
    PubMed syntax, for example ``TP53[Title/Abstract] AND review[pt]``.
    """
    max_results = max(1, min(max_results, 200))
    sort = sort if sort in {"relevance", "pub date", "first author", "journal name"} else "relevance"
    params: dict[str, Any] = {
        "db": "pubmed", "term": query, "retmax": max_results,
        "sort": sort, "usehistory": "n",
    }
    if min_date:
        params.update({"mindate": min_date, "datetype": "pdat"})
    if max_date:
        params.update({"maxdate": max_date, "datetype": "pdat"})
    data = await _request("esearch.fcgi", params)
    result = data.get("esearchresult", {})
    ids = result.get("idlist", [])
    response: dict[str, Any] = {
        "query": query, "count": int(result.get("count", 0)), "ids": ids,
        "query_translation": result.get("querytranslation"),
    }
    if include_summaries and ids:
        summary = await ncbi_summary("pubmed", ids)
        response["articles"] = summary["result"]
    return response


async def pubmed_citations(pmids: list[str], include_abstracts: bool = False) -> dict[str, Any]:
    """Fetch citation metadata for PMIDs, optionally including XML abstracts."""
    if not pmids or len(pmids) > 100:
        raise ValueError("pmids must contain between 1 and 100 PMIDs")
    summary = await ncbi_summary("pubmed", pmids)
    response: dict[str, Any] = {"pmids": pmids, "articles": summary["result"]}
    if include_abstracts:
        response["abstract_xml"] = (await ncbi_fetch("pubmed", pmids, "xml"))["content"]
    return response


# Common organism aliases mapped to the scientific names GEO indexes.
_ORGANISM_ALIASES = {
    "human": "Homo sapiens",
    "mouse": "Mus musculus",
    "rat": "Rattus norvegicus",
    "arabidopsis": "Arabidopsis thaliana",
    "rice": "Oryza sativa",
    "zebrafish": "Danio rerio",
    "fruit fly": "Drosophila melanogaster",
    "fly": "Drosophila melanogaster",
    "worm": "Caenorhabditis elegans",
    "yeast": "Saccharomyces cerevisiae",
    "maize": "Zea mays",
    "pig": "Sus scrofa",
    "chicken": "Gallus gallus",
    "ecoli": "Escherichia coli",
    "poplar": "Populus",
    "populus": "Populus",
    "杨树": "Populus",
    "human tissue": "Homo sapiens",
    "人类": "Homo sapiens",
}

# Biology-oriented data-type options mapped to GEO keyword clauses.
GEO_DATA_TYPES = {
    "wgs": '("whole genome sequencing"[All Fields] OR WGS[All Fields])',
    "wes": '("whole exome sequencing"[All Fields] OR WES[All Fields] OR exome[All Fields])',
    "rna_seq": '("RNA-Seq"[All Fields] OR "bulk RNA"[All Fields])',
    "long_reads": '(("long read"[All Fields] OR "long-read"[All Fields] OR "long reads"[All Fields])'
                  ' AND (transcriptome[All Fields] OR RNA[All Fields] OR sequencing[All Fields]))',
    "hifi": '(("PacBio"[All Fields] OR "HiFi"[All Fields] OR "high-fidelity"[All Fields])'
            ' AND ("long read"[All Fields] OR "long-read"[All Fields] OR HiFi[All Fields]))',
    "ont": '("Oxford Nanopore"[All Fields] OR "Nanopore"[All Fields] OR ONT[All Fields])',
    "scrna": '(("single cell"[All Fields] OR "single-cell"[All Fields]) AND RNA[All Fields]'
             ' AND (scRNA[All Fields] OR "10x"[All Fields] OR "Smart-seq"[All Fields]'
             ' OR transcriptomic[All Fields] OR sequencing[All Fields]))',
    "snrna": '(("single nucleus"[All Fields] OR "single-nucleus"[All Fields] OR snRNA-seq[All Fields])'
             ' AND RNA[All Fields])',
    "spatial": '("spatial transcriptomic"[All Fields] OR "spatial transcriptomics"[All Fields]'
               ' OR Visium[All Fields] OR "Slide-seq"[All Fields] OR MERFISH[All Fields])',
    "atac": '("ATAC-seq"[All Fields] OR "ATAC"[All Fields] OR "chromatin accessibility"[All Fields])',
    "chip_seq": '("ChIP-seq"[All Fields] OR "ChIP"[All Fields])',
    "methylome": '("methylation"[All Fields] AND ("bisulfite"[All Fields] OR "EPIC"[All Fields]'
                 ' OR "450k"[All Fields] OR sequencing[All Fields]))',
    "proteomics": '("proteomic"[All Fields] OR "proteomics"[All Fields] OR "mass spectrometry"[All Fields])',
    "epigenomic": '("epigenomic"[All Fields] OR "epigenetics"[All Fields])',
}


def _free_text_clause(query: str) -> str:
    """Quote plain multi-word topics so GEO does not AND the words apart."""
    cleaned = text(query).strip()
    if " " in cleaned and not re.search(r'\[|["()]|\b(?:AND|OR|NOT)\b', cleaned):
        cleaned = f'"{cleaned}"'
    return cleaned


def _organism_clause(organism: str) -> str:
    """Normalize an organism query into GEO's [Organism] field syntax."""
    organism = text(organism).strip()
    if not organism:
        raise ValueError("organism must be a non-empty name such as 'human' or 'Homo sapiens'")
    scientific = _ORGANISM_ALIASES.get(organism.lower(), organism)
    return f'"{scientific}"[Organism]'


async def _taxid(organism: str) -> str:
    """Resolve an organism name/alias to an NCBI taxonomy id for SRA queries."""
    organism = text(organism).strip()
    if not organism:
        raise ValueError("organism must be a non-empty name such as 'human' or 'Homo sapiens'")
    scientific = _ORGANISM_ALIASES.get(organism.lower(), organism)
    found = await ncbi_search("taxonomy", f'{scientific}[Scientific Name] UNCLASSIFIED', 1)
    if not found["ids"]:
        found = await ncbi_search("taxonomy", f'"{scientific}"[Scientific Name]', 1)
    if not found["ids"]:
        raise ValueError(f"Unknown organism {organism!r}: no taxonomy entry for {scientific}")
    return found["ids"][0]


# SRA indexes exact fields; mirror the lrmcp approach of filtering on
# library strategy and instrument platform instead of guessing keywords.
SRA_STRATEGIES = {
    "wgs": "WGS", "wga": "WGA", "wxs": "WXS", "rna_seq": "RNA-Seq",
    "mirna_seq": "miRNA-Seq", "ncrna_seq": "ncRNA-Seq", "fl_cdna": "FL-cDNA",
    "est": "EST", "clone": "CLONE", "cloneend": "CLONEEND", "amplicon": "AMPLICON",
    "targeted_capture": "TARGETED-CAPTURE", "mre_seq": "MRE-Seq", "chip_seq": "ChIP-Seq",
    "dnase": "DNase-Hypersensitivity", "bisulfite": "Bisulfite-Seq", "other": "OTHER",
}
SRA_PLATFORMS = {
    "illumina": "ILLUMINA", "ion_torrent": "ION_TORRENT", "pacbio": "PACBIO_SMRT",
    "hifi": "PACBIO_SMRT", "ont": "OXFORD_NANOPORE", "nanopore": "OXFORD_NANOPORE",
    "solid": "ABI_SOLID", "bgiseq": "BGISEQ", "capillary": "CAPILLARY", "ls454": "LS454",
}
SRA_SOURCES = {
    "genomic": "GENOMIC", "transcriptomic": "TRANSCRIPTOMIC", "metagenomic": "METAGENOMIC",
    "metatranscriptomic": "METATRANSCRIPTOMIC", "synthetic": "SYNTHETIC",
    "epigenomic": "EPIGENOMIC", "other": "OTHER",
}

# Each find_data data type routes to both a GEO keyword clause and the best
# exact-field SRA clauses (strategy/platform) plus optional keyword narrowing.
FIND_DATA_TYPES: dict[str, dict[str, Any]] = {
    key: {"geo": clause} for key, clause in GEO_DATA_TYPES.items()
}
FIND_DATA_TYPES.update({
    "wgs": {"geo": GEO_DATA_TYPES["wgs"], "strategy": "WGS"},
    "wes": {"geo": GEO_DATA_TYPES["wes"], "strategy": "WXS"},
    "rna_seq": {"geo": GEO_DATA_TYPES["rna_seq"], "strategy": "RNA-Seq"},
    "long_reads": {"geo": GEO_DATA_TYPES["long_reads"],
                   "platform": "(PACBIO_SMRT[Platform] OR OXFORD_NANOPORE[Platform])"},
    "hifi": {"geo": GEO_DATA_TYPES["hifi"], "platform": "PACBIO_SMRT[Platform]",
             "keywords": '("HiFi"[All Fields] OR "high-fidelity"[All Fields] OR CCS[All Fields])'},
    "ont": {"geo": GEO_DATA_TYPES["ont"], "platform": "OXFORD_NANOPORE[Platform]"},
    "scrna": {"geo": GEO_DATA_TYPES["scrna"], "strategy": "RNA-Seq",
              "keywords": '("single cell"[All Fields] OR "single-cell"[All Fields] OR scRNA[All Fields])'},
    "snrna": {"geo": GEO_DATA_TYPES["snrna"], "strategy": "RNA-Seq",
              "keywords": '("single nucleus"[All Fields] OR "single-nucleus"[All Fields] OR snRNA[All Fields])'},
    "spatial": {"geo": GEO_DATA_TYPES["spatial"], "strategy": "RNA-Seq",
                "keywords": '("spatial"[All Fields] AND (Visium[All Fields] OR MERFISH[All Fields]'
                            ' OR "Slide-seq"[All Fields]))'},
    "atac": {"geo": GEO_DATA_TYPES["atac"],
             "keywords": '("ATAC-seq"[All Fields] OR "ATAC"[All Fields])'},
    "chip_seq": {"geo": GEO_DATA_TYPES["chip_seq"], "strategy": "ChIP-Seq"},
    "methylome": {"geo": GEO_DATA_TYPES["methylome"], "strategy": "Bisulfite-Seq"},
})


async def sra_search(
    query: str = "",
    organism: str = "",
    strategy: str = "",
    platform: str = "",
    source: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Search NCBI SRA raw-read archives with exact structured fields.

    Args:
        query: Free-text condition/topic, e.g. "drought", "liver tumor".
        organism: Organism name or common alias ("human", "arabidopsis");
            resolved to an exact NCBI taxonomy id.
        strategy: Library strategy: wgs, wxs, rna_seq, chip_seq, bisulfite,
            targeted_capture, amplicon, fl_cdna, mirna_seq, ncrna_seq, ... .
        platform: Sequencing platform: illumina, pacbio, ont, ion_torrent,
            bgiseq, solid, ls454, capillary.
        source: Library source: genomic, transcriptomic, epigenomic,
            metagenomic, metatranscriptomic, synthetic, other.
    """
    clauses: list[str] = []
    if query.strip():
        clauses.append(_free_text_clause(query))
    if organism.strip():
        clauses.append(f'txid{await _taxid(organism)}[Organism]')
    if strategy.strip():
        key = strategy.strip().lower()
        if key not in SRA_STRATEGIES:
            raise ValueError(f"Unsupported strategy {strategy!r}; choose from {sorted(SRA_STRATEGIES)}")
        clauses.append(f'{SRA_STRATEGIES[key]}[Strategy]')
    if platform.strip():
        key = platform.strip().lower()
        if key not in SRA_PLATFORMS:
            raise ValueError(f"Unsupported platform {platform!r}; choose from {sorted(SRA_PLATFORMS)}")
        clauses.append(f'{SRA_PLATFORMS[key]}[Platform]')
    if source.strip():
        key = source.strip().lower()
        if key not in SRA_SOURCES:
            raise ValueError(f"Unsupported source {source!r}; choose from {sorted(SRA_SOURCES)}")
        clauses.append(f'{SRA_SOURCES[key]}[Source]')
    if not clauses:
        raise ValueError("Provide a query and/or at least one filter (organism, strategy, platform, source)")
    term = " AND ".join(clauses)
    bounded(limit)
    result = await ncbi_search("sra", term, limit)
    result["query"] = term
    result["source_url"] = "https://www.ncbi.nlm.nih.gov/sra/?" + urlencode({"term": term})
    result["summaries"] = (await ncbi_summary("sra", result["ids"]))["result"] if result["ids"] else {}
    return result


_SRA_ACCESSION = r"(?:SRR|ERR|DRR|SRX|ERX|DRX|SRP|ERP|DRP|SRS|SAMD?|GSM)[1-9][0-9]*"


async def _sra_runs(ids: list[str], limit: int) -> list[dict[str, Any]]:
    """Fetch NCBI runinfo for SRA runs/UIDs and return parsed run records."""
    response = await request("GET", f"{BASE_URL}/efetch.fcgi",
                             params={"db": "sra", "id": ",".join(ids[:200]),
                                     "rettype": "runinfo", "retmode": "csv"})
    body = response.text.strip()
    # NCBI returns headerless runinfo CSV; prepend the canonical column names.
    if not body.lower().startswith("run,"):
        body = ("Run,releaseDate,LoadDate,spots,bases,spots_with_mates,avgLength,size_MB,"
                "AssemblyName,download_path,Experiment,LibraryName,LibraryStrategy,"
                "LibrarySelection,LibrarySource,LibraryLayout,InsertSize,InsertDev,"
                "Platform,Model,SRAStudy,BioProject,Study_Pubmed_Link,ProjectID,Sample,"
                "BioSample,SampleType,TaxID,ScientificName,SampleName,g1k_pop,g1k_arm,"
                "Consented,run_hash") + "\n" + body
    rows = list(csv.DictReader(io.StringIO(body)))
    runs: list[dict[str, Any]] = []
    for row in rows:
        run = (row.get("Run") or "").strip()
        if not run:
            continue
        download = (row.get("download_path") or "").strip()
        if download.startswith("ftp://"):
            download = "https" + download[3:]
        runs.append({
            "run": run,
            "experiment": row.get("Experiment", ""),
            "study": row.get("SRAStudy", ""),
            "sample": row.get("Sample", ""),
            "organism": row.get("ScientificName", ""),
            "platform": row.get("Platform", ""),
            "model": row.get("Model", ""),
            "strategy": row.get("LibraryStrategy", ""),
            "layout": row.get("LibraryLayout", ""),
            "spots": int(row["spots"]) if row.get("spots", "").isdigit() else None,
            "bases": int(row["bases"]) if row.get("bases", "").isdigit() else None,
            "size_mb": float(row["size_MB"]) if row.get("size_MB", "") else None,
            "download_url": download or f"https://sra-pub-run-odp.s3.amazonaws.com/sra/{run}/{run}",
        })
        if len(runs) >= limit:
            break
    return runs


async def _sra_runs_for_accessions(accessions: list[str], limit: int) -> list[dict[str, Any]]:
    """Expand run/study/experiment/sample accessions to run records."""
    runs_direct = [a for a in accessions if a[:3] in {"SRR", "ERR", "DRR"}]
    to_resolve = [a for a in accessions if a not in runs_direct]
    ids = list(runs_direct)
    if to_resolve:
        term = " OR ".join(f'{a}[Accession]' for a in to_resolve)
        found = await ncbi_search("sra", term, 200)
        if not found["ids"]:
            raise ValueError(f"No SRA records found for {', '.join(to_resolve)}")
        ids = runs_direct + found["ids"]
    return await _sra_runs(ids, limit)


async def sra_files(accessions: list[str], limit: int = 30) -> dict[str, Any]:
    """Expand SRA accessions to runs and list direct download URLs; do not download.

    Accepts run, experiment, study, or sample accessions (SRR/ERR/DRR runs,
    SRX/ERX/DRX experiments, SRP/ERP/DRP studies, SAMD samples). Uses efetch
    runinfo so a study expands to its runs. Each run carries a public HTTPS
    link (the NCBI trace .sra object) plus platform, strategy, layout, spot
    and base counts, and size. Raw reads in FASTQ need the ENA mirror
    (see the ena-mcp server); SRA objects can be converted with
    sra-tools/fasterq-dump.
    """
    accessions = identifiers(accessions, 20)
    accessions = [identifier(a.upper(), _SRA_ACCESSION, "SRA accession") for a in accessions]
    bounded(limit)
    runs = await _sra_runs_for_accessions(accessions, limit)
    return {"accessions": accessions, "runs": runs, "returned": len(runs),
            "source_url": "https://www.ncbi.nlm.nih.gov/sra/" + urlencode({"term": ",".join(accessions)})}


GSA_BIG_SEARCH = "https://ngdc.cncb.ac.cn/search/api/specific"
ENA_PORTAL = "https://www.ebi.ac.uk/ena/portal/api/search"
_ENA_KNOWN_TAXA = {
    "Homo sapiens": "9606", "Mus musculus": "10090", "Arabidopsis thaliana": "3702",
    "Oryza sativa": "4530", "Populus": "3689", "Populus trichocarpa": "3694",
}


async def _ena_taxon(organism: str) -> tuple[str | None, bool]:
    """Resolve public ENA taxonomy without requiring NCBI credentials."""
    if not organism:
        return None, False
    name = _ORGANISM_ALIASES.get(organism.lower(), organism)
    if name.isdigit():
        return identifier(name, r"[1-9][0-9]*", "taxid"), False
    if name in _ENA_KNOWN_TAXA:
        return _ENA_KNOWN_TAXA[name], name == "Populus"
    response = await request("GET", "https://www.ebi.ac.uk/ena/taxonomy/rest/scientific-name/" + quote(name, safe=""))
    rows = response.json()
    matches = [row for row in rows if row.get("scientificName", "").lower() == name.lower()]
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous scientific name {name!r}; specify a scientific name or taxid")
    row = matches[0]
    return identifier(str(row["taxId"]), r"[1-9][0-9]*", "taxid"), row.get("rank") not in {"species", "subspecies", "strain"}


async def _sample_attributes(accession: str) -> dict[str, str]:
    accession = identifier(accession, r"(?:SAM[END][A-Z]?[0-9]+|[SED]RS[0-9]+)", "sample accession")
    response = await request("GET", "https://www.ebi.ac.uk/ena/browser/api/xml/" + accession)
    root = ET.fromstring(response.text)
    attributes: dict[str, str] = {}
    for node in root.findall(".//SAMPLE_ATTRIBUTE"):
        tag, value = node.findtext("TAG", "").strip().lower(), node.findtext("VALUE", "").strip()
        if tag and value:
            key = "attribute:" + tag
            if key in attributes and attributes[key] != value:
                raise ValueError(f"Conflicting sample attribute {tag}")
            attributes[key] = value
    for tag in ("donor_id", "donor id", "subject_id", "subject id", "individual_id", "individual id",
                "patient_id", "patient id", "participant_id"):
        if attributes.get("attribute:" + tag):
            value = attributes["attribute:" + tag]
            if attributes.get("donor_id") and attributes["donor_id"] != value:
                raise ValueError("Conflicting donor identity attributes")
            if value.lower() not in {"unknown", "not provided", "not applicable", "na", "n/a", "missing"}:
                attributes["donor_id"] = value
    return attributes


async def _ena_section(f: Filters, limit: int, metadata_limit: int) -> dict[str, Any]:
    taxid, genus = await _ena_taxon(f.organism)
    # Query both technologies separately so the first page of one does not crowd out the other.
    windows = ([replace(f, read_type=kind,
                        protocol="any" if kind == "short" else f.protocol,
                        platforms=(tuple(p for p in f.platforms if p in allowed) or
                                   (("PACBIO_SMRT",) if kind == "long" and f.protocol in {"hifi", "iso_seq"}
                                    else ("OXFORD_NANOPORE",) if kind == "long" and f.protocol != "any" else ())))
                for kind, allowed in (("short", {"ILLUMINA", "BGISEQ", "DNBSEQ", "ION_TORRENT"}),
                                      ("long", {"PACBIO_SMRT", "OXFORD_NANOPORE"}))
                if not f.platforms or set(f.platforms) & allowed]
               if f.read_type == "both" else [f])
    records: dict[str, dict] = {}
    queries, pages = [], []
    page_errors = []
    for window in windows:
        query = ena_query(window, taxid, genus or f.include_descendants)
        if not query:
            raise ValueError("No searchable ENA constraints; specify organism, assay, tissue or condition")
        params = {"result": "read_run", "query": query, "fields": ENA_RUN_FIELDS,
                  "format": "json", "limit": limit, "offset": f.offset}
        source_url = ENA_PORTAL + "?" + urlencode(params)
        queries.append(query)
        try:
            response = await request("GET", ENA_PORTAL, params=params)
            rows = response.json()
            if not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("run_accession") for row in rows):
                raise ValueError("ENA returned an invalid run report")
        except Exception as exc:
            page_errors.append(exc)
            pages.append({"query": query, "source_url": source_url, "status": "error",
                          "error": {"type": type(exc).__name__, "message": "ENA window failed"}})
            continue
        pages.append({"query": query, "source_url": source_url, "returned": len(rows),
                      "status": "ok", "truncated": len(rows) >= limit,
                      "next_offset": f.offset + limit if len(rows) >= limit else None})
        for row in rows:
            records[row["run_accession"]] = row
    if len(page_errors) == len(windows):
        raise page_errors[-1]
    samples = list(dict.fromkeys(row.get("sample_accession") for row in records.values() if row.get("sample_accession")))
    need_metadata = bool(f.tissue or f.pairing == "same_donor" or f.sample_type != "any" or f.sample_scope != "any")
    selected = samples[:metadata_limit] if need_metadata else []
    results = await asyncio.gather(*[_sample_attributes(sample) for sample in selected], return_exceptions=True)
    attributes = dict(zip(selected, results))
    candidates, runs, warnings = [], [], []
    for accession, row in records.items():
        metadata = dict(row)
        aliases = row.get("secondary_sample_accession", "").split(";")
        biosample = next((s for s in [row.get("sample_accession", ""), *aliases] if s.startswith("SAM")), None)
        metadata["biosample"] = biosample
        sample = row.get("sample_accession")
        extra = attributes.get(sample, {})
        candidate_warnings = []
        if isinstance(extra, Exception):
            candidate_warnings.append(f"Sample metadata unavailable: {type(extra).__name__}")
            extra = {}
        if need_metadata and sample not in attributes:
            candidate_warnings.append("Sample enrichment not attempted within metadata_limit")
        metadata.update(extra)
        files, file_warnings = files_from_record(row)
        candidate_warnings.extend(file_warnings)
        url = "https://www.ebi.ac.uk/ena/browser/view/" + accession
        candidate = {"id": "ena:" + accession, "source": "ena", "run": accession,
                     "study": row.get("study_accession"), "sample": sample,
                     "experiment": row.get("experiment_accession"), "title": row.get("experiment_title") or row.get("study_title"),
                     "metadata": metadata, "files": files, "warnings": candidate_warnings,
                     "attribute_fields": [k for k in extra if k.startswith("attribute:")],
                     "field_sources": {k: "https://www.ebi.ac.uk/ena/browser/api/xml/" + sample for k in extra},
                     "taxonomy_filtered": bool(taxid), "source_url": url}
        candidates.append(assess(candidate, f))
        sizes = [int(b) for b in (row.get("fastq_bytes") or "").split(";") if b.isdigit()]
        runs.append({"run": accession, "study": row.get("study_accession"), "title": row.get("study_title", ""),
                     "organism": row.get("scientific_name"), "strategy": row.get("library_strategy"),
                     "platform": row.get("instrument_platform"), "fastq_bytes": sum(sizes) or None,
                     "files": files, "source_url": url})
    if need_metadata and len(samples) > len(selected):
        warnings.append("Some samples were not enriched; increase metadata_limit or paginate")
    return {"query": queries[0] if len(queries) == 1 else queries, "count": len(runs),
            "count_kind": "returned_runs", "runs": runs, "candidates": candidates,
            "truncated": any(page.get("truncated", False) for page in pages), "pages": pages,
            "partial": bool(page_errors) or any(isinstance(value, Exception) for value in attributes.values()),
            "warnings": warnings, "source_url": pages[0]["source_url"]}


async def _gsa_section(organism: str, data_type: str, condition: str, limit: int, offset: int = 0) -> dict[str, Any] | None:
    """Keyword-search CNCB GSA (BIG Search); returns None if nothing to ask."""
    scientific = _ORGANISM_ALIASES.get(organism.strip().lower(), organism.strip())
    words = [w for w in (scientific, condition, data_type.replace("_", "-")) if w]
    if not words:
        return None
    query = " ".join(words)
    response = await request("GET", GSA_BIG_SEARCH,
                             params={"db": "gsa", "q": query, "start": offset, "length": limit})
    rows, total = search_payload(response.json())
    records = [{"id": row.get("id"), "type": row.get("type"), "title": row.get("title"),
                "url": row.get("url")} for row in rows]
    return {"query": query, "count": total, "returned": len(records),
            "records": records, "source_url": GSA_BIG_SEARCH.split("/api")[0] +
            f"/specific?db=gsa&q={quote_plus(query)}"}


def _summary_candidates(name: str, section: dict, f: Filters) -> list[dict]:
    candidates = []
    for uid, row in section.get("summaries", {}).items():
        if not isinstance(row, dict):
            continue
        accession = row.get("accession") or str(uid)
        metadata = {}
        run_ids = []
        if name == "sra":
            try:
                root = ET.fromstring("<root>" + row.get("expxml", "") + "</root>")
                for tag, field in (("Study", "study_accession"), ("Sample", "sample_accession"),
                                   ("Experiment", "experiment_accession"), ("Biosample", "biosample")):
                    node = root.find(".//" + tag)
                    if node is not None:
                        metadata[field] = node.get("acc") or node.text or ""
                title = root.findtext(".//Title")
                if title:
                    metadata["experiment_title"] = title
                node = root.find(".//Organism")
                if node is not None:
                    metadata["scientific_name"] = node.get("ScientificName", "")
                    metadata["tax_id"] = node.get("taxid", "")
                node = root.find(".//Platform")
                if node is not None:
                    metadata["instrument_platform"] = node.text or ""
                    metadata["instrument_model"] = node.get("instrument_model", "")
                for tag, field in (("LIBRARY_STRATEGY", "library_strategy"),
                                   ("LIBRARY_SOURCE", "library_source"),
                                   ("LIBRARY_CONSTRUCTION_PROTOCOL", "library_construction_protocol")):
                    value = root.findtext(".//" + tag)
                    if value:
                        metadata[field] = value
                runs = ET.fromstring("<root>" + row.get("runs", "") + "</root>")
                run_ids = [node.get("acc") for node in runs.iter("Run") if node.get("acc")]
            except ET.ParseError:
                pass
        for run in run_ids or [None]:
            identity = run or accession
            source_url = ("https://www.ncbi.nlm.nih.gov/sra/" + identity if name == "sra" else
                          "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=" + accession)
            candidate = {"id": name + ":" + identity, "source": name, "run": run,
                         "study": metadata.get("study_accession") or (accession if name == "geo" else None),
                         "sample": metadata.get("sample_accession"), "metadata": metadata,
                         "title": row.get("title") or metadata.get("experiment_title"), "files": [],
                         "taxonomy_filtered": name == "sra" and bool(f.organism),
                         "source_url": source_url,
                         "warnings": ["Summary only; use ENA or record tools for full sample/file evidence"]}
            candidates.append(assess(candidate, f))
    return candidates


async def _entrez_section(name: str, f: Filters, entry_type: str, limit: int) -> dict:
    clauses = []
    for value, expand in ((f.condition, condition_query_terms), (f.tissue, tissue_query_terms)):
        if value:
            clauses.append("(" + " OR ".join(_free_text_clause(term) for term in expand(value)) + ")")
    if name == "geo":
        if f.organism:
            clauses.append(_organism_clause(f.organism))
        for key in dict.fromkeys((f.data_type, f.assay)):
            if key in GEO_DATA_TYPES:
                clauses.append(GEO_DATA_TYPES[key])
        if f.protocol != "any":
            clauses.append(_free_text_clause(f.protocol.replace("_", "-")))
        if f.read_type == "long" and f.data_type != "long_reads":
            clauses.append(GEO_DATA_TYPES["long_reads"])
        if f.platforms:
            clauses.append("(" + " OR ".join(_free_text_clause(p) for p in f.platforms) + ")")
        if entry_type:
            clauses.append({"series": "gse", "sample": "gsm", "platform": "gpl"}[entry_type] + "[ETYP]")
    else:
        if f.organism:
            clauses.append(f"txid{await _taxid(f.organism)}[Organism]")
        if f.assay in {"rna_seq", "scrna", "snrna", "spatial"}:
            clauses.extend(["TRANSCRIPTOMIC[Source]", "(RNA-Seq[Strategy] OR FL-cDNA[Strategy] OR OTHER[Strategy] OR AMPLICON[Strategy])"])
        elif FIND_DATA_TYPES.get(f.assay, {}).get("strategy"):
            clauses.append(FIND_DATA_TYPES[f.assay]["strategy"] + "[Strategy]")
        platforms = platform_clause(f)
        if platforms:
            clauses.append("(" + " OR ".join(p + "[Platform]" for p in platforms) + ")")
        if f.protocol == "hifi":
            clauses.append('(HiFi[All Fields] OR "high-fidelity"[All Fields] OR CCS[All Fields])')
        elif f.protocol != "any":
            clauses.append(_free_text_clause(f.protocol.replace("_", " ")))
        if FIND_DATA_TYPES.get(f.assay, {}).get("keywords"):
            clauses.append(FIND_DATA_TYPES[f.assay]["keywords"])
    database = "gds" if name == "geo" else "sra"
    term = " AND ".join(clauses)
    hit = (await ncbi_search(database, term, limit, offset=f.offset) if f.offset else
           await ncbi_search(database, term, limit))
    section = {"count": hit["count"], "count_kind": "archive_records", "ids": hit["ids"], "query": term,
               "source_url": f"https://www.ncbi.nlm.nih.gov/{database}/?" + urlencode({"term": term}),
               "truncated": f.offset + len(hit["ids"]) < hit["count"],
               "next_offset": f.offset + limit if f.offset + limit < hit["count"] else None,
               "summaries": {}, "warnings": []}
    if hit["ids"]:
        try:
            section["summaries"] = (await ncbi_summary(database, hit["ids"]))["result"]
        except Exception as exc:
            section["warnings"].append("Summary unavailable: " + type(exc).__name__)
            section["partial"] = True
    section["candidates"] = _summary_candidates(name, section, f)
    return section


async def _discovery_gsa(f: Filters, limit: int) -> dict:
    words = [f.condition, f.tissue, *f.platforms]
    if f.protocol != "any":
        words.append(f.protocol.replace("_", " "))
    section = await _gsa_section(f.organism, f.assay or f.data_type, " ".join(w for w in words if w), limit, f.offset)
    if section is None:
        raise ValueError("No searchable GSA keywords")
    section["count_kind"] = "archive_records"
    section["truncated"] = f.offset + section["returned"] < section["count"]
    section["next_offset"] = f.offset + limit if section["truncated"] else None
    section["candidates"] = [assess({"id": "gsa:" + str(row["id"]), "source": "gsa",
                                    "run": None, "study": None, "sample": None,
                                    "title": row.get("title"), "metadata": {}, "files": [],
                                    "source_url": row.get("url") or section["source_url"],
                                    "warnings": ["Keyword search only; specimen, protocol and files are unverified"]}, f)
                              for row in section["records"]]
    return section


async def find_data(
    organism: str = "", data_type: str = "", condition: str = "", entry_type: str = "series",
    archives: str = "geo,sra,ena,gsa", limit: int = 10,
    tissue: str = "", assay: str = "", platforms: list[str] | None = None,
    read_type: str = "any", protocol: str = "any", sample_scope: str = "any",
    sample_type: str = "any", pairing: str = "any", file_format: str = "any",
    include_descendants: bool = False, offset: int = 0, metadata_limit: int = 10,
) -> dict[str, Any]:
    """Find data with independent biological/technical constraints and per-criterion evidence.

    Legacy data_type is supported. Prefer assay="rna_seq", tissue="liver",
    read_type="both", pairing="same_sample" for short/long transcriptomes;
    organism="poplar", assay="wgs", protocol="hifi" for poplar genome reads.
    platforms: illumina, bgiseq, dnbseq, pacbio, ont.
    read_type: any/short/long/both. protocol: any/hifi/iso_seq/direct_rna/direct_cdna/pcr_cdna.
    sample_scope: any/bulk/single_cell/single_nucleus; sample_type: any/tissue/cell_line/organoid.
    pairing: any/same_sample/same_donor, requiring explicit short/long identity evidence.
    file_format: any/fastq/bam/cram/sra/h5. Missing evidence stays unknown, not matched.
    ENA limit is per technology when read_type=both. metadata_limit bounds sample XML enrichment
    (0-20). offset pages each archive/window; return per-source errors and truncation flags.
    GEO/SRA queries require NCBI_EMAIL; ENA/GSA remain usable without it.
    """
    chosen = list(dict.fromkeys(a.strip().lower() for a in archives.split(",") if a.strip()))
    if not chosen or any(a not in {"geo", "sra", "ena", "gsa"} for a in chosen):
        raise ValueError("archives must be a comma-separated subset of geo,sra,ena,gsa")
    if data_type.strip() and data_type.strip().lower() not in FIND_DATA_TYPES:
        raise ValueError(f"Unsupported data_type {data_type!r}")
    entry_type = entry_type.strip().lower()
    if entry_type not in {"", "series", "sample", "platform"}:
        raise ValueError("entry_type must be series, sample or platform")
    bounded(limit)
    bounded(metadata_limit, 20, "metadata_limit", 0)
    f = discovery_filters(organism, data_type, condition, tissue=tissue, assay=assay,
                          platforms=platforms, read_type=read_type, protocol=protocol,
                          sample_scope=sample_scope, sample_type=sample_type, pairing=pairing,
                          file_format=file_format, include_descendants=include_descendants, offset=offset)
    # Reject query syntax in structured values before starting any provider calls.
    for value in (f.tissue, f.condition, f.organism):
        if value:
            ena_literal(value)
    tasks = {name: (_entrez_section(name, f, entry_type, limit) if name in {"geo", "sra"}
                    else _ena_section(f, limit, metadata_limit) if name == "ena"
                    else _discovery_gsa(f, limit)) for name in chosen}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    output: dict[str, Any] = {"data_type": f.data_type or None, "organism": f.organism or None,
                              "condition": f.condition or None, "archives": chosen,
                              "filters": f.as_dict(), "errors": {}, "warnings": [], "partial": False}
    candidates = []
    for name, result in zip(tasks, results):
        if isinstance(result, Exception):
            # Do not return HTTP exception strings: Entrez URLs can contain credentials.
            message = str(result) if isinstance(result, ValueError) else "Provider request failed; retry or inspect provider availability"
            error = {"type": type(result).__name__, "message": message}
            if isinstance(result, httpx.HTTPStatusError):
                error["status_code"] = result.response.status_code
            output[name] = {"status": "error", "error": error}
            output["errors"][name] = error
            output["partial"] = True
        else:
            output[name] = {"status": "ok", **result}
            candidates.extend(result.get("candidates", []))
            output["partial"] = output["partial"] or result.get("partial", False)
    groups = pair_candidates(candidates, f)
    output["candidates"] = [c for c in candidates if c["status"] != "mismatch"]
    output["excluded_candidates"] = [c for c in candidates if c["status"] == "mismatch"]
    output["pair_groups"] = groups
    output["candidate_counts"] = {status: sum(c["status"] == status for c in candidates)
                                  for status in ("match", "unknown", "mismatch")}
    output["truncated"] = any(output[name].get("truncated", False) for name in chosen)
    output["all_sources_failed"] = len(output["errors"]) == len(chosen)
    output["warnings"].append("Counts refer to archive records/runs, not biological samples; bounded windows are not exhaustive. Files and metadata are listed, not downloaded or checksum-verified.")
    return output


async def geo_search(
    query: str = "",
    limit: int = 20,
    organism: str = "",
    data_type: str = "",
    entry_type: str = "",
) -> dict[str, Any]:
    """Search GEO with biology-oriented filters.

    Args:
        query: Free-text topic, e.g. "Alzheimer's disease". Optional if filters given.
        organism: Organism name or common alias, e.g. "human", "mouse",
            "arabidopsis", "rice", "zebrafish", or any scientific name.
        data_type: One of wgs, wes, rna_seq, long_reads, hifi, ont, scrna,
            snrna, spatial, atac, chip_seq, methylome, proteomics, epigenomic.
        entry_type: "series" (GSE), "sample" (GSM), or "platform" (GPL).
    Examples: human long-read transcriptome -> organism="human",
    data_type="long_reads"; Arabidopsis single cell -> organism="arabidopsis",
    data_type="scrna".
    """
    clauses: list[str] = []
    if query.strip():
        clauses.append(_free_text_clause(query))
    if organism.strip():
        clauses.append(_organism_clause(organism))
    if data_type.strip():
        key = data_type.strip().lower()
        if key not in GEO_DATA_TYPES:
            raise ValueError(f"Unsupported data_type {data_type!r}; choose from {sorted(GEO_DATA_TYPES)}")
        clauses.append(GEO_DATA_TYPES[key])
    if entry_type.strip():
        tag = {"series": "gse", "sample": "gsm", "platform": "gpl"}.get(entry_type.strip().lower())
        if tag is None:
            raise ValueError("entry_type must be 'series', 'sample', or 'platform'")
        clauses.append(f"{tag}[ETYP]")
    if not clauses:
        raise ValueError("Provide a query and/or at least one filter (organism, data_type, entry_type)")
    term = " AND ".join(clauses)
    bounded(limit)
    result = await ncbi_search("gds", term, limit)
    result["query"] = term
    result["source_url"] = "https://www.ncbi.nlm.nih.gov/gds/?" + urlencode({"term": term})
    result["summaries"] = (await ncbi_summary("gds", result["ids"]))["result"] if result["ids"] else {}
    return result


def _geo_accession(accession: str) -> str:
    return identifier(accession.upper(), r"(?:GSE|GSM)[1-9][0-9]*", "GEO accession")


async def geo_record(accession: str) -> dict[str, Any]:
    """Read GSE/GSM SOFT metadata, including sample characteristics and supplement links."""
    accession = _geo_accession(accession)
    response = await request("GET", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi",
                             params={"acc": accession, "targ": "self", "form": "text", "view": "full"})
    metadata: dict[str, list[str]] = {}
    for line in response.text.splitlines():
        if line.startswith("!") and " = " in line:
            key, value = line[1:].split(" = ", 1)
            metadata.setdefault(key, []).append(value)
    if not metadata:
        raise ValueError(f"No GEO SOFT metadata returned for {accession}")
    return {"accession": accession, "metadata": metadata,
            "source_url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"}


class _DirectoryLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)


async def _geo_file_urls(accession: str) -> list[str]:
    """List GEO series matrix and supplement file URLs for an accession."""
    kind = "series" if accession.startswith("GSE") else "samples"
    group = re.sub(r"[0-9]{1,3}$", "nnn", accession)
    base = f"https://ftp.ncbi.nlm.nih.gov/geo/{kind}/{group}/{accession}/"
    directories = [base + "suppl/"]
    if kind == "series":
        directories.insert(0, base + "matrix/")
    files: list[str] = []
    for directory in directories:
        try:
            response = await request("GET", directory)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        parser = _DirectoryLinks()
        parser.feed(response.text)
        for href in parser.links:
            url = urljoin(directory, href)
            if url.startswith(directory) and not url.endswith("/") and "?" not in url and url not in files:
                files.append(url)
    return files


async def geo_files(accession: str, limit: int = 30) -> dict[str, Any]:
    """List actual GEO series matrices/supplements or sample supplements; do not download them."""
    accession = _geo_accession(accession)
    bounded(limit)
    kind = "series" if accession.startswith("GSE") else "samples"
    group = re.sub(r"[0-9]{1,3}$", "nnn", accession)
    base = f"https://ftp.ncbi.nlm.nih.gov/geo/{kind}/{group}/{accession}/"
    files = await _geo_file_urls(accession)
    return {"accession": accession, "files": files[:limit], "returned": min(len(files), limit),
            "truncated": len(files) > limit, "source_url": base}


async def download_plan(accessions: list[str], limit: int = 500) -> dict[str, Any]:
    """Build a batch download plan for GEO and SRA accessions; do not download.

    Accepts a mix of GSE/GSM and SRR/ERR/DRR/SRX/SRP accessions. GEO files
    (series matrices, supplements) and SRA run URLs are collected, sizes are
    totalled where known, and ready-to-save aria2c and wget inputs are
    returned. Feed aria2_input to `aria2c -i file.txt`; wget_script to
    `bash script.sh`.
    """
    accessions = identifiers(accessions, 20)
    bounded(limit, 2000)
    items: list[dict[str, Any]] = []
    geo_accessions = []
    sra_accessions = []
    for acc in accessions:
        acc = acc.upper()
        if acc.startswith("GSE") or acc.startswith("GSM"):
            geo_accessions.append(_geo_accession(acc))
        else:
            sra_accessions.append(identifier(acc.upper(), _SRA_ACCESSION, "SRA accession"))
    jobs = [(accession, _geo_file_urls(accession)) for accession in geo_accessions]
    if sra_accessions:
        jobs.append(("sra", _sra_runs_for_accessions(sra_accessions, limit)))
    results = await asyncio.gather(*(task for _, task in jobs), return_exceptions=True)
    errors = {}
    truncated = False
    for (accession, _), result in zip(jobs, results):
        if isinstance(result, Exception):
            errors[accession] = {"type": type(result).__name__, "message": "File listing failed"}
            continue
        if accession == "sra":
            truncated = truncated or len(result) >= limit
            for run in result:
                items.append({"source": "sra", "accession": run["run"], "url": run["download_url"],
                              "size_mb": run["size_mb"]})
        else:
            for url in result:
                items.append({"source": "geo", "accession": accession, "url": url, "size_mb": None})
    items = list({item["url"]: item for item in items}.values())
    truncated = truncated or len(items) > limit
    items = items[:limit]
    total_known_mb = sum(i["size_mb"] for i in items if i["size_mb"])
    unknown = sum(1 for i in items if i["size_mb"] is None)
    urls = [i["url"] for i in items]
    aria2_input = "\n".join(urls)
    wget_script = "\n".join(f"wget -c -- {shlex.quote(url)}" for url in urls)
    return {"accessions": accessions, "items": items, "count": len(items),
            "total_known_size_mb": total_known_mb, "files_without_size": unknown,
            "aria2_input": aria2_input, "wget_script": wget_script,
            "errors": errors, "partial": bool(errors), "truncated": truncated,
            "note": "GEO file sizes come from the FTP directory listing and are not "
                    "reported here; SRA .sra objects need fasterq-dump to convert."}


async def geo_metadata(accessions: list[str], limit: int = 500) -> dict[str, Any]:
    """Harvest sample-level metadata from GEO series for meta-analysis.

    For each GSE, reads the full SOFT sample block and returns one row per
    sample: title, source, organism, molecule, and all Sample_characteristics
    (treatment, tissue, variety, ...). Also returns a CSV text block ready to
    save as .csv and open in Excel. Accepts up to 10 GSE accessions.
    """
    accessions = identifiers(accessions, 10)
    accessions = [_geo_accession(a) if a.upper().startswith(("GSE", "GSM")) else _geo_accession(a) for a in accessions]
    bounded(limit, 5000)
    rows: list[dict[str, Any]] = []
    for accession in accessions:
        response = await request("GET", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi",
                                 params={"acc": accession, "targ": "gsm",
                                         "form": "text", "view": "full"})
        found = False
        for fields in soft_samples(response.text):
            found = True
            rows.append({
                "series": accession,
                "sample": _geo_accession(fields["Sample_geo_accession"][0]),
                "title": "; ".join(fields.get("Sample_title", [])),
                "source": "; ".join(fields.get("Sample_source_name_ch1", [])),
                "organism": "; ".join(fields.get("Sample_organism_ch1", [])),
                "molecule": "; ".join(fields.get("Sample_molecule_ch1", [])),
                "characteristics": "; ".join(fields.get("Sample_characteristics_ch1", [])),
            })
            if len(rows) >= limit:
                break
        if not found:
            raise ValueError(f"No sample metadata returned for {accession}")
        if len(rows) >= limit:
            break
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["series", "sample", "title", "source",
                                                "organism", "molecule", "characteristics"])
    writer.writeheader()
    writer.writerows(rows)
    return {"series": accessions, "samples": len(rows), "rows": rows[:200],
            "csv": buffer.getvalue(), "truncated_rows": len(rows) > 200,
            "truncated": len(rows) >= limit}


def databases() -> str:
    """List databases supported by this server."""
    return json.dumps(sorted(ALLOWED_DATABASES))


TOOLS = (
    ncbi_search,
    ncbi_summary,
    ncbi_fetch,
    ncbi_link,
    pubmed_search,
    pubmed_citations,
    sra_search,
    sra_files,
    find_data,
    geo_search,
    geo_record,
    geo_files,
    download_plan,
    geo_metadata,
)


RESOURCES = (
    ("ncbi://databases", databases),
)
