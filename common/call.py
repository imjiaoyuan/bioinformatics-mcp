"""Invoke one tool on an installed provider server over stdio and print the result."""
from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _text(result) -> str:
    return "\n".join(block.text for block in result.content if getattr(block, "type", "") == "text")


async def call(command: str, tool: str, arguments: str, timeout: float) -> None:
    try:
        payload = json.loads(arguments)
    except json.JSONDecodeError as error:
        raise ValueError(f"arguments must be a JSON object: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("arguments must be a JSON object")
    params = StdioServerParameters(command=command, env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            discovered = {item.name for item in (await session.list_tools()).tools}
            result = None
            failure: Exception | None = None
            if tool not in discovered:
                failure = ValueError(f"unknown tool {tool!r}; available: {', '.join(sorted(discovered))}")
            else:
                try:
                    result = await asyncio.wait_for(session.call_tool(tool, payload), timeout)
                except TimeoutError as error:
                    failure = error
    if failure is not None:
        raise failure
    if result.is_error:
        raise RuntimeError(_text(result) or "tool reported an error")
    content = result.structured_content
    if content is None:
        text = _text(result)
        try:
            content = json.loads(text)
        except json.JSONDecodeError:
            content = None
    if content is None:
        print(_text(result))
    else:
        print(json.dumps(content, indent=2, ensure_ascii=False))


def main(command: str, tool: str, arguments: str, timeout: float) -> None:
    try:
        asyncio.run(call(command, tool, arguments, timeout))
    except Exception as error:
        hint = "" if isinstance(error, (ValueError, RuntimeError, TimeoutError)) else \
            " (provider server failed to start or closed the connection; run it directly to see its error)"
        print(f"bioinformatics-mcp call: {error}{hint}", file=sys.stderr)
        raise SystemExit(1) from None
