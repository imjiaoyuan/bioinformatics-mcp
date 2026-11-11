"""ENA record fields and file parsing shared by discovery and the ENA server."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

RUN_FIELDS = ",".join((
    "run_accession", "study_accession", "sample_accession", "secondary_sample_accession",
    "experiment_accession", "tax_id", "scientific_name", "study_title", "sample_title",
    "sample_description", "experiment_title", "library_strategy", "library_source",
    "library_selection", "library_layout", "library_construction_protocol",
    "instrument_platform", "instrument_model", "tissue_type", "cell_type", "cell_line",
    "read_count", "base_count", "fastq_ftp", "fastq_md5", "fastq_bytes",
    "submitted_ftp", "submitted_md5", "submitted_bytes",
))


def file_format(url: str) -> str:
    name = urlsplit(url).path.lower()
    name = re.sub(r"\.(gz|bz2|zst)$", "", name)
    for suffix, kind in ((".fastq", "fastq"), (".fq", "fastq"), (".bam", "bam"),
                         (".cram", "cram"), (".sra", "sra"), (".h5", "h5")):
        if name.endswith(suffix):
            return kind
    return "other"


def files_from_record(record: dict, submitted: bool = True) -> tuple[list[dict], list[str]]:
    """Keep per-file values aligned; never guess checksums for malformed lists."""
    files: dict[str, dict] = {}
    warnings: list[str] = []
    for prefix in (("fastq", "submitted") if submitted else ("fastq",)):
        raw_paths = record.get(prefix + "_ftp") or ""
        if not raw_paths:
            continue
        paths = raw_paths.split(";")
        checksums = (record.get(prefix + "_md5") or "").split(";")
        sizes = (record.get(prefix + "_bytes") or "").split(";")
        for field, values in (("md5", checksums), ("bytes", sizes)):
            if len(values) != len(paths):
                warnings.append(f"{prefix}_{field} length differs from file list; values omitted")
        for i, path in enumerate(paths):
            url = path if path.startswith("https://") else "https://" + path.removeprefix("ftp://")
            parsed = urlsplit(url)
            if not path or not parsed.hostname or parsed.username or any(c.isspace() for c in url):
                warnings.append("Invalid file URL omitted")
                continue
            size = sizes[i] if len(sizes) == len(paths) else ""
            checksum = checksums[i] if len(checksums) == len(paths) else ""
            name = parsed.path.lower()
            role = ("subreads" if "subreads" in name else "hifi" if "hifi" in name
                    else "ccs" if re.search(r"[._/-]ccs[._/-]", name) else "reads")
            entry = {"url": url, "md5": checksum or None,
                     "bytes": int(size) if size.isdigit() else None,
                     "format": file_format(url), "role": role, "role_basis": "filename_hint", "origins": [prefix]}
            if url in files:
                files[url]["origins"].append(prefix)
                for key in ("md5", "bytes"):
                    if files[url][key] is None:
                        files[url][key] = entry[key]
                    elif entry[key] is not None and files[url][key] != entry[key]:
                        files[url][key] = None
                        warnings.append(f"Conflicting {key} for {url}")
            else:
                files[url] = entry
    return list(files.values()), warnings
