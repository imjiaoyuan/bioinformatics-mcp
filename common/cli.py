"""Generate client configuration for installed MCP server commands."""
from __future__ import annotations

import argparse
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


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


def main(argv: list[str] | None = None) -> None:
    commands = server_commands()
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("list", help="List available provider names")
    for action in ("config", "register"):
        sub = subparsers.add_parser(action, help="Print configuration" if action == "config"
                                    else "Merge entries into an mcpServers JSON file")
        sub.add_argument("servers", nargs="+", choices=sorted(commands), metavar="SERVER")
        if action == "config":
            sub.add_argument("--format", choices=("json", "toml"), default="json")
        else:
            sub.add_argument("--config", type=Path, required=True, help="Target mcpServers JSON file")
            sub.add_argument("--replace", action="store_true", help="Replace conflicting selected entries")
    args = parser.parse_args(argv)
    if args.action == "list":
        print("\n".join(sorted(commands)))
        return
    try:
        entries = {name: {"command": find_command(commands[name])} for name in args.servers}
        if args.action == "register":
            merge_config(args.config.expanduser(), entries, replace=args.replace)
            print(f"Registered {', '.join(entries)} in {args.config}")
        elif args.format == "json":
            print(json.dumps({"mcpServers": entries}, indent=2))
        else:
            for name, entry in entries.items():
                print(f"[mcp_servers.{name}]")
                print(f"command = {json.dumps(entry['command'])}")
                if name == "ncbi":
                    print('env_vars = ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"]')
                elif name == "publications":
                    print('env_vars = ["NCBI_EMAIL"]')
                elif name == "bioconductor":
                    print('env_vars = ["BIOC_VERSION"]')
                print()
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
