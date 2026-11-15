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
    "variation": ["NCBI_EMAIL", "NCBI_API_KEY"],
    "taxonomy": ["NCBI_EMAIL", "NCBI_API_KEY"],
    "phytozome": ["JGI_EMAIL", "JGI_PASSWORD"],
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


def build_entries(selected: list[str], *, serve: bool, uvx: bool, ref: str | None = None,
                  name: str = "bioinformatics") -> dict[str, dict]:
    source = SOURCE if ref is None else f"{SOURCE}@{ref}"
    if serve:
        if uvx:
            command, arguments = "uvx", ["--from", source, "bioinformatics-mcp", "serve", *selected]
        else:
            command, arguments = find_command("bioinformatics-mcp"), ["serve", *selected]
        return {name: {"command": command, **({"args": arguments} if arguments else {})}}
    if uvx:
        ensure_uvx()
        return {entry_name: {"command": "uvx", "args": ["--from", source, f"{entry_name}-mcp"]} for entry_name in selected}
    return {entry_name: {"command": find_command(f"{entry_name}-mcp")} for entry_name in selected}


def merge_config(path: Path, entries: dict, *, replace: bool, remove: bool = False) -> None:
    if path.is_symlink():
        raise ValueError("Config path must not be a symlink")
    original = path.read_text(encoding="utf-8") if path.exists() else None
    config = json.loads(original) if original is not None else {}
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("Expected a JSON object with an mcpServers object")
    servers = config.setdefault("mcpServers", {})
    if remove:
        unknown = [key for key in entries if key not in servers]
        if unknown:
            raise ValueError(f"Not registered: {', '.join(unknown)}")
        for key in entries:
            del servers[key]
    else:
        conflicts = [entry_name for entry_name, entry in entries.items()
                     if entry_name in servers and servers[entry_name] != entry]
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
    subparsers.add_parser("list", help="List available providers grouped by category with selection numbers")
    for action in ("config", "register"):
        sub = subparsers.add_parser(action, help="Print configuration" if action == "config"
                                    else "Merge or remove entries in an mcpServers JSON file")
        sub.add_argument("servers", nargs="+" if action == "config" else "*", metavar="SERVER",
                         help="Provider names or numbers, e.g. ensembl, 1.3, 2")
        sub.add_argument("--serve", action="store_true",
                         help="Emit one aggregated entry serving all selected providers")
        sub.add_argument("--uvx", action="store_true",
                         help="Emit uvx entries that install on demand, without fixed paths")
        sub.add_argument("--ref", help="Pin the git source to a tag, e.g. v0.2.0 (with --uvx)")
        if action == "config":
            sub.add_argument("--format", choices=("json", "toml"), default="json")
            sub.add_argument("--name", default="bioinformatics",
                             help="Entry key for the aggregated --serve entry (default: bioinformatics)")
        else:
            sub.add_argument("--config", type=Path, required=True, help="Target mcpServers JSON file")
            sub.add_argument("--replace", action="store_true", help="Replace conflicting selected entries")
            sub.add_argument("--remove", action="store_true",
                             help="Remove the selected entries instead of adding them")
    doctor = subparsers.add_parser("doctor", help="Check providers, required environment, and release status")
    doctor.add_argument("servers", nargs="*", metavar="SERVER", help="Providers to check (default: all)")
    doctor.add_argument("--offline", action="store_true", help="Skip the release check")
    subparsers.add_parser("update", help="Upgrade the installed package")
    serve = subparsers.add_parser("serve", help="Serve selected providers aggregated in one MCP process")
    serve.add_argument("servers", nargs="+", metavar="SERVER",
                       help="Provider names or numbers, e.g. ensembl, 1.3, 2")
    call = subparsers.add_parser("call", help="Invoke one tool on an installed provider server")
    call.add_argument("provider", metavar="SERVER", help="Provider name or number, e.g. ensembl, 1.3")
    call.add_argument("tool", help="Tool name, as shown by the provider's list_tools")
    call.add_argument("arguments", nargs="?", default="{}", help="JSON object with tool arguments")
    call.add_argument("--timeout", type=float, default=120.0, help="Seconds to wait for the tool result")
    args = parser.parse_args(argv)
    from common.categories import format_list, resolve_selections
    if args.action == "list":
        print(format_list(commands))
        return
    if args.action == "update":
        from common.doctor import upgrade
        upgrade()
        return
    if args.action == "doctor":
        from common.doctor import main as doctor_main
        doctor_main(["check", *args.servers, *(["--offline"] if args.offline else [])])
        return
    if args.action == "call":
        provider, = resolve_selections([args.provider], commands)
        from common.call import main as call_main
        call_main(find_command(f"{provider}-mcp"), args.tool, args.arguments, args.timeout)
        return
    if args.action == "register" and not args.servers:
        parser.error("register requires at least one SERVER unless --remove targets specific servers")
    if getattr(args, "ref", None) and not args.uvx:
        parser.error("--ref applies to --uvx entries that install from the git source")
    try:
        args.servers = resolve_selections(args.servers, commands)
    except ValueError as error:
        parser.error(str(error))
    if args.action == "serve":
        from common.serve import main as serve_main
        serve_main(args.servers)
        return
    try:
        if args.action == "register":
            if not args.servers:
                parser.error("register --remove requires at least one SERVER")
            entries = build_entries(args.servers, serve=args.serve, uvx=args.uvx, ref=args.ref)
            merge_config(args.config.expanduser(), entries, replace=args.replace, remove=args.remove)
            verb = "Removed" if args.remove else "Registered"
            print(f"{verb} {', '.join(entries)} {'from' if args.remove else 'in'} {args.config}")
        else:
            entries = build_entries(args.servers, serve=args.serve, uvx=args.uvx, ref=args.ref, name=args.name)
            if args.format == "json":
                print(json.dumps({"mcpServers": entries}, indent=2))
            else:
                print_toml(entries, args.servers)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
