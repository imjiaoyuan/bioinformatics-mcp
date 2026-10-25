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
| `ensembl-mcp` | Ensembl/Ensembl Plants annotations, sequences and homology |
| `bioconductor-mcp` | Bioconductor package registry |
| `anaconda-mcp` | Anaconda and Conda packages |
| `cncb-mcp` | CNCB-NGDC resources |
| `ena-mcp` | ENA study/sample/run search and FASTQ metadata |
| `uniprot-mcp` | Protein annotations, sequences and batch ID mapping |
| `gprofiler-mcp` | GO/pathway enrichment, gene ID conversion and orthologs |
| `biostudies-mcp` | BioStudies/ArrayExpress studies, files and SDRF metadata |
| `interpro-mcp` | InterPro/Pfam families, domains, GO annotations and protein matches |

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

## Additional provider tools

### GEO (included in ncbi-mcp)

`geo_search` searches GEO summaries, `geo_record` reads GSE/GSM SOFT metadata
(including sample characteristics), and `geo_files` lists actual matrix and
supplement URLs. File contents are not downloaded. Entrez `gds` and `geoprofiles`
are also available through the generic NCBI tools. Entrez calls require
`NCBI_EMAIL`; `NCBI_API_KEY` remains optional. [Official GEO access guide](https://www.ncbi.nlm.nih.gov/geo/info/geo_paccess.html).

### ENA

ENA tools: `ena_search`, `ena_record`, `ena_fastq`, `ena_fields`. Search uses
ENA Portal syntax and supports bounded pagination. FASTQ results include public
HTTPS URLs, MD5 checksums and file sizes; no downloads are started. No credentials
are required for public records. [ENA API guide](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access.html).

### UniProt

UniProt tools: `uniprot_search`, `uniprot_entry`, `uniprot_sequence`,
`uniprot_mapping_submit`, `uniprot_mapping_status`, `uniprot_mapping_results`.
Mapping is asynchronous: submit IDs, check the returned job ID, then fetch a
bounded result page. Failed mappings and pagination links are preserved. Database
codes follow the [official ID mapping configuration](https://rest.uniprot.org/configure/idmapping/fields).
Public queries require no credentials. [UniProt API](https://www.uniprot.org/help/api).

### g:Profiler

g:Profiler tools: `gprofiler_enrichment`, `gprofiler_convert`, `gprofiler_orthologs`.
The enrichment tool defaults to GO BP/MF/CC, supports a custom background of
detected genes and reports correction/version metadata and truncation explicitly.
Organism codes and data-source availability follow [g:Profiler](https://biit.cs.ut.ee/gprofiler/page/apis).
Conversion targets are `ENTREZGENE_ACC` (default), `ENSG` and `UNIPROTSWISSPROT`.
Public calls require no credentials; selecting KEGG does not grant rights to its data.

### BioStudies / ArrayExpress

BioStudies tools: `biostudies_search`, `biostudies_record`, `biostudies_files`,
`biostudies_samples`. Searches default to ArrayExpress; use `collection="all"`
for all BioStudies. Study trees preserve ENA links. Files support offset pagination;
SDRF results contain columns and assay rows, preserving duplicate column names.
Assay rows are not deduplicated into biological samples. No credentials are needed
for public data. [ArrayExpress in BioStudies](https://www.ebi.ac.uk/biostudies/arrayexpress).

### Ensembl Plants

Ensembl Plants uses the existing `ensembl-mcp` server. Added `ensembl_species`
(species/assembly discovery), `ensembl_lookup_batch` (100 IDs), `ensembl_sequence`
and `ensembl_homologs`. Rice defaults to `oryza_sativa`; compare the returned
assembly/release to your reference before using IDs. No implicit conversion
between RAP-DB, MSU or other annotation versions is performed. Homology defaults
to `compara="plants"`, and protein sequences should use transcript/translation IDs.
Public calls need no credentials. [Ensembl Plants REST guide](https://jun2026-plants.ensembl.org/info/data/rest.html).

### InterPro

InterPro tools: `interpro_search`, `interpro_entry`,
`interpro_protein_annotations`, `interpro_proteins`. These retrieve existing
annotations rather than running InterProScan on novel sequences. IPR/PF records,
protein match locations and taxon-filtered protein lists preserve source IDs and
pagination. HTTP 408 is reported as pending computation, distinct from an empty
result. Public calls need no credentials. [InterPro API guide](https://interpro-documentation.readthedocs.io/en/latest/api.html).

## Development

Cancer-data API research and proposed next integrations are documented in
[Cancer data API options](docs/cancer-apis.md). GDC/TCGA and cBioPortal public
queries have been checked; these providers are not implemented yet.

From the repository root:

```bash
python -m compileall -q servers
python -m unittest discover -s tests -v
python -m pip check
```

Regression tests use mocked HTTP responses and need no network or API keys.

Provider implementations are under `servers/`. Keep credentials in environment variables and follow each provider's rate limits, licensing, and copyright terms.
