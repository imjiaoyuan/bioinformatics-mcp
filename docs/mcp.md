# Connecting MCP clients

This repository ships independent MCP stdio servers, one console command per
bioinformatics provider. They speak only the standard MCP protocol, so any
MCP-capable client works the same way: pick the commands you need, point the
client at the installed executable, and pass credentials through environment
variables. This page gives the exact configuration shape for common clients.
If yours is missing, read the generic pattern first — most clients copy it.

For globally installed commands (`uv tool`, pipx, or system packages), use
`bioinformatics-mcp config publications pdb` to print ready-to-use
`mcpServers` JSON with discovered absolute executable paths. Use
`bioinformatics-mcp register publications pdb --config /path/to/mcp.json`
to merge those entries directly into a plain `mcpServers` JSON file. Existing
settings are preserved, conflicts require `--replace`, and the first original
file is backed up with a `.bak` suffix. This command does not support JSONC or
other client schemas. Use `config ... --format toml` for a Codex fragment.
Export credentials before launching the client; JSON entries rely on inherited
environment variables, while the TOML output includes `env_vars` for providers
that use them. No repository checkout or `cwd` is required in either case.

The manual development-install examples below use `<REPOSITORY_ROOT>` for the absolute path of the cloned
`bioinformatics-mcp` checkout. Examples configure one or two servers; repeat
the entry shape for each additional command you need. Prefer the smallest set
that covers the task: every connected server adds its tool schemas to the
context window, and some clients also cap the number of servers.

## Prerequisites

```bash
cd <REPOSITORY_ROOT>
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Every server is then available as `<REPOSITORY_ROOT>/.venv/bin/<command>-mcp`.
The `cellxgene-mcp` cell-level tools need the optional SDK in a separate
Python 3.10–3.13 environment (see the README); use
`<REPOSITORY_ROOT>/.venv-cellxgene/bin/cellxgene-mcp` for that server.

Environment variables servers read from their process environment:

| Variable | Used by | Required | Purpose |
| --- | --- | --- | --- |
| `NCBI_EMAIL` | `ncbi-mcp` | Yes | Entrez contact address |
| `NCBI_API_KEY` | `ncbi-mcp` | No | Higher request rates |
| `NCBI_TOOL` | `ncbi-mcp` | No | Entrez tool name (default `ncbi-mcp`) |
| `NCBI_EMAIL` | `publications-mcp` | No | Contact address in the HTTP User-Agent |
| `BIOC_VERSION` | `bioconductor-mcp` | No | Bioconductor release (default `3.21`) |

No other server needs credentials. Keep secrets out of the repository.

## Generic pattern

Every server is a local stdio MCP server: an executable, an optional working
directory, and environment variables. In the usual `mcpServers` JSON dialect
that nearly every client understands:

```json
{
  "mcpServers": {
    "publications": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/publications-mcp",
      "cwd": "<REPOSITORY_ROOT>"
    },
    "ncbi": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp",
      "cwd": "<REPOSITORY_ROOT>",
      "env": {"NCBI_EMAIL": "you@example.org", "NCBI_API_KEY": "..."}
    }
  }
}
```

If your client has no `cwd` field, set `command` to an absolute path. The
servers resolve no paths relative to the checkout, so `cwd` is a convenience
rather than a requirement.

If your client's format is not on this page, convert from this pattern:
`command` + `args` (here the executable path with no arguments), `env`, and
`cwd`.

## Claude Code

CLI (writes to `~/.claude.json`; add `--scope project` to write `.mcp.json`
in the repository instead, or `--scope user` for all projects):

```bash
claude mcp add ncbi --env NCBI_EMAIL=you@example.org -- \
  <REPOSITORY_ROOT>/.venv/bin/ncbi-mcp
claude mcp add publications -- <REPOSITORY_ROOT>/.venv/bin/publications-mcp
claude mcp list   # verify each server shows Connected
```

JSON equivalent (`.mcp.json` in the project, or `~/.claude.json`):

```json
{
  "mcpServers": {
    "publications": {
      "type": "stdio",
      "command": "<REPOSITORY_ROOT>/.venv/bin/publications-mcp",
      "cwd": "<REPOSITORY_ROOT>"
    },
    "ncbi": {
      "type": "stdio",
      "command": "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp",
      "env": {"NCBI_EMAIL": "you@example.org", "NCBI_API_KEY": "..."}
    }
  }
}
```

Claude Code sets `CLAUDE_PROJECT_DIR` in each server's environment. In a
`.mcp.json` entry you can use it for project-relative paths, for example
`"cwd": "${CLAUDE_PROJECT_DIR}"`; with a literal `cwd` this is unnecessary.
`${VAR}` references in `command`/`args`/`env` values expand from the parent
environment.

## Codex

`~/.codex/config.toml`. Codex forwards environment variables by name with
`env_vars` — values such as `"${NCBI_EMAIL}"` in an `env` table are literal
strings, not expansions, so do not use that form:

```toml
[mcp_servers.publications]
command = "<REPOSITORY_ROOT>/.venv/bin/publications-mcp"
cwd = "<REPOSITORY_ROOT>"

[mcp_servers.ncbi]
command = "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp"
cwd = "<REPOSITORY_ROOT>"
env_vars = ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"]
```

Export the forwarded variables before starting Codex. Set `enabled = false`
on an entry to keep it configured but disconnected. Verify with
`codex mcp list`.

## Pi

User-level servers live in `~/.pi/agent/mcp.json`, project servers in
`.pi/mcp.json` (read only in a trusted project). The format matches the
generic `mcpServers` pattern; stdio entries accept `command`, `args`, `env`,
and `cwd`:

```json
{
  "mcpServers": {
    "publications": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/publications-mcp",
      "cwd": "<REPOSITORY_ROOT>"
    },
    "ncbi": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp",
      "cwd": "<REPOSITORY_ROOT>",
      "env": {"NCBI_EMAIL": "${NCBI_EMAIL}", "NCBI_API_KEY": "${NCBI_API_KEY}"}
    }
  }
}
```

Pi expands `${VAR}` in `env` values from the environment, so export the
variables before starting Pi. CLI alternative:

```bash
pi mcp add ncbi --env NCBI_EMAIL='${NCBI_EMAIL}' -- \
  <REPOSITORY_ROOT>/.venv/bin/ncbi-mcp
pi mcp list   # connect to every enabled server and print state and errors
```

Add `-l`/`--local` to `pi mcp add` to write the project file. Use `/mcp` in a
session to inspect connections. With 20 servers available, Pi's default
`codemode` exposure is a good fit: tool schemas stay out of the context until
a script needs them; use `direct` exposure (or `toolExposure`) only for a
small, frequently used set.

## OpenCode

Servers are configured under `mcp` in `opencode.json` / `opencode.jsonc`
(project) or `~/.config/opencode/opencode.json` (global). Local stdio servers
use `"type": "local"` with `command` as an **array** and environment variables
under `environment`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "publications": {
      "type": "local",
      "command": ["<REPOSITORY_ROOT>/.venv/bin/publications-mcp"],
      "cwd": "<REPOSITORY_ROOT>",
      "enabled": true
    },
    "ncbi": {
      "type": "local",
      "command": ["<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp"],
      "cwd": "<REPOSITORY_ROOT>",
      "environment": {"NCBI_EMAIL": "{env:NCBI_EMAIL}", "NCBI_API_KEY": "{env:NCBI_API_KEY}"},
      "enabled": true
    }
  }
}
```

`{env:NAME}` resolves from the environment at launch. If `{env:...}` does not
work in `environment` on your version, export the variables before starting
OpenCode instead — a local server inherits the parent environment either way.
MCP tools appear prefixed with the server name (for example
`ncbi_pubmed_search`); you can refer to them as `use ncbi` in prompts, or
enable/disable them (glob patterns allowed) under `tools`.

## DeepSeek Harness (yak)

yak bridges MCP servers through its resident `mcp_bridge` extension.
Configuration lives in `~/.yak/extensions/mcp.json` (an `{"mcpServers": ...}`
wrapper is unwrapped when present):

```json
{
  "mcpServers": {
    "publications": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/publications-mcp"
    },
    "ncbi": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp",
      "env": {"NCBI_EMAIL": "${NCBI_EMAIL}", "NCBI_API_KEY": "${NCBI_API_KEY}"}
    }
  }
}
```

Notes specific to the bridge:

- `env` rides along with the inherited environment; `${VAR}` in any string
  value expands from the environment, and an unset variable is an error
  rather than an empty string. Export `NCBI_EMAIL` before starting yak.
- There is no `cwd` field; the server inherits yak's working directory. This
  is fine for these servers, which resolve no paths relative to the checkout.
- Tools mount as `<server>__<tool>` (for example `ncbi__pubmed_search`) and
  a `tools` filter per entry can trim the mounted set before schemas reach
  the context:
  `"tools": {"only": ["pubmed_*"]}`.
- `mcp_bridge` must not be in `extensions.disabled` in `~/.yak/config.json`.
- A server that fails to start or finish the initialize handshake is skipped
  with a warning; the rest keep working. `tool_timeout` (default 120s)
  bounds every call.
- Verify by asking yak to list its tools (or calling a cheap one) and
  checking that the `ncbi__...` / `publications__...` entries appear.

## Claude Desktop, Cursor, and other clients

Clients that document the plain `mcpServers` JSON dialect (Claude Desktop,
Cursor, Cline, VS Code MCP, …) take the [generic pattern](#generic-pattern)
as-is, usually under their own settings key. VS Code (`mcp.json` in
`.vscode/`) and Cursor (`.cursor/mcp.json`) additionally support
`${input:name}` prompts; `${VAR}` environment expansion works in most of
them — when in doubt, write literal values or export variables and omit
`env`. With no `cwd` support, give `command` as an absolute path.

## Verifying a connection

1. List tools through the client (`claude mcp list`, `codex mcp list`,
   `pi mcp list`, `/mcp` panels, or asking the agent to enumerate its tools)
   and confirm the expected server appears connected with its tools.
2. Call a cheap tool, for example `publication_journal_search` or
   `pdb_status`.
3. For `ncbi-mcp`, confirm `NCBI_EMAIL` reached the process (a call fails
   fast with a validation error when it is missing). For error shapes and
   rate limits, see the per-provider notes in the README.
