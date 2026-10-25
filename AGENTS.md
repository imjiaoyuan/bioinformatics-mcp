# Repository Guidelines

## Project Structure & Module Organization

This repository contains independent Python MCP servers for bioinformatics services. Each server lives in its own package under `servers/`:

```text
servers/ncbi_mcp/
servers/pdb_mcp/
servers/string_mcp/
servers/ensembl_mcp/
servers/bioconductor_mcp/
servers/anaconda_mcp/
servers/cncb_mcp/
servers/publications_mcp/
```

Each package exposes a `server.py` with a `main()` entry point. `pyproject.toml` defines the executable names. Shared helpers belong in `common/`; do not copy transport, caching, or rate-limit logic between providers. Documentation is in `README.md`. Tests should be added under `tests/` as coverage grows.

## Build, Test, and Development Commands

Create an environment and install the project in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run an individual server over stdio, for example:

```bash
NCBI_EMAIL=you@example.org ncbi-mcp
publications-mcp
```

Run the baseline syntax check before submitting changes:

```bash
python -m compileall -q servers
```

When tests exist, run them with `pytest` from the repository root.

## Coding Style & Naming Conventions

Use Python 3.10+ with four-space indentation, type hints, and small async functions for HTTP calls. Use `snake_case` for modules, functions, and MCP tools; use descriptive provider prefixes such as `pdb_`, `cncb_`, and `publication_`. Keep tool inputs bounded and validate identifiers, formats, and result limits at the server boundary. Format and lint additions with the project’s configured tooling when introduced.

## Testing Guidelines

Prefer deterministic tests with mocked HTTP responses; do not depend on live database availability or API keys. Name files `test_<provider>.py` and test both successful responses and rate-limit/API errors. Every new tool should have at least one validation test.

## Commit & Pull Request Guidelines

Use imperative, focused commit subjects such as `Add Ensembl overlap tool` or `Fix PubMed date filters`. Pull requests should explain the provider/API changes, list new tools and environment variables, include validation commands and results, and call out licensing, rate-limit, or authentication constraints.

## Security & Configuration

Keep API keys and email addresses in environment variables; never commit credentials. Respect each provider’s rate limits, terms, and copyright rules. Return source identifiers and URLs so results remain traceable.
