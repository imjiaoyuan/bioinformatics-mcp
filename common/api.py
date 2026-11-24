"""Small response and input helpers for bounded provider integrations."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any

from common.http import bounded, request, safe_url

_CACHE_MAX_ENTRIES = 256
_DEFAULT_TTL = 60
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_inflight: dict[str, asyncio.Task] = {}


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
                        headers: dict[str, str] | None = None,
                        interval: float = 0.35, max_bytes: int = 8_000_000,
                        ttl: int = _DEFAULT_TTL) -> tuple[Any, dict]:
    """Fetch JSON, caching idempotent GETs for ``ttl`` seconds (256-entry LRU).

    Concurrent identical GETs share one in-flight request instead of hitting the
    upstream repeatedly; pass ``ttl=0`` to disable caching for a call.
    """
    key: str | None = None
    if ttl > 0 and body is None:
        key = url + "?" + str(sorted((params or {}).items())) + "?" + str(sorted((headers or {}).items()))
        hit = _cached(key, ttl)
        if hit is not None:
            data, source = hit
            return data, {**source, "cached": True}
    if key is not None:
        shared = _inflight.get(key)
        if shared is not None:
            data, source = await shared
            return data, {**source, "cached": True}

    async def fetch() -> tuple[Any, dict]:
        response = await request("GET" if body is None else "POST", url, params=params,
                                 json=body, retryable=body is not None, interval=interval,
                                 max_bytes=max_bytes, headers=headers)
        return response.json(), {"source_url": safe_url(response.url)}

    if key is None:
        return await fetch()
    task = asyncio.ensure_future(fetch())
    _inflight[key] = task
    try:
        data, source = await task
        _store(key, (data, source))
        return data, source
    finally:
        if _inflight.get(key) is task:
            _inflight.pop(key, None)


def local_page(rows: list, limit: int, offset: int, **metadata: Any) -> dict:
    """Slice byte-bounded, unpaginated upstream lists; explicitly identify local paging."""
    paging = page(limit, offset)
    return {**metadata, **paging, "results": rows[offset:offset + limit], "total": len(rows),
            "truncated": offset + limit < len(rows), "pagination": "local"}
