# bioinformatics-mcp

Copy the prompt below into your AI agent. 

```text
Use https://github.com/imjiaoyuan/bioinformatics-mcp. Read its README.md and docs/mcp.md; if using a checkout, also read AGENTS.md.
First check whether bioinformatics-mcp is already installed globally. If available, use `bioinformatics-mcp list` and reuse the installed commands without cloning or reinstalling. Otherwise use an existing checkout, or install with uv tool/pipx from the Git URL; use the documented venv installation if needed. List the available MCP servers and their capabilities, and choose the smallest useful set for my task. Generate configuration with `bioinformatics-mcp config <selected providers>` (use `--format toml` for Codex), or merge into an mcpServers JSON file with `bioinformatics-mcp register <selected providers> --config <path>`. Follow docs/mcp.md for other client formats and environment variables, then verify each connection. Ask only when a choice or credential is required. Keep secrets in environment variables.
```

### Global installation and quick registration

For a global installation without a checkout, use uv (or pipx):

```bash
uv tool install git+https://github.com/imjiaoyuan/bioinformatics-mcp.git
# Alternative:
# pipx install git+https://github.com/imjiaoyuan/bioinformatics-mcp.git

bioinformatics-mcp list
bioinformatics-mcp config publications pdb
```

The management command discovers installed server executables and generates
absolute paths; no repository directory or `cwd` is needed. This also works
with system packages (including an AUR package that installs this project's
console scripts); no particular package manager is required.

Register selected servers in a client using an `mcpServers` JSON file, for
example Cursor's global config:

```bash
bioinformatics-mcp register publications pdb --config ~/.cursor/mcp.json
```

Existing settings and unrelated servers are preserved. A differing entry with
the same name requires `--replace`; the first original file is saved as
`mcp.json.bak`. The target must be plain JSON using `mcpServers`, not JSONC,
OpenCode's `mcp` format, or TOML. Configuration does not test the connection;
restart/reload the client and verify its tools. Export required environment
variables before launching the client; no credentials are copied into files.

For Codex, print a TOML fragment and merge it into `~/.codex/config.toml`:

```bash
bioinformatics-mcp config publications ncbi --format toml
```

See [Connecting MCP clients](docs/mcp.md) for client-specific instructions.

### Development installation

Development installation commands must run **from the cloned repository root**, the directory containing `pyproject.toml`:

```bash
git clone https://github.com/imjiaoyuan/bioinformatics-mcp.git
cd bioinformatics-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The install creates a `bioinformatics-mcp` management command and these executable MCP servers:

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
| `sra-mcp` | NCBI SRA run metadata search and study/run lookup |
| `gtex-mcp` | GTEx tissue expression, gene search and eQTLs |
| `hpa-mcp` | Human Protein Atlas tissue, cell, pathology and subcellular annotations |
| `alphafold-mcp` | AlphaFold DB predicted structure metadata, confidence and file URLs |
| `emdb-mcp` | EMDB cryo-EM entries, resolution and map file references |
| `kegg-mcp` | KEGG REST pathway, gene and compound retrieval |
| `panglao-mcp` | PanglaoDB cell-type marker genes |
| `intact-mcp` | IntAct molecular interactions with MI scores and participants |
| `biogrid-mcp` | BioGRID physical and genetic interactions (API key) |
| `depmap-mcp` | DepMap datasets, cell lines, dependencies and compound sensitivity |
| `civic-mcp` | CIViC genes, variants and evidence items |
| `clinvar-mcp` | ClinVar variant clinical significance and RCV records |
| `pharmgkb-mcp` | PharmGKB drugs, genes, variants and clinical annotations |
| `disgenet-mcp` | DisGeNET gene/variant-disease associations (API key) |
| `mondo-mcp` | MONDO disease ontology entries, cross-references and children |
| `hpo-mcp` | HPO phenotype terms, hierarchy and gene/disease links |
| `quickgo-mcp` | QuickGO GO entries, annotations and slimming |
| `singlecell-mcp` | Human Cell Atlas and Single Cell Portal study/sample metadata |
| `vep-mcp` | Ensembl VEP variant consequence annotation (single, batch, region) |
| `ucsc-mcp` | UCSC Genome Browser genomes, tracks and range data |
| `mygene-mcp` | MyGene.info gene query/batch and MyVariants.info annotations |
| `bigg-mcp` | BiGG metabolic models, reactions and metabolites |
| `bgee-mcp` | Bgee gene expression by anatomical entity and species |
| `pdbe-mcp` | PDBe SIFTS mappings and PDBe-KB aggregated entry summaries |
| `msigdb-mcp` | MSigDB gene set details, members and collection catalog |

The base install supplies all 45 commands and works on Python 3.10 through
3.14. `cellxgene-mcp` follows the same baseline: version listings, dataset
search and H5AD URLs are served from public REST APIs with no extra
dependencies. Only the cell-level Census tools (`cellxgene_cells`,
`cellxgene_genes`, `cellxgene_expression`) need the optional SDK, whose native
TileDB-SOMA wheels currently cover Python 3.10-3.13 only. Without the SDK
those three tools return a clear error; everything else keeps working. To
enable them, use a separate 3.10-3.13 environment:

```bash
python3.12 -m venv .venv-cellxgene
source .venv-cellxgene/bin/activate
python -m pip install -e '.[cellxgene]'
```

Any Python 3.10-3.13 works for this extra; 3.12 is one known-good choice.

This uses standard Python, venv and pip. No additional environment manager is required.
Configure CELLxGENE with `.venv-cellxgene/bin/cellxgene-mcp`; other commands can
continue using the original `.venv`.

## Agent configuration

Each provider command is an MCP stdio server. Configure its installed executable;
the repository working directory is optional. For a development install:

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

The servers use only the standard MCP stdio protocol, so any MCP-capable client
works the same way. Exact configuration snippets for Claude Code, Codex, Pi,
OpenCode, DeepSeek Harness (DSH), and the generic `mcpServers` JSON dialect
are in [Connecting MCP clients](docs/mcp.md).

### Environment variables

Servers read configuration directly from their process environment:

| Variable | Used by | Required | Purpose |
| --- | --- | --- | --- |
| `NCBI_EMAIL` | `ncbi-mcp` | Yes | Entrez contact address |
| `NCBI_API_KEY` | `ncbi-mcp` | No | Higher request rates |
| `NCBI_TOOL` | `ncbi-mcp` | No | Entrez tool name (default `ncbi-mcp`) |
| `NCBI_EMAIL` | `publications-mcp` | No | Contact address in the HTTP User-Agent |
| `BIOC_VERSION` | `bioconductor-mcp` | No | Bioconductor release (default `3.21`) |
| `NCBI_EMAIL` | `sra-mcp`, `clinvar-mcp` | Yes | Entrez contact address |
| `NCBI_API_KEY` | `sra-mcp`, `clinvar-mcp` | No | Higher request rates |
| `BIOGRID_API_KEY` | `biogrid-mcp` | Yes | Free key from webservice.thebiogrid.org registration |
| `DISGENET_API_KEY` | `disgenet-mcp` | Yes | Free academic key from DisGeNET registration |

Whatever client you use, ensure these variables reach the server process. Most
MCP clients support an `env` field on the server entry, which is set verbatim in
the child process environment:

```json
{
  "mcpServers": {
    "ncbi": {
      "command": "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp",
      "cwd": "<REPOSITORY_ROOT>",
      "env": {"NCBI_EMAIL": "you@example.org", "NCBI_API_KEY": "..."}
    }
  }
}
```

Alternatively, export the variables before starting the agent; a stdio server
inherits its parent environment. For Codex, forward existing variables with
`env_vars` instead — values such as `"${NCBI_EMAIL}"` in an `env` table are
literal strings, not expansions. Per-client configuration, including how each
client passes these variables and where its config file lives, is documented in
[Connecting MCP clients](docs/mcp.md).

```toml
[mcp_servers.ncbi]
command = "<REPOSITORY_ROOT>/.venv/bin/ncbi-mcp"
cwd = "<REPOSITORY_ROOT>"
env_vars = ["NCBI_EMAIL", "NCBI_API_KEY", "NCBI_TOOL"]
```

Do not store credentials in the repository. `string_interactions.limit` caps
returned edges locally; it does not expand the input protein set.

## Additional provider tools

### GEO (included in ncbi-mcp)

`geo_search` searches GEO with structured biology filters — `organism`
("human", "arabidopsis", any scientific name), `data_type` (wgs, rna_seq,
long_reads, hifi, ont, scrna, snrna, spatial, atac, chip_seq, methylome,
proteomics, epigenomic), and `entry_type` (series/sample/platform).
`geo_record` reads GSE/GSM SOFT metadata (including sample characteristics),
and `geo_files` lists actual matrix and supplement URLs. File contents are not
downloaded. `sra_search` finds raw reads in SRA with exact fields (organism
taxid, library `strategy`, sequencing `platform`, library `source`), and
`sra_files` expands run, experiment, study, or sample accessions into runs
with public HTTPS download URLs, platform/strategy metadata, spot/base
counts, and sizes (no download is started; FASTQ needs the ENA mirror).
`find_data` is the one-call entry point: it searches GEO, SRA, ENA and CNCB
GSA in parallel (selectable via `archives`) and returns sections tagged by
source. Each source can fail independently: successful results are retained,
with `errors`, `partial`, and `all_sources_failed` distinguishing failures
from an empty search. `download_plan` turns a mixed list of GSE/GSM and SRA accessions into
a batch download manifest with known sizes plus ready-to-save aria2c/wget
inputs, and `geo_metadata` harvests sample-level SOFT characteristics
(treatment, tissue, variety) for a list of GSEs and returns rows plus an
Excel-ready CSV. Entrez `gds` and `geoprofiles` are also available through
the generic NCBI
tools. Entrez calls require `NCBI_EMAIL`; `NCBI_API_KEY` remains optional.
[Official GEO access guide](https://www.ncbi.nlm.nih.gov/geo/info/geo_paccess.html).

#### Structured data discovery

Use independent `find_data` filters to express biological requirements separately
from sequencing technology. For example, human liver short- and long-read RNA
data with verified specimen identity:

```json
{
  "organism": "human",
  "assay": "rna_seq",
  "tissue": "liver",
  "read_type": "both",
  "pairing": "same_sample",
  "archives": "ena",
  "limit": 10,
  "metadata_limit": 10
}
```

Poplar genomic HiFi candidates (the `poplar`/`杨树` alias searches the entire
*Populus* genus; use a scientific species name for a narrower search):

```json
{
  "organism": "poplar",
  "assay": "wgs",
  "protocol": "hifi",
  "archives": "ena,gsa",
  "file_format": "bam",
  "limit": 10
}
```

| Filter | Values / meaning |
| --- | --- |
| `assay` | `rna_seq`, `wgs`, `wes`, `scrna`, `snrna`, `spatial`, `atac`, `chip_seq`, `methylome`, `proteomics`, `epigenomic` |
| `tissue`, `condition` | Separate literal terms; sample metadata supplies evidence, while study-title matches alone remain unverified |
| `platforms` | List of `illumina`, `bgiseq`, `dnbseq`, `pacbio`, `ont` |
| `read_type` | `any`, `short`, `long`, `both` |
| `protocol` | `any`, `hifi`, `iso_seq`, `direct_rna`, `direct_cdna`, `pcr_cdna` |
| `sample_scope` | `any`, `bulk`, `single_cell`, `single_nucleus` |
| `sample_type` | `any`, `tissue`, `cell_line`, `organoid` |
| `pairing` | `any`, `same_sample`, `same_donor`; pairs require both short and long reads |
| `file_format` | `any`, `fastq`, `bam`, `cram`, `sra`, `h5`; reports presence, not completeness |
| `include_descendants` | Include descendant taxa in ENA; genus aliases always include descendants |
| `offset` | Page start, 0–100000; follow per-source/per-technology `next_offset` |
| `metadata_limit` | Maximum unique ENA samples enriched from XML per call, 0–20 |

Legacy `data_type` calls remain supported. `long_reads` and `ont` default to
transcriptomic data; use `assay="wgs", read_type="long"` for genomic long reads.
The independent filters reject contradictory combinations before searching.
For `read_type="both"`, the long-read `protocol` applies only to long-read members.

The response retains archive sections and adds `candidates`, `excluded_candidates`,
`candidate_counts`, and `pair_groups`. Each candidate has study/sample/run identifiers,
observed metadata, file URLs/formats/roles/sizes/checksums where available, and a
`criteria` map. Each criterion reports `match`, `unknown`, or `mismatch`, a reason,
and source-linked evidence. Contradictory records appear in `excluded_candidates`;
records missing evidence stay in `candidates` with explicit `uncertainties`. These
are metadata assessments, not measurements of read quality or experimental suitability.

Tissue matching uses a small, explicit anatomical vocabulary and parent relationships:
for example `brain` includes cerebral cortex, hippocampus and cerebellum, while a
request for cerebral cortex is not established by a broad `brain` annotation. Search
queries expand the supported descendant names too. Structured tissue and disease/
health attributes take precedence over sample prose. Comparison text such as "tumor
sample compared with healthy controls" does not establish a healthy specimen.
Conflicting annotations and unmapped anatomy remain `unknown`; this is not a complete
anatomical ontology or a general natural-language classifier.

ENA provides the most detailed assessment, including original submitted files as
well as generated FASTQs. PacBio platform alone and CCS naming alone do not prove
HiFi quality. File roles are filename hints, not inspected read contents. If metadata
explicitly reports HiFi but ENA file names say `subreads`, the protocol evidence is
retained and `read_representation` remains unknown until read headers/quality are
checked. An unannotated subreads file alone cannot establish HiFi.
RNA searches retain `OTHER`/`AMPLICON` strategies for protocol inspection and exclude
known miRNA/ncRNA strategies from bulk/full-length RNA candidates.

GEO/SRA summaries and GSA keyword hits may lack specimen/protocol/file evidence;
they remain unverified rather than inheriting the user's requested conditions.
GSA experiment/run/file expansion and ENCODE integration are not implemented here.
ENA-only searches do not require `NCBI_EMAIL`. If NCBI credentials are absent,
default multi-archive calls report GEO/SRA errors while continuing ENA/GSA.

Pairing uses an explicit sample/BioSample accession or a donor identifier from
sample XML. Donor identifiers are scoped to their study to avoid collisions.
Sharing an organism, tissue, project or sample title is insufficient. A pair's
`identity_verified` confirms its identifier relationship; `status` still reflects
any unknown biological/technical criteria. Missing pairs mean none were confirmed
in this result window, not that none exist in the archive.

`limit` caps each archive query (1–100). ENA `read_type="both"` searches separate
short/long windows, each capped at `limit`, so it can return up to `2 × limit` runs.
Counts are labelled as returned runs or archive records, never biological samples.
Truncation, enrichment limits and unavailable metadata are reported. Pagination is
bounded and searches are not exhaustive; files are not downloaded or checksum-verified.
The download planner also supports GEO-only and SRA-only inputs, deduplicates URLs,
and reports source errors, unknown sizes and possible truncation.
GEO sample metadata is parsed by SOFT sample boundaries, preserving repeated and
missing fields per sample. CNCB/GSA business failures and malformed payloads raise
explicit errors rather than masquerading as zero hits.

The queries and fields follow the official [ENA advanced-search API](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/advanced-search.html)
and [taxonomy API](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/taxon-api.html).

### Related publications

`publication_related(doi, limit)` resolves OpenAlex work IDs using the `/works/{id}`
endpoint. It returns an object with `articles`, `errors`, `partial`,
`all_requests_failed`, `total_related` and `truncated`, plus the source URL.
This replaces its previous bare article list: callers should read `articles`.
Individual retrieval failures retain successful articles and report the failed
IDs; an empty related-work list is distinguished from failure of every request.
An initial DOI lookup failure is an explicit tool error. Public queries use the
shared bounded transport with rate limiting and transient-error retry.

### ENA

ENA tools: `ena_search`, `ena_record`, `ena_fastq`, `ena_fields`. Search uses
ENA Portal syntax and supports bounded pagination. FASTQ results include public
HTTPS URLs, MD5 checksums and file sizes; no downloads are started. No credentials
are required for public records. [ENA API guide](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access.html).

### UniProt

UniProt tools: `uniprot_search`, `uniprot_entry`, `uniprot_sequence`,
`uniprot_function`, `uniprot_mapping_submit`, `uniprot_mapping_status`, `uniprot_mapping_results`.
For a question such as "What does Arabidopsis MYB52 do?", call
`uniprot_function(gene="MYB52", taxon_id=3702)`. It performs exact gene/alias
search, retrieves full entries, and returns function annotations together with
CAUTION/sequence warnings, phenotypes, localization, GO annotations, features,
evidence codes and supporting PubMed/DOI references. For this example the
reviewed entry is `Q6R0C4` (`MYB52_ARATH`, locus `At1g17950`); the contradictory
positive/negative secondary-cell-wall phenotypes remain visible in `cautions`.
Original annotation text and evidence are retained; an agent can summarize them
in the user's language without treating predicted annotations as experiments.

Provide the organism's NCBI `taxon_id` to disambiguate gene symbols. If the species
is omitted or several entries match, `selection_required` is true and no entry
is selected automatically. The default `reviewed_only=True` searches Swiss-Prot;
set it to false to include unreviewed TrEMBL candidates. Up to five full entries
are fetched, with explicit partial failures and pagination/truncation metadata.
Missing FUNCTION annotations stay missing. Features, GO annotations and citations
are each capped at 100 with separate truncation flags. Existing `uniprot_entry`
still returns the full record for a known accession.

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

### SRA and ClinVar (NCBI E-utilities)

`sra-mcp` searches NCBI SRA run metadata and resolves studies and runs through
Entrez `esearch`/`esummary` (database `sra`); it overlaps deliberately with the
generic NCBI tools and the ENA server, which remain the preferred route for
FASTQ-level metadata. `clinvar-mcp` searches variant clinical significance and
resolves RCV records through E-utilities (database `clinvar`). Both require
`NCBI_EMAIL`; `NCBI_API_KEY` stays optional.
Both servers translate `limit`/`offset` into Entrez `retmax`/`retstart` and report
upstream experiment/variant paging. SRA study grouping covers only the experiment
page returned; `total_kind="studies_in_this_page"` makes that distinction explicit.
SRA experiment XML can contain sibling elements as well as a single Summary node.

The shared HTTP transport removes API-key, access-key, token and contact-email
query parameters from returned request URLs, HTTP errors and HTTP client logs,
while still sending the original parameters to the provider. SRA/ClinVar JSON
and XML source links, and shared BioGRID response links, use the same redaction.

### GTEx, HPA, AlphaFold DB, EMDB and KEGG

`gtex-mcp` queries tissue lists, median and tissue-specific gene expression and
eQTLs. `hpa-mcp` retrieves tissue, cell-type, pathology and subcellular
annotations; respect Human Protein Atlas copyright terms when republishing.
`alphafold-mcp` returns prediction metadata, confidence and model file URLs
without downloading structures. `emdb-mcp` reads cryo-EM entries, resolution
and map file references. `kegg-mcp` uses the public KEGG REST endpoints
(list/find/get/link/conv); selecting KEGG does not grant rights to its data.

### Interactions, clinical and associations

`intact-mcp` queries IntAct interactions with MI scores and participants.
`biogrid-mcp` requires `BIOGRID_API_KEY` (free registration); the key is read
from the environment and never stored. `civic-mcp` and `clinvar-mcp` cover
variant-to-evidence and variant-to-significance navigation;
`pharmgkb-mcp` covers drug-gene-variant annotations; `disgenet-mcp` requires
`DISGENET_API_KEY` (free academic registration) for gene/variant-disease
associations. Association scores are evidence weights, not effect sizes.

### Ontologies, GO and expression

`mondo-mcp` reads the official MONDO release for entries, cross-references and
children. `hpo-mcp` navigates HPO terms, hierarchy and gene/disease links.
`quickgo-mcp` retrieves GO entries, annotations and slimmed sets; enrichment
analysis remains in `gprofiler-mcp`. `bgee-mcp` queries gene expression per
anatomical entity across species. `panglao-mcp` serves cell-type marker genes
from the PanglaoDB snapshot (2020-03-27) and does not reflect later updates.

### Structure and model resources

`pdbe-mcp` exposes PDBe SIFTS UniProt/ENA mappings, PDBe-KB aggregated summaries
and ligand or modified-residue information for PDB entries; `pdb-mcp` remains
the route for entry and file metadata. `vep-mcp` annotates variant consequences
through the Ensembl VEP REST endpoints (single, batch and region calls).
`ucsc-mcp` lists genomes, tracks and chromosomes and fetches range data.
`mygene-mcp` covers MyGene.info query/batch annotation and MyVariants.info
variant annotation. `bigg-mcp` retrieves BiGG genome-scale models, reactions
and metabolites. `singlecell-mcp` searches Human Cell Atlas (Azul) and Broad
Single Cell Portal study, sample and file metadata; no data download starts.
`msigdb-mcp` reads public MSigDB gene set detail and members per species;
upstream keyword search and collection browsing require a login, so collections
are served from a curated static catalog and no fake search tool is provided.

Sources deliberately not integrated: the eQTL Catalogue REST API is deprecated
(HTTP 410; FTP/tabix downloads only, outside this project's no-download scope)
and the GWAS Atlas host is unreachable, so `eqtl-mcp` was dropped; GWAS trait
metadata remains available through `gwas-mcp`. DrugBank, OMIM, MetaCyc, VMH and
CellMarker have no stable free API or restrict redistribution by license.

## Development

Cancer-data API research and further integration options are documented in
[Cancer data API options](docs/cancer-apis.md). GDC/TCGA and cBioPortal public
query servers are implemented; Xena, PDC and ARGO remain proposals.

From the repository root:

```bash
python -m pip install -e '.[dev]'
python -m compileall -q servers common tests scripts
python -m unittest discover -s tests -v
python -m pytest -q
python -m pip check
```

Regression tests use mocked HTTP/SDK responses and need no network or API keys.
Transport tests start all 45 installed console scripts from temporary working
directories, initialize stdio connections, discover tools and check validation
responses without contacting providers. Local-only PDB/CNCB tools also exercise
successful responses. The registered command list and tool counts are asserted
in `tests/test_mcp_transport.py`; update it when adding a server or tool.
A local SOMA dataframe test runs when the optional CELLxGENE dependency is
installed and skips otherwise. To run that test, install `'.[dev,cellxgene]'`
in any Python 3.10-3.13 environment.

### Continuous integration

[CI](.github/workflows/ci.yml) runs on pushes, pull requests and manual dispatch:

- Base installation, dependency consistency, compilation, regression and stdio
  tests on Python 3.10, 3.11, 3.12, 3.13 and 3.14.
- A separate Python 3.12 job installs the CELLxGENE extra from a native
  TileDB-SOMA wheel, verifies imports and runs the full suite including local SOMA.
- A Python 3.12 packaging job builds an sdist and a wheel from that sdist, checks
  metadata with Twine, then installs each artifact into its own clean venv and
  exercises all 45 installed MCP commands outside the source checkout.

Run the packaging checks locally with:

```bash
python -m build
python -m twine check --strict dist/*
python scripts/check_distribution.py dist
```

Use a distribution directory containing exactly one wheel and one source archive.
Dependency installation requires network access; the tests do not call live
bioinformatics APIs and need no credentials. CI uses standard Python, venv and pip.

Provider implementations are under `servers/`. Keep credentials in environment variables and follow each provider's rate limits, licensing, and copyright terms.
