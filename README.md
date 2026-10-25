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
| `ncbi-mcp` | NCBI, PubMed, and GEO |
| `publications-mcp` | Cell, Nature, PNAS, and Science metadata |
| `pdb-mcp` | RCSB Protein Data Bank |
| `string-mcp` | STRING interactions and enrichment |
| `ensembl-mcp` | Ensembl identifiers and genomic features |
| `bioconductor-mcp` | Bioconductor package registry |
| `anaconda-mcp` | Anaconda and Conda packages |
| `cncb-mcp` | CNCB-NGDC resources |
| `ena-mcp` | ENA study/sample/run search and FASTQ metadata |
| `uniprot-mcp` | Protein annotations, sequences and batch ID mapping |

## Agent configuration

### GEO (included in ncbi-mcp)

`geo_search` searches GEO summaries, `geo_record` reads GSE/GSM SOFT metadata
(including sample characteristics), and `geo_files` lists actual matrix and
supplement URLs. File contents are not downloaded. Entrez `gds` and `geoprofiles`
are also available through the generic NCBI tools. Entrez calls require
`NCBI_EMAIL`; `NCBI_API_KEY` remains optional. [Official GEO access guide](https://www.ncbi.nlm.nih.gov/geo/info/geo_paccess.html).

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

For Codex, forward existing environment variables using `env_vars`; values such as
`"${NCBI_EMAIL}"` in an `env` table are literal strings:

```toml
[mcp_servers.ncbi]
command = "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp"
cwd = "<REPOSITORY_ROOT>"
env_vars = ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"]
```

Export these variables before starting the agent. Do not store credentials in the
repository. Bioconductor defaults to release 3.21; set `BIOC_VERSION` in the server
environment to select another release. `string_interactions.limit` caps returned
edges locally; it does not expand the input protein set.

## Development

UniProt tools: `uniprot_search`, `uniprot_entry`, `uniprot_sequence`,
`uniprot_mapping_submit`, `uniprot_mapping_status`, `uniprot_mapping_results`.
Mapping is asynchronous: submit IDs, check the returned job ID, then fetch a
bounded result page. Failed mappings and pagination links are preserved. Database
codes follow the [official ID mapping configuration](https://rest.uniprot.org/configure/idmapping/fields).
Public queries require no credentials. [UniProt API](https://www.uniprot.org/help/api).

ENA tools: `ena_search`, `ena_record`, `ena_fastq`, `ena_fields`. Search uses
ENA Portal syntax and supports bounded pagination. FASTQ results include public
HTTPS URLs, MD5 checksums and file sizes; no downloads are started. No credentials
are required for public records. [ENA API guide](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access.html).

From the repository root:

```bash
python -m compileall -q servers
python -m unittest discover -s tests -v
python -m pip check
```

Regression tests use mocked HTTP responses and need no network or API keys.

Provider implementations are under `servers/`. Keep credentials in environment variables and follow each provider's rate limits, licensing, and copyright terms.
