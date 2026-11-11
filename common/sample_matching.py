"""Conservative specimen matching with a small, explicit anatomical vocabulary.

This is not a complete ontology or a general natural-language classifier. Unmapped
anatomy, comparison narratives and conflicting annotations remain unknown.
"""
from __future__ import annotations

import re

# canonical name -> (parent, aliases). Keep broad-to-specific relationships explicit.
ANATOMY = {
    "brain": (None, ("brain", "脑", "脑组织")),
    "cerebrum": ("brain", ("cerebrum", "大脑")),
    "cerebral cortex": ("cerebrum", ("cerebral cortex", "brain cortex", "大脑皮层")),
    "frontal cortex": ("cerebral cortex", ("frontal cortex", "prefrontal cortex", "frontal lobe")),
    "temporal cortex": ("cerebral cortex", ("temporal cortex", "temporal lobe")),
    "hippocampus": ("brain", ("hippocampus", "hippocampal", "海马")),
    "cerebellum": ("brain", ("cerebellum", "cerebellar", "小脑")),
    "liver": (None, ("liver", "hepatic tissue", "肝", "肝脏")),
    "lung": (None, ("lung", "lung tissue", "肺")),
    "heart": (None, ("heart", "cardiac tissue", "心脏")),
    "kidney": (None, ("kidney", "renal tissue", "肾")),
    "renal cortex": ("kidney", ("renal cortex", "kidney cortex")),
    "blood": (None, ("blood", "whole blood", "血液")),
    "leaf": (None, ("leaf", "leaves", "叶", "叶片")),
    "root": (None, ("root", "roots", "根")),
}
_UNKNOWN = {"", "unknown", "not provided", "not applicable", "missing", "na", "n/a", "none"}
_COMPARISON = re.compile(r"\b(compared?|comparison|versus|vs|between|controls? for|relative to)\b|对照|比较", re.I)
_NEGATION = re.compile(r"\b(not|without|no|non|free)\b|非|无", re.I)
_TISSUE_KEYS = {"tissue", "tissue type", "organ", "organism part", "body site", "source name", "source name ch1"}
_CONDITION_KEYS = {"condition", "disease", "disease state", "disease status", "health status", "health state",
                   "phenotype", "diagnosis", "tumor status", "tumour status", "treatment", "treatment group"}
_HEALTH = {"healthy", "normal", "healthy control", "disease free", "non diseased", "unaffected", "no disease"}
_TUMOR = {"tumor", "tumour", "cancer", "malignant", "carcinoma"}


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("_", " ").replace("-", " ")).strip()


def contains(value: str, term: str) -> bool:
    return bool(re.search(r"(?<![^\W_])" + re.escape(normalized(term)) + r"(?![^\W_])", normalized(value)))


def ancestors(node: str) -> set[str]:
    result = {node}
    while node in ANATOMY and ANATOMY[node][0]:
        node = ANATOMY[node][0]
        result.add(node)
    return result


def anatomy_terms(value: str) -> set[str]:
    # Match longer anatomical names first, e.g. kidney cortex must not become brain cortex.
    remaining = normalized(value)
    result = set()
    aliases = sorted(((alias, name) for name, (_, names) in ANATOMY.items() for alias in names),
                     key=lambda row: len(row[0]), reverse=True)
    for alias, name in aliases:
        pattern = r"(?<![^\W_])" + re.escape(normalized(alias)) + r"(?![^\W_])"
        if re.search(pattern, remaining):
            result.add(name)
            remaining = re.sub(pattern, " ", remaining)
    return result


def tissue_query_terms(value: str) -> list[str]:
    nodes = anatomy_terms(value)
    if len(nodes) != 1:
        return [value]
    wanted = next(iter(nodes))
    # Include descendants, but never broaden a specific tissue to its parent.
    return list(dict.fromkeys([value, wanted, *[name for name in ANATOMY if wanted in ancestors(name)]]))


def condition_query_terms(value: str) -> list[str]:
    label = normalized(value)
    return [value, "healthy", "normal"] if label in _HEALTH else [value]


def _structured(metadata: dict, kind: str) -> list[str]:
    keys = _TISSUE_KEYS if kind == "tissue" else _CONDITION_KEYS
    fields = ["tissue_type"] if kind == "tissue" else []
    fields += [key for key in metadata if key.startswith("attribute:") and normalized(key[10:]) in keys]
    return [key for key in fields if normalized(str(metadata.get(key) or "")) not in _UNKNOWN]


def match_tissue(metadata: dict, wanted: str) -> tuple[str, list[str], str]:
    structured = _structured(metadata, "tissue")
    fields = structured or [key for key in ("sample_title", "sample_description") if metadata.get(key)]
    requested = anatomy_terms(wanted)
    query_node = next(iter(requested)) if len(requested) == 1 else None
    statuses = []
    for field in fields:
        value = str(metadata[field])
        if _COMPARISON.search(value) or _NEGATION.search(normalized(value)):
            statuses.append("unknown")
            continue
        observed = anatomy_terms(value)
        if query_node and observed:
            matching = [query_node in ancestors(node) for node in observed]
            if all(matching):
                statuses.append("match")
            elif any(matching) or any(node in ancestors(query_node) for node in observed):
                statuses.append("unknown")
            else:
                statuses.append("mismatch" if structured else "unknown")
        elif normalized(value) == normalized(wanted):
            statuses.append("match")
        else:
            statuses.append("unknown")
    status = ("unknown" if "match" in statuses and "mismatch" in statuses else
              "match" if "match" in statuses else "mismatch" if structured and statuses and all(s == "mismatch" for s in statuses)
              else "unknown")
    return status, fields, "Anatomical labels and explicit parent relationships; unmapped or conflicting anatomy stays unknown"


def _condition_status(value: str, wanted: str, structured: bool, field: str) -> str:
    label, target = normalized(value), normalized(wanted)
    if label in _UNKNOWN or _COMPARISON.search(value):
        return "unknown"
    health_request = target in _HEALTH
    tumor_request = target in _TUMOR
    negated = _NEGATION.search(label) and label not in _HEALTH
    if negated:
        return "mismatch" if structured and contains(label, target) else "unknown"
    healthy = label in _HEALTH
    tumor = any(contains(label, term) for term in _TUMOR)
    if tumor and any(contains(label, word) for word in ("normal", "healthy")):
        return "unknown"
    if health_request:
        if healthy:
            return "match"
        if (structured and (tumor or ("disease" in field and label not in _UNKNOWN))) or (
                not structured and tumor and len(label.split()) <= 5):
            return "mismatch"
        # A short specimen label such as 'healthy liver' is useful, a comparison is not.
        if not structured and len(label.split()) <= 5 and contains(label, "healthy") and not tumor:
            return "match"
        return "unknown"
    if tumor_request:
        return "match" if tumor else "mismatch" if structured and healthy else "unknown"
    if contains(label, target) and (structured or len(label.split()) <= 5):
        return "match"
    return "unknown"


def match_condition(metadata: dict, wanted: str) -> tuple[str, list[str], str]:
    structured = _structured(metadata, "condition")
    if normalized(wanted) in _HEALTH:
        structured = [key for key in structured if "treatment" not in key]
    fields = structured or [key for key in ("sample_title", "sample_description") if metadata.get(key)]
    statuses = [_condition_status(str(metadata[key]), wanted, bool(structured), key) for key in fields]
    status = ("unknown" if "match" in statuses and "mismatch" in statuses else
              "mismatch" if "mismatch" in statuses else "match" if "match" in statuses else "unknown")
    return status, fields, "Structured specimen attributes take precedence; comparison text and conflicting conditions stay unknown"
