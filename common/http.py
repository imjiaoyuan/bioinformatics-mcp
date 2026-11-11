"""Bounded requests and validation shared by the provider integrations."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

_locks: dict[str, asyncio.Lock] = {}
_last_request: dict[str, float] = {}
_PRIVATE_PARAMETERS = {"apikey", "ncbiapikey", "accesskey", "accesstoken", "token",
                       "authorization", "password", "secret", "clientsecret", "email"}


def safe_url(url: str | httpx.URL) -> str:
    """Keep traceable query parameters while removing credentials and contact addresses."""
    parts = urlsplit(str(url))
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if re.sub(r"[^a-z0-9]", "", key.lower()) not in _PRIVATE_PARAMETERS]
    authority = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, authority, parts.path, urlencode(query), ""))


class _SafeHTTPLog(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = re.sub(r"https?://[^\s\"'<>]+", lambda match: safe_url(match.group()), record.getMessage())
        message = re.sub(r"(?i)((?:api[_-]?key|accesskey|access_token|token|email|password|client_secret)=)[^&\s\"'<>]+",
                         r"\1REDACTED", message)
        record.msg, record.args = message, ()
        return True


for _logger_name in ("httpx", "httpcore", "httpcore.http11", "httpcore.http2", "httpcore.connection"):
    logging.getLogger(_logger_name).addFilter(_SafeHTTPLog())


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
                  headers: dict[str, str] | None = None,
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
                                             headers={"User-Agent": "bioinformatics-mcp/0.1", **(headers or {})}) as client:
                    async with client.stream(method, url, params=params, json=json, data=data) as response:
                        if (method == "GET" or retryable) and response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                            try:
                                delay = min(5.0, max(1.0, float(response.headers.get("Retry-After", "1"))))
                            except ValueError:
                                delay = 1.0
                            await asyncio.sleep(delay)
                            continue
                        safe_request = httpx.Request(method, safe_url(response.url))
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError:
                            safe_response = httpx.Response(response.status_code, request=safe_request)
                            raise httpx.HTTPStatusError(f"HTTP {response.status_code} for {safe_request.url}",
                                                        request=safe_request, response=safe_response) from None
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
                                              content=b"".join(chunks), request=safe_request)
            except httpx.RequestError as exc:
                try:
                    target = safe_url(exc.request.url)
                except RuntimeError:
                    target = safe_url(url)
                raise type(exc)(f"Request failed for {target}", request=httpx.Request(method, target)) from None
            finally:
                _last_request[host] = time.monotonic()
    raise RuntimeError("Request retry exhausted")


async def get_json(url: str, params: dict | None = None) -> Any:
    return (await request("GET", url, params=params)).json()
