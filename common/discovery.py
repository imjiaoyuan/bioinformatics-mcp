"""Validated discovery requirements and conservative, traceable candidate assessment."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from common.http import bounded, text

PLATFORMS = {"illumina": "ILLUMINA", "bgiseq": "BGISEQ", "dnbseq": "DNBSEQ",
             "pacbio": "PACBIO_SMRT", "ont": "OXFORD_NANOPORE"}
LONG_PLATFORMS = {"PACBIO_SMRT", "OXFORD_NANOPORE"}
SHORT_PLATFORMS = {"ILLUMINA", "BGISEQ", "DNBSEQ", "ION_TORRENT"}
PROTOCOLS = {"any", "hifi", "iso_seq", "direct_rna", "direct_cdna", "pcr_cdna"}
ASSAYS = {"rna_seq", "wgs", "wes", "scrna", "snrna", "spatial", "atac", "chip_seq",
          "methylome", "proteomics", "epigenomic"}
TISSUES = {"肝": "liver", "肝脏": "liver", "脑": "brain", "大脑": "brain",
           "心脏": "heart", "心": "heart", "肺": "lung", "叶": "leaf", "叶片": "leaf"}
PROTOCOL_PATTERNS = {
    "hifi": r"\bhifi\b|high[- ]fidelity",
    "iso_seq": r"iso[- ]?seq",
    "direct_rna": r"direct[- ]rna|rna00[124]",
    "direct_cdna": r"direct[- ]cdna|dcs10[89]",
    "pcr_cdna": r"pcr[- ]cdna|pcs1[01][0-9]",
}


@dataclass(frozen=True)
class Filters:
    organism: str
    data_type: str
    condition: str
    tissue: str
    assay: str
    platforms: tuple[str, ...]
    read_type: str
    protocol: str
    sample_scope: str
    sample_type: str
    pairing: str
    file_format: str
    include_descendants: bool
    offset: int

    def as_dict(self) -> dict:
        return asdict(self)


def filters(organism: str, data_type: str, condition: str, *, tissue: str = "", assay: str = "",
            platforms: list[str] | None = None, read_type: str = "any", protocol: str = "any",
            sample_scope: str = "any", sample_type: str = "any", pairing: str = "any",
            file_format: str = "any", include_descendants: bool = False, offset: int = 0) -> Filters:
    values = {"organism": organism, "data_type": data_type, "condition": condition,
              "tissue": tissue, "assay": assay}
    for key, value in values.items():
        values[key] = text(value, key, 200) if value.strip() else ""
    data_type = values["data_type"].lower()
    assay = values["assay"].lower()
    inferred_assay = data_type if data_type in ASSAYS else "rna_seq" if data_type in {"long_reads", "ont"} else ""
    if assay and inferred_assay and assay != inferred_assay:
        raise ValueError("assay conflicts with data_type; use read_type/protocol for independent filters")
    assay = assay or inferred_assay
    if assay and assay not in ASSAYS:
        raise ValueError(f"assay must be one of {sorted(ASSAYS)}")
    options = {"read_type": (read_type, {"any", "short", "long", "both"}),
               "protocol": (protocol, PROTOCOLS),
               "sample_scope": (sample_scope, {"any", "bulk", "single_cell", "single_nucleus"}),
               "sample_type": (sample_type, {"any", "tissue", "cell_line", "organoid"}),
               "pairing": (pairing, {"any", "same_sample", "same_donor"}),
               "file_format": (file_format, {"any", "fastq", "bam", "cram", "sra", "h5"})}
    for name, (value, allowed) in options.items():
        if value not in allowed:
            raise ValueError(f"{name} must be one of {sorted(allowed)}")
    if not isinstance(include_descendants, bool):
        raise ValueError("include_descendants must be boolean")
    bounded(offset, 100000, "offset", 0)
    if data_type in {"hifi", "ont", "long_reads"}:
        if read_type == "short":
            raise ValueError("read_type conflicts with data_type")
        read_type = "long" if read_type == "any" else read_type
    if data_type == "hifi":
        if protocol not in {"any", "hifi"}:
            raise ValueError("protocol conflicts with data_type=hifi")
        protocol = "hifi"
    if data_type == "ont" and protocol in {"hifi", "iso_seq"}:
        raise ValueError("PacBio protocol conflicts with data_type=ont")
    if assay in {"wgs", "wes"} and protocol in {"iso_seq", "direct_rna", "direct_cdna", "pcr_cdna"}:
        raise ValueError("RNA protocol conflicts with genomic assay")
    if protocol != "any":
        if read_type == "short":
            raise ValueError("long-read protocol conflicts with read_type=short")
        read_type = "long" if read_type == "any" else read_type
    if assay in {"scrna", "snrna"}:
        expected_scope = "single_cell" if assay == "scrna" else "single_nucleus"
        if sample_scope not in {"any", expected_scope}:
            raise ValueError("sample_scope conflicts with assay")
        sample_scope = expected_scope
    if platforms is not None and (not platforms or len(platforms) > len(PLATFORMS)):
        raise ValueError("platforms must contain 1-6 platform names")
    chosen = []
    for platform in platforms or []:
        if platform.lower() not in PLATFORMS:
            raise ValueError(f"platforms must use {sorted(PLATFORMS)}")
        chosen.append(PLATFORMS[platform.lower()])
    inferred = ({"PACBIO_SMRT"} if protocol in {"hifi", "iso_seq"} else
                {"OXFORD_NANOPORE"} if protocol != "any" or data_type == "ont" else set())
    selected_long = set(chosen) & LONG_PLATFORMS if read_type == "both" else set(chosen)
    if inferred and selected_long and not selected_long <= inferred:
        raise ValueError("platforms conflict with protocol/data_type")
    chosen = chosen or (sorted(inferred) if read_type != "both" else [])
    if read_type == "both" and chosen and not (set(chosen) & SHORT_PLATFORMS and set(chosen) & LONG_PLATFORMS):
        raise ValueError("read_type=both requires selected platforms from both short- and long-read technologies")
    compatible = SHORT_PLATFORMS if read_type == "short" else LONG_PLATFORMS if read_type == "long" else None
    if compatible and chosen and not set(chosen) <= compatible:
        raise ValueError("platforms conflict with read_type")
    if not any((data_type, condition.strip(), tissue.strip(), assay, chosen, protocol != "any",
                read_type != "any", sample_scope != "any", sample_type != "any")):
        raise ValueError("Provide a data type, assay, tissue, condition or sequencing filter")
    return Filters(values["organism"], data_type, values["condition"],
                   TISSUES.get(values["tissue"], values["tissue"]), assay,
                   tuple(dict.fromkeys(chosen)), read_type, protocol, sample_scope, sample_type,
                   pairing, file_format, include_descendants, offset)


def platform_clause(f: Filters) -> list[str]:
    return list(f.platforms) or (sorted(LONG_PLATFORMS) if f.read_type == "long" else
                                sorted(SHORT_PLATFORMS) if f.read_type == "short" else [])


def ena_literal(value: str) -> str:
    """Structured values are literals, not user-supplied Portal query expressions."""
    if any(c in value for c in ('"', '\\', '*', '?')):
        raise ValueError("Structured ENA filters cannot contain quotes, backslashes or wildcards")
    return '"' + value + '"'


def ena_text(value: str, fields: tuple[str, ...]) -> str:
    literal = ena_literal(value)
    wildcard = '"*' + literal[1:-1] + '*"'
    return "(" + " OR ".join(f"{field}={wildcard}" for field in fields) + ")"


def ena_query(f: Filters, taxid: str | None, tree: bool = False) -> str:
    clauses = []
    if taxid:
        clauses.append(f"tax_{'tree' if tree else 'eq'}({taxid})")
    strategies = {"wgs": "WGS", "wes": "WXS", "chip_seq": "ChIP-Seq", "methylome": "Bisulfite-Seq"}
    if f.assay in {"rna_seq", "scrna", "snrna", "spatial"}:
        clauses.append('library_source="TRANSCRIPTOMIC"')
        # OTHER and AMPLICON must remain candidates until protocol evidence is assessed.
        clauses.append('(library_strategy="RNA-Seq" OR library_strategy="FL-cDNA" OR '
                       'library_strategy="OTHER" OR library_strategy="AMPLICON")')
    elif f.assay in strategies:
        clauses.append(f'library_strategy="{strategies[f.assay]}"')
    platforms = platform_clause(f)
    if platforms:
        clauses.append("(" + " OR ".join(f'instrument_platform="{p}"' for p in platforms) + ")")
    searchable = ("sample_title", "sample_description", "experiment_title", "study_title")
    if f.tissue:
        clauses.append(ena_text(f.tissue, ("tissue_type", *searchable)))
    if f.condition:
        clauses.append(ena_text(f.condition, searchable))
    if f.sample_scope in {"single_cell", "single_nucleus"}:
        terms = (("single cell", "single-cell", "scRNA", "10x", "Smart-seq") if f.sample_scope == "single_cell"
                 else ("single nucleus", "single-nucleus", "single nuclei", "snRNA"))
        clauses.append("(" + " OR ".join(ena_text(term, searchable) for term in terms) + ")")
    if f.sample_type == "organoid":
        clauses.append(ena_text("organoid", searchable))
    if f.protocol == "hifi":
        clauses.append("(" + " OR ".join(ena_text(term, ("library_construction_protocol", *searchable))
                                          for term in ("HiFi", "high-fidelity", "CCS")) + ")")
    elif f.protocol != "any":
        terms = {"iso_seq": ("Iso-Seq", "IsoSeq"), "direct_rna": ("direct RNA", "RNA002", "RNA004"),
                 "direct_cdna": ("direct cDNA", "DCS108", "DCS109"),
                 "pcr_cdna": ("PCR cDNA", "PCR-cDNA", "PCS109", "PCS111")}[f.protocol]
        clauses.append("(" + " OR ".join(ena_text(term, ("library_construction_protocol", *searchable)) for term in terms) + ")")
    # Assays without a reliable exact field use keyword recall and remain unverified.
    if f.assay in {"atac", "proteomics", "epigenomic"}:
        clauses.append(ena_text({"atac": "ATAC", "proteomics": "proteom", "epigenomic": "epigen"}[f.assay], searchable))
    return " AND ".join(clauses)


def _contains(value: str, needle: str) -> bool:
    return bool(re.search(r"(?<![^\W_])" + re.escape(needle) + r"(?![^\W_])", value, re.I))


def assess(candidate: dict, f: Filters) -> dict:
    """Assess observed fields only: study titles are never specimen evidence."""
    metadata = candidate.get("metadata", {})
    url = candidate["source_url"]
    checks: dict[str, dict] = {}

    def check(name: str, status: str, fields: list[str], explanation: str) -> None:
        checks[name] = {"status": status, "reason": explanation,
                        "evidence": [{"field": field, "value": metadata[field],
                                      "source_url": candidate.get("field_sources", {}).get(field, url)}
                                     for field in fields if metadata.get(field)]}

    platform = metadata.get("instrument_platform", "")
    kind = "long" if platform in LONG_PLATFORMS else "short" if platform in SHORT_PLATFORMS else None
    candidate["read_type"] = kind
    if f.organism:
        # Structured taxonomy filters are authoritative; keyword-only archives are not.
        check("organism", "match" if candidate.get("taxonomy_filtered") else "unknown",
              ["scientific_name", "tax_id"], "Archive taxonomy filter" if candidate.get("taxonomy_filtered")
              else "Species has not been verified from structured metadata")
    if f.platforms:
        check("platforms", "match" if platform in f.platforms else "mismatch" if platform else "unknown",
              ["instrument_platform"], "Sequencing platform")
    if f.read_type != "any":
        check("read_type", "match" if kind and (f.read_type == "both" or kind == f.read_type)
              else "mismatch" if kind else "unknown", ["instrument_platform"], "Read technology from platform")
    fields = ["experiment_title", "library_construction_protocol", "sample_title", "sample_description"]
    description = " ".join(str(metadata.get(k) or "") for k in fields)
    strategy = metadata.get("library_strategy", "")
    source = metadata.get("library_source", "")
    if f.assay:
        expected = {"wgs": "WGS", "wes": "WXS", "chip_seq": "ChIP-Seq", "methylome": "Bisulfite-Seq"}.get(f.assay)
        if f.assay in {"rna_seq", "scrna", "snrna", "spatial"}:
            status = ("mismatch" if strategy in {"miRNA-Seq", "ncRNA-Seq", "WGS", "WXS"} or source == "GENOMIC"
                      else "match" if strategy in {"RNA-Seq", "FL-cDNA"}
                      else "match" if source == "TRANSCRIPTOMIC" and re.search(
                          r"iso[- ]?seq|direct[- ]rna|direct[- ]cdna|pcr[- ]cdna|full[- ]length", description, re.I)
                      else "unknown")
        else:
            status = "match" if expected and strategy == expected else "mismatch" if expected and strategy else "unknown"
        check("assay", status, ["library_strategy", "library_source", *fields], "Library strategy/source and protocol evidence")
    for name, wanted in (("tissue", f.tissue), ("condition", f.condition)):
        if not wanted:
            continue
        relevant = (r"tissue|organ|body.?site|source.?name" if name == "tissue" else
                    r"condition|disease|treatment|phenotype|health|description")
        attributes = [k for k in candidate.get("attribute_fields", []) if re.search(relevant, k, re.I)]
        observed = ["tissue_type", "sample_title", "sample_description", *attributes]
        matched = [k for k in observed if _contains(str(metadata.get(k) or ""), wanted)]
        status = "match" if matched else "unknown"
        if name == "tissue" and metadata.get("tissue_type") and not _contains(metadata["tissue_type"], wanted):
            status = "mismatch"
        check(name, status, matched or ["tissue_type"], "Sample-level evidence required; project keywords alone are insufficient")
    if f.protocol != "any":
        roles = {entry["role"] for entry in candidate.get("files", [])}
        matched = bool(re.search(PROTOCOL_PATTERNS[f.protocol], description, re.I))
        if f.protocol == "hifi":
            matched = matched or "hifi" in roles
        status = "match" if matched else "unknown"
        if f.protocol in {"hifi", "iso_seq"} and platform and platform != "PACBIO_SMRT":
            status = "mismatch"
        if f.protocol in {"direct_rna", "direct_cdna", "pcr_cdna"} and platform and platform != "OXFORD_NANOPORE":
            status = "mismatch"
        if f.protocol == "hifi" and roles == {"subreads"}:
            if matched:
                check("read_representation", "unknown", fields,
                      "Metadata reports HiFi but file names suggest subreads; inspect read headers/quality to resolve")
                checks["read_representation"]["evidence"].extend(
                    {"field": "filename_role_hint", "value": "subreads", "source_url": entry["url"]}
                    for entry in candidate.get("files", []))
            else:
                status = "mismatch"
        if f.protocol == "hifi" and re.search(r"\bCLR\b|continuous long reads", description, re.I):
            status = "mismatch"
        if f.protocol in {"direct_rna", "direct_cdna", "pcr_cdna"}:
            others = [p for p in ("direct_rna", "direct_cdna", "pcr_cdna") if p != f.protocol]
            if any(re.search(PROTOCOL_PATTERNS[p], description, re.I) for p in others):
                status = "unknown" if matched else "mismatch"
        check("protocol", status, fields, "Protocol evidence required; platform or CCS alone does not establish HiFi")
        checks["protocol"]["evidence"].extend({"field": "file_role", "value": entry["role"],
                                                 "source_url": entry["url"]}
                                                for entry in candidate.get("files", []) if entry["role"] != "reads")
        if f.read_type == "both" and kind == "short":
            checks["protocol"] = {"status": "match", "reason": "Protocol constraint applies to long-read members only",
                                  "evidence": checks["read_type"]["evidence"]}
    if f.sample_scope != "any":
        detected = ("single_nucleus" if re.search(r"single[- ]nucle(?:us|i)|snrna", description, re.I)
                    else "single_cell" if re.search(r"single[- ]cell|scrna|10x genomics|smart[- ]seq", description, re.I)
                    else "bulk" if re.search(r"\bbulk\b", description, re.I) else None)
        check("sample_scope", "match" if detected == f.sample_scope else "mismatch" if detected else "unknown",
              fields, "Bulk is not inferred from absence of single-cell keywords")
    if f.sample_type != "any":
        detected = ("cell_line" if metadata.get("cell_line") or re.search(r"cell[- ]line", description, re.I)
                    else "organoid" if re.search(r"organoid", description, re.I)
                    else "tissue" if metadata.get("tissue_type") or re.search(r"primary tissue|tissue biopsy", description, re.I)
                    else None)
        check("sample_type", "match" if detected == f.sample_type else "mismatch" if detected else "unknown",
              ["tissue_type", "cell_line", *fields], "Specimen type requires explicit annotation")
    if f.file_format != "any":
        available = candidate.get("files", [])
        status = "match" if any(x["format"] == f.file_format for x in available) else "unknown"
        check("file_format", status, [], "Only listed formats are confirmed; missing formats may exist elsewhere")
        checks["file_format"]["evidence"] = [{"field": "format", "value": x["format"], "source_url": x["url"]} for x in available]
    candidate["criteria"] = checks
    return update_status(candidate)


def update_status(candidate: dict) -> dict:
    checks = candidate["criteria"]
    candidate["status"] = ("mismatch" if any(x["status"] == "mismatch" for x in checks.values())
                           else "unknown" if not checks or any(x["status"] == "unknown" for x in checks.values())
                           else "match")
    candidate["uncertainties"] = [name for name, value in checks.items() if value["status"] == "unknown"]
    return candidate


def pair_candidates(candidates: list[dict], f: Filters) -> list[dict]:
    """Require explicit specimen IDs, or study-scoped donor IDs, across technologies."""
    mode = f.pairing if f.pairing != "any" else "same_sample"
    buckets: dict[tuple, list[dict]] = {}
    for candidate in candidates:
        if candidate["status"] == "mismatch":
            continue
        metadata = candidate.get("metadata", {})
        identity = ((metadata.get("biosample") or metadata.get("sample_accession"))
                    if mode == "same_sample" else metadata.get("donor_id"))
        study = metadata.get("study_accession")
        if not identity or (mode == "same_donor" and not study):
            continue
        key = (identity,) if mode == "same_sample" else (study, identity)
        buckets.setdefault(key, []).append(candidate)
    groups = []
    paired = set()
    for identity, rows in buckets.items():
        if {row.get("read_type") for row in rows} >= {"short", "long"}:
            groups.append({"mode": mode, "identity": list(identity),
                           "candidate_ids": [r["id"] for r in rows],
                           "status": "match" if all(r["status"] == "match" for r in rows) else "unknown",
                           "identity_verified": True,
                           "evidence": [{"source_url": r["source_url"], "sample": r.get("metadata", {}).get("sample_accession"),
                                         "biosample": r.get("metadata", {}).get("biosample"),
                                         "donor_id": r.get("metadata", {}).get("donor_id")} for r in rows]})
            paired.update(r["id"] for r in rows)
    if f.pairing != "any":
        for candidate in candidates:
            candidate["criteria"]["pairing"] = {
                "status": "match" if candidate["id"] in paired else "unknown",
                "reason": "Explicit identity across short/long reads" if candidate["id"] in paired
                          else "No short/long pair verified in this bounded result window",
                "evidence": [g for g in groups if candidate["id"] in g["candidate_ids"]]}
            update_status(candidate)
    return groups
