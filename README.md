# bioinformatics-mcp

Copy the prompt below into your AI agent. 

```text
Clone and use https://github.com/imjiaoyuan/bioinformatics-mcp. If it is already checked out, use that checkout.
Read its README.md and AGENTS.md. List every available MCP server and its capabilities. For my task, choose the smallest useful set, install the project from the repository root, configure the selected servers in this agent's MCP configuration, and verify each connection. Ask only when a choice or credential is required. Keep secrets in environment variables.
```

Installation commands must run **from the cloned repository root**, the directory containing `pyproject.toml`:

```bash
git clone https://github.com/imjiaoyuan/bioinformatics-mcp.git
cd bioinformatics-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The install creates these executable MCP servers:

| Command | Provider |
| --- | --- |
| `ncbi-mcp` | NCBI and PubMed |
| `publications-mcp` | Cell, Nature, PNAS, and Science metadata |
| `pdb-mcp` | RCSB Protein Data Bank |
| `string-mcp` | STRING interactions and enrichment |
| `ensembl-mcp` | Ensembl identifiers and genomic features |
| `bioconductor-mcp` | Bioconductor package registry |
| `anaconda-mcp` | Anaconda and Conda packages |
| `cncb-mcp` | CNCB-NGDC resources |

## Agent configuration

Each command is an MCP stdio server. An agent should configure the selected command with the repository root as its working directory. For example:

```json
{
  "mcpServers": {
    "publications": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/publications-mcp",
      "cwd": "<REPOSITORY_ROOT>"
    }
  }
}
```

Use the equivalent MCP configuration file or CLI command for Codex, Claude Code, Pi, OpenCode, or DeepSeek Harness. `NCBI_EMAIL` is required for NCBI; `NCBI_API_KEY` is optional and only needed for higher request rates.

## Development

From the repository root:

```bash
python -m compileall -q servers
```

Provider implementations are under `servers/`. Keep credentials in environment variables and follow each provider's rate limits, licensing, and copyright terms.
