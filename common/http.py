"""Bounded requests and validation shared by the provider integrations."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

_locks: dict[str, asyncio.Lock] = {}
_last_request: dict[str, float] = {}


def text(value: str, name: str = "query", maximum: int = 2000) -> str:
    value = value.strip()
    if not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"{name} must contain 1-{maximum} characters without control characters")
    return value


def identifier(value: str, pattern: str = r"[A-Za-z0-9_.-]+", name: str = "identifier") -> str:
    value = text(value, name, 150)
    if not re.fullmatch(pattern, value):
        raise ValueError(f"Invalid {name}")
    return value


def bounded(value: int, maximum: int = 100, name: str = "limit", minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def identifiers(values: list[str], maximum: int = 1000) -> list[str]:
    if not values or len(values) > maximum:
        raise ValueError(f"identifiers must contain 1-{maximum} items")
    return [text(value, "identifier", 150) for value in values]


async def request(method: str, url: str, *, params: dict | None = None,
                  json: Any = None, data: dict | None = None,
                  max_bytes: int = 8_000_000, interval: float = 0.35,
                  retryable: bool = False) -> httpx.Response:
    """Bound responses and retry transient GET failures or explicitly idempotent requests once."""
    host = urlsplit(url).netloc
    lock = _locks.setdefault(host, asyncio.Lock())
    async with lock:
        for attempt in range(2):
            await asyncio.sleep(max(0, interval - (time.monotonic() - _last_request.get(host, 0))))
            try:
                async with httpx.AsyncClient(timeout=45, follow_redirects=True,
                                             headers={"User-Agent": "bioinformatics-mcp/0.1"}) as client:
                    async with client.stream(method, url, params=params, json=json, data=data) as response:
                        if (method == "GET" or retryable) and response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                            try:
                                delay = min(5.0, max(1.0, float(response.headers.get("Retry-After", "1"))))
                            except ValueError:
                                delay = 1.0
                            await asyncio.sleep(delay)
                            continue
                        response.raise_for_status()
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise ValueError("Response is too large; narrow the query or reduce the limit")
                            chunks.append(chunk)
                        await response.aclose()
                        headers = {k: v for k, v in response.headers.items()
                                   if k not in {"content-encoding", "content-length"}}
                        return httpx.Response(response.status_code, headers=headers,
                                              content=b"".join(chunks), request=response.request)
            finally:
                _last_request[host] = time.monotonic()
    raise RuntimeError("Request retry exhausted")


async def get_json(url: str, params: dict | None = None) -> Any:
    return (await request("GET", url, params=params)).json()
