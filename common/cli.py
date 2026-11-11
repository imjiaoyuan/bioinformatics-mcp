"""Manage installed bioinformatics MCP server commands: list, configure, serve, call."""
from __future__ import annotations

import argparse
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE = "git+https://github.com/imjiaoyuan/bioinformatics-mcp.git"
ENVIRONMENT_VARIABLES = {
    "ncbi": ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"],
    "publications": ["NCBI_EMAIL"],
    "bioconductor": ["BIOC_VERSION"],
    "sra": ["NCBI_EMAIL", "NCBI_API_KEY"],
    "clinvar": ["NCBI_EMAIL", "NCBI_API_KEY"],
    "biogrid": ["BIOGRID_API_KEY"],
    "disgenet": ["DISGENET_API_KEY"],
}


def server_commands() -> dict[str, str]:
    return {
        entry.name.removesuffix("-mcp"): entry.name
        for entry in distribution("bioinformatics-mcp").entry_points
        if entry.group == "console_scripts" and entry.value.startswith("servers.")
    }


def find_command(command: str) -> str:
    installed = shutil.which(command)
    if installed:
        return os.path.abspath(installed)
    # uv tool/pipx may expose only the management command on PATH.
    sibling = Path(sys.executable).parent / (command + (".exe" if os.name == "nt" else ""))
    if sibling.is_file() and os.access(sibling, os.X_OK):
        return str(sibling.absolute())
    raise ValueError(f"Cannot find {command}; install bioinformatics-mcp or add its bin directory to PATH")


def ensure_uvx() -> None:
    if shutil.which("uvx") is None:
        raise ValueError("--uvx requires uvx on PATH; install uv first")


def build_entries(selected: list[str], *, serve: bool, uvx: bool) -> dict[str, dict]:
    if serve:
        if uvx:
            command, arguments = "uvx", ["--from", SOURCE, "bioinformatics-mcp", "serve", *selected]
        else:
            command, arguments = find_command("bioinformatics-mcp"), ["serve", *selected]
        return {"bioinformatics": {"command": command, **({"args": arguments} if arguments else {})}}
    if uvx:
        ensure_uvx()
        return {name: {"command": "uvx", "args": ["--from", SOURCE, f"{name}-mcp"]} for name in selected}
    return {name: {"command": find_command(f"{name}-mcp")} for name in selected}


def merge_config(path: Path, entries: dict, *, replace: bool) -> None:
    if path.is_symlink():
        raise ValueError("Config path must not be a symlink")
    original = path.read_text(encoding="utf-8") if path.exists() else None
    config = json.loads(original) if original is not None else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Expected a JSON object with an mcpServers object")
    servers = config.setdefault("mcpServers", {})
    conflicts = [name for name, entry in entries.items()
                 if name in servers and servers[name] != entry]
    if conflicts and not replace:
        raise ValueError(f"Existing entries differ: {', '.join(conflicts)}; use --replace to update them")
    servers.update(entries)
    content = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    if content == original:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        # Exclusive creation preserves the first backup on repeated registrations.
        try:
            with path.with_name(path.name + ".bak").open("x", encoding="utf-8") as backup:
                os.chmod(backup.name, 0o600)
                backup.write(original)
        except FileExistsError:
            pass
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as output:
            temporary = output.name
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def print_toml(entries: dict[str, dict], selected: list[str]) -> None:
    variables = list(dict.fromkeys(name for provider in selected
                                   for name in ENVIRONMENT_VARIABLES.get(provider, [])))
    for name, entry in entries.items():
        print(f"[mcp_servers.{name}]")
        print(f"command = {json.dumps(entry['command'])}")
        if entry.get("args"):
            print(f"args = {json.dumps(entry['args'])}")
        if variables:
            print(f"env_vars = {json.dumps(variables)}")
        print()


def main(argv: list[str] | None = None) -> None:
    commands = server_commands()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("list", help="List available provider names")
    for action in ("config", "register"):
        sub = subparsers.add_parser(action, help="Print configuration" if action == "config"
                                    else "Merge entries into an mcpServers JSON file")
        sub.add_argument("servers", nargs="+", choices=sorted(commands), metavar="SERVER")
        sub.add_argument("--serve", action="store_true",
                         help="Emit one aggregated entry serving all selected providers")
        sub.add_argument("--uvx", action="store_true",
                         help="Emit uvx entries that install on demand, without fixed paths")
        if action == "config":
            sub.add_argument("--format", choices=("json", "toml"), default="json")
        else:
            sub.add_argument("--config", type=Path, required=True, help="Target mcpServers JSON file")
            sub.add_argument("--replace", action="store_true", help="Replace conflicting selected entries")
    serve = subparsers.add_parser("serve", help="Serve selected providers aggregated in one MCP process")
    serve.add_argument("servers", nargs="+", choices=sorted(commands), metavar="SERVER")
    call = subparsers.add_parser("call", help="Invoke one tool on an installed provider server")
    call.add_argument("provider", choices=sorted(commands), metavar="SERVER")
    call.add_argument("tool", help="Tool name, as shown by the provider's list_tools")
    call.add_argument("arguments", nargs="?", default="{}", help="JSON object with tool arguments")
    call.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for the tool result")
    args = parser.parse_args(argv)
    if args.action == "list":
        print("\n".join(sorted(commands)))
        return
    if args.action == "serve":
        from common.serve import main as serve_main
        serve_main(args.servers)
        return
    if args.action == "call":
        from common.call import main as call_main
        call_main(find_command(f"{args.provider}-mcp"), args.tool, args.arguments, args.timeout)
        return
    try:
        entries = build_entries(args.servers, serve=args.serve, uvx=args.uvx)
        if args.action == "register":
            merge_config(args.config.expanduser(), entries, replace=args.replace)
            print(f"Registered {', '.join(entries)} in {args.config}")
        elif args.format == "json":
            print(json.dumps({"mcpServers": entries}, indent=2))
        else:
            print_toml(entries, args.servers)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
