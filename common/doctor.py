"""Verify provider servers: installation, required environment, and tool listings."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from common.cli import ENVIRONMENT_VARIABLES, find_command, server_commands
from common.version import installed_version, latest_version

PACKAGE = "bioinformatics-mcp"
_CREDENTIAL_VARIABLES = ("_EMAIL", "_API_KEY", "_PASSWORD")
# Free keys that only unlock higher request rates or bonus data are optional.
_OPTIONAL_KEY_VARIABLES = {"NCBI_API_KEY"}


async def probe(command: str) -> list[str]:
    """Start one provider over stdio, initialize, and return its tool names."""
    params = StdioServerParameters(command=command, env=dict(os.environ))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return sorted(tool.name for tool in (await session.list_tools()).tools)


def upgrade_command() -> list[str]:
    """Return the command that upgrades the installed package."""
    uv = shutil.which("uv")
    if uv is not None:
        listed = subprocess.run([uv, "tool", "list"], capture_output=True, text=True)
        if listed.returncode == 0 and PACKAGE in listed.stdout:
            return [uv, "tool", "upgrade", PACKAGE]
    return [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]


def upgrade() -> None:
    result = subprocess.run(upgrade_command())
    if result.returncode == 0:
        print(f"Now {PACKAGE} {installed_version()}; restart MCP clients to pick it up.")


def report(providers: list[str], *, check_release: bool) -> int:
    commands = server_commands()
    version = installed_version()
    failures = 0
    print(f"{PACKAGE} {version}")
    if check_release:
        try:
            latest = asyncio.run(latest_version())
        except (httpx.HTTPError, ValueError, KeyError) as error:
            print(f"latest release: unavailable ({type(error).__name__}: {error})")
        else:
            if latest and latest != version:
                print(f"latest release: {latest} — run 'bioinformatics-mcp update'")
            else:
                print(f"latest release: {latest} (up to date)")
    for provider in providers:
        required = [name for name in ENVIRONMENT_VARIABLES.get(provider, [])
                    if name.endswith(_CREDENTIAL_VARIABLES)
                    and name not in _OPTIONAL_KEY_VARIABLES]
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            failures += 1
            print(f"✗ {provider}: missing environment variables: {', '.join(missing)}")
            continue
        try:
            tools = asyncio.run(probe(find_command(f"{provider}-mcp")))
        except Exception as error:  # diagnostics must survive any startup failure
            failures += 1
            print(f"✗ {provider}: {type(error).__name__}: {error}")
            continue
        print(f"✓ {provider}: {len(tools)} tools")
        hints = [name for name in ENVIRONMENT_VARIABLES.get(provider, [])
                 if name.endswith("_API_KEY") and not os.getenv(name)
                 and name not in required]
        if hints:
            print(f"  hint: set {', '.join(hints)} for higher request rates")
    return failures


def main(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="action", required=True)
    check = subparsers.add_parser("check", help="Check providers, environment, and release status")
    check.add_argument("providers", nargs="*", help="Providers to check (default: all)")
    check.add_argument("--offline", action="store_true", help="Skip the release check")
    subparsers.add_parser("install", help="Upgrade the installed package")
    args = parser.parse_args(argv)
    if args.action == "install":
        upgrade()
        return
    selected = args.providers or list(server_commands())
    unknown = [name for name in selected if name not in server_commands()]
    if unknown:
        parser.error(f"Unknown providers: {', '.join(unknown)}; run 'bioinformatics-mcp list'")
    raise SystemExit(report(selected, check_release=not args.offline))


if __name__ == "__main__":
    main()
