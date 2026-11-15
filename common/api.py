"""Small response and input helpers for bounded provider integrations."""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

from common.http import bounded, request, safe_url

_CACHE_MAX_ENTRIES = 256
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def _cached(key: str, ttl: int) -> Any | None:
    entry = _cache.get(key)
    if entry is not None and time.monotonic() - entry[0] < ttl:
        _cache.move_to_end(key)
        return entry[1]
    return None


def _store(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def choice(value: str, values: set[str], name: str) -> str:
    if value not in values:
        raise ValueError(f"{name} must be one of {', '.join(sorted(values))}")
    return value


def page(limit: int, offset: int) -> dict:
    return {"limit": bounded(limit), "offset": bounded(offset, 1_000_000, "offset", 0)}


async def json_response(url: str, params: dict | None = None, *, body: Any = None,
                        interval: float = 0.35, max_bytes: int = 8_000_000,
                        ttl: int = 0) -> tuple[Any, dict]:
    """Fetch JSON, optionally caching idempotent GETs for ``ttl`` seconds (256-entry LRU)."""
    key: str | None = None
    if ttl > 0 and body is None:
        key = url + "?" + str(sorted((params or {}).items()))
        hit = _cached(key, ttl)
        if hit is not None:
            data, source = hit
            return data, {**source, "cached": True}
    response = await request("GET" if body is None else "POST", url, params=params,
                             json=body, retryable=body is not None, interval=interval,
                             max_bytes=max_bytes)
    data = response.json()
    source = {"source_url": safe_url(response.url)}
    if key is not None:
        _store(key, (data, source))
    return data, source


def local_page(rows: list, limit: int, offset: int, **metadata: Any) -> dict:
    """Slice byte-bounded, unpaginated upstream lists; explicitly identify local paging."""
    paging = page(limit, offset)
    return {**metadata, **paging, "results": rows[offset:offset + limit], "total": len(rows),
            "truncated": offset + limit < len(rows), "pagination": "local"}
