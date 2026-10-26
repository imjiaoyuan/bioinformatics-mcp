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
| `gdc-mcp` | GDC/TCGA projects, cases, file metadata and manifests |
| `reactome-mcp` | Pathways, reactions, participants and gene-to-pathway mapping |
| `cellxgene-mcp` | CELLxGENE Census metadata and bounded expression slices (optional SDK) |
| `chembl-mcp` | Compounds, targets, assays, measured activities and mechanisms |
| `gwas-mcp` | GWAS Catalog REST v2 traits, studies, curated associations and variants |
| `opentargets-mcp` | Target/disease/drug annotations, association scores and evidence |
| `cbioportal-mcp` | Public cancer studies, clinical data, mutations and molecular measurements |

The base install supplies all 20 commands. CELLxGENE data queries additionally
need the optional SDK. Python 3.12 is recommended for this extra; native
TileDB-SOMA wheels may be unavailable for newer Python versions. Use a separate
environment if the existing environment runs Python 3.14:

```bash
python3.12 -m venv .venv-cellxgene
source .venv-cellxgene/bin/activate
python -m pip install -e '.[cellxgene]'
```

This uses standard Python, venv and pip. No additional environment manager is required.
Configure CELLxGENE with `.venv-cellxgene/bin/cellxgene-mcp`; other commands can
continue using the original `.venv`.

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

### GDC / TCGA

Tools: `gdc_projects`, `gdc_cases`, `gdc_files`, `gdc_file`, `gdc_manifest`,
`gdc_download_url`. Project searches default to TCGA; pass `program=null` for all
programs. Cases/files require a project ID, such as `TCGA-BRCA`. File searches
default to open access and support data-type and workflow filters. Lists use
`limit` (1–100) and zero-based `offset`. Manifests accept at most 100 UUIDs and
report unresolved IDs. Download addresses are returned only after checking open
access; no file transfer starts. Controlled metadata can be searched, but token
handling and controlled downloads are outside this implementation.
Preserve case/sample relationships, reference/workflow versions and expression
units when analyzing results. File totals are not patient counts.
[GDC API guide](https://docs.gdc.cancer.gov/API/Users_Guide/Getting_Started/).

### Reactome

Tools: `reactome_search`, `reactome_entry`, `reactome_pathway_events`,
`reactome_participants`, `reactome_pathways_for_gene`. Search uses upstream
pagination starting at `page=1`. Events, participants and gene mappings use local
`limit`/`offset` pagination because those upstream endpoints return whole lists;
the shared response-byte limit still applies. Participants are reference entities,
and contained events include recursively nested pathways/reactions. Gene mapping
accepts `UniProt` or `Ensembl` as the resource and defaults to human. These tools
retrieve pathway content; use the existing g:Profiler tools for enrichment.
[Reactome Content Service](https://reactome.org/dev/content-service).

### CELLxGENE Census

Tools: `cellxgene_versions`, `cellxgene_datasets`, `cellxgene_cells`,
`cellxgene_genes`, `cellxgene_expression`, `cellxgene_dataset_url`. Install the
optional extra as described above. Human and mouse are supported. Metadata tools
resolve `stable`/`latest` to a dated release and return that version explicitly.
Cell filters match exact tissue, cell-type, disease and dataset labels.

Metadata scans inspect a bounded `soma_joinid` window: `after_joinid=-1`,
`scan_size=1000` by default (maximum 10,000), and return at most `limit` rows
(maximum 100). Continue with `next_after_joinid` while `has_more` is true, keeping
the returned dated version fixed. An empty window can have matches in later
windows. `truncated` means more matching rows were found within the current
window; `has_more` also accounts for unsearched windows. Cells are not deduplicated
into biological samples; `is_primary_data` is retained when available.

Expression reads require a dated `version`, explicit cell `soma_joinid` values
from that release, and feature IDs (maximum 100 cells × 100 genes). Returned
cell/gene metadata defines the matrix axis order, with missing IDs reported.
The `raw` layer is returned without normalization; zeros alone do not establish
that a feature was assayed in every source dataset. Dataset URLs return the
official source H5AD locator and start no download.
[Census Python API](https://chanzuckerberg.github.io/cellxgene-census/python-api.html).

### ChEMBL

Tools: `chembl_search`, `chembl_molecule`, `chembl_target`, `chembl_activities`,
`chembl_assay`, `chembl_mechanisms`. Search supports molecule, target and assay
resources. Activities require a target or molecule ChEMBL ID and optionally an
exact `standard_type`, such as `IC50`. All measured activity fields, including
units, relation operators, validity flags and assay/document references, are
preserved. Measurements from different assays/types are not automatically pooled
or converted. Lists preserve `page_meta` and use `limit`/`offset`.
[ChEMBL web services](https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services).

### GWAS Catalog

Tools: `gwas_traits`, `gwas_studies`, `gwas_study`, `gwas_associations`,
`gwas_variant`. Uses REST v2, with zero-based `page`, bounded `limit` and preserved
HAL `_embedded`, `_links` and `page` metadata. Trait search discovers ontology IDs;
association queries accept an ontology ID, rs ID, GCST accession or mapped gene.
`show_child_traits` defaults to false; the extended gene set is disabled. Studies
can be filtered by population descriptor (`ancestral_group`). Associations are
curated top hits rather than complete genome-wide summary statistics; study
records retain available summary-statistics download links. No downloads start.
[GWAS API guide](https://www.ebi.ac.uk/gwas/docs/programmatic-access/rest-api/).

### Open Targets

Tools: `opentargets_search`, `opentargets_target`, `opentargets_disease`,
`opentargets_associations`, `opentargets_drug`, `opentargets_evidence`. Uses fixed
GraphQL templates and variables against the public Platform API. Search returns
IDs; target queries use human Ensembl gene IDs. Association ranking accepts
exactly one target or disease ID, with zero-based `page` and bounded `limit`.
Evidence queries require both IDs and preserve the next cursor. Results include
API/data release metadata and explicitly distinguish `ok`, `partial` and `error`
responses, including GraphQL errors returned with HTTP 200. Association scores
represent aggregated evidence rather than a causal or clinical conclusion.
[GraphQL API guide](https://platform-docs.opentargets.org/data-access/graphql-api).

### cBioPortal

Tools: `cbioportal_studies`, `cbioportal_samples`, `cbioportal_clinical`,
`cbioportal_molecular_profiles`, `cbioportal_mutations`, `cbioportal_molecular_data`.
Uses the public REST API, without the hosted MCP's OAuth flow. Clinical data
distinguishes SAMPLE and PATIENT levels. Discover profiles before querying values;
their descriptions, alteration types and datatypes are returned with measurements.
Mutation queries require a mutation profile; numeric queries support expression,
copy number, protein and methylation profiles. Both require explicit sample IDs
and Entrez gene IDs, capped at 100 each and 1,000 sample-gene pairs.

Paged endpoints use zero-based `page` and bounded `limit`. When the API omits a
total, `has_more` is unknown (`null`) and `may_have_more` indicates a full page.
Numeric molecular-data queries have no upstream pagination and are bounded by
the selected sample-gene pairs. Values keep the selected profile's original
scale, including z-scores or discrete copy-number calls. Cohorts and processing
releases are not assumed to match GDC.
[cBioPortal API documentation](https://docs.cbioportal.org/web-api-and-clients/).

These seven integrations query public resources and need no credentials or new
environment variables. Follow each provider's data-use and licensing terms; API
availability does not grant additional rights to source publications or datasets.
See [integration validation notes](docs/new-provider-validation.md) for tested
versions, live checks and limitations.

## Development

Cancer-data API research and further integration options are documented in
[Cancer data API options](docs/cancer-apis.md). GDC/TCGA and cBioPortal public
query servers are implemented; Xena, PDC and ARGO remain proposals.

From the repository root:

```bash
python -m compileall -q servers common
python -m unittest discover -s tests -v
pytest -q
python -m pip check
```

Regression tests use mocked HTTP/SDK responses and need no network or API keys.
Transport tests initialize each new server over stdio, discover tools and check
validation error responses. A local SOMA dataframe test runs when the optional
CELLxGENE dependency is installed and skips otherwise.

Provider implementations are under `servers/`. Keep credentials in environment variables and follow each provider's rate limits, licensing, and copyright terms.
