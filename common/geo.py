"""Parse GEO SOFT samples without losing repeated or missing field boundaries."""
from __future__ import annotations

from collections.abc import Iterator


def soft_samples(content: str) -> Iterator[dict[str, list[str]]]:
    sample: dict[str, list[str]] = {}
    marked = False
    for line in content.splitlines():
        if line.startswith("^"):
            if sample:
                yield sample
            sample = {}
            marked = line.startswith("^SAMPLE = ")
            if marked:
                sample["Sample_geo_accession"] = [line.split(" = ", 1)[1].strip()]
            continue
        if not line.startswith("!Sample_") or " = " not in line:
            continue
        key, value = line[1:].split(" = ", 1)
        if key == "Sample_geo_accession":
            if marked:
                if sample["Sample_geo_accession"] != [value]:
                    raise ValueError("GEO sample marker and accession disagree")
                continue
            if sample:
                yield sample
            sample = {key: [value]}
        elif sample:
            sample.setdefault(key, []).append(value)
        else:
            raise ValueError("Sample fields precede a GEO sample boundary; cannot assign them safely")
    if sample:
        yield sample
