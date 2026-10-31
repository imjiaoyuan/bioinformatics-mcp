"""Small response and input helpers for bounded provider integrations."""
from __future__ import annotations

from typing import Any

from common.http import bounded, request


def choice(value: str, values: set[str], name: str) -> str:
    if value not in values:
        raise ValueError(f"{name} must be one of {', '.join(sorted(values))}")
    return value


def page(limit: int, offset: int) -> dict:
    return {"limit": bounded(limit), "offset": bounded(offset, 1_000_000, "offset", 0)}


async def json_response(url: str, params: dict | None = None, *, body: Any = None,
                        interval: float = 0.35, max_bytes: int = 8_000_000) -> tuple[Any, dict]:
    response = await request("GET" if body is None else "POST", url, params=params,
                             json=body, retryable=body is not None, interval=interval,
                             max_bytes=max_bytes)
    return response.json(), {"source_url": str(response.url)}


def local_page(rows: list, limit: int, offset: int, **metadata: Any) -> dict:
    """Slice byte-bounded, unpaginated upstream lists; explicitly identify local paging."""
    paging = page(limit, offset)
    return {**metadata, **paging, "results": rows[offset:offset + limit], "total": len(rows),
            "truncated": offset + limit < len(rows), "pagination": "local"}
