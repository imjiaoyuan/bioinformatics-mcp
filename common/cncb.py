"""Validate CNCB BIG Search business responses consistently across providers."""
from __future__ import annotations


def search_payload(data: object) -> tuple[list[dict], int]:
    if not isinstance(data, dict):
        raise ValueError("CNCB returned a non-object search response")
    code = data.get("code")
    if ("code" in data and (not isinstance(code, (str, int)) or isinstance(code, bool)
                            or code not in {200, "200", 0, "0"})) or data.get("success") is False:
        # Upstream messages may echo submitted values; keep errors structural.
        raise RuntimeError("CNCB reported a search failure")
    result = data.get("result")
    payload = result.get("data") if isinstance(result, dict) else None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("CNCB returned an invalid search payload")
    rows = payload["data"]
    if any(not isinstance(row, dict) or not row.get("id") for row in rows):
        raise ValueError("CNCB returned invalid search records")
    total = payload.get("recordsFiltered")
    if isinstance(total, bool) or not isinstance(total, (int, str)) or not str(total).isdigit():
        raise ValueError("CNCB returned no valid search count")
    total = int(total)
    if total < len(rows):
        raise ValueError("CNCB search count is smaller than returned records")
    return rows, total
