# Cancer data API options

Reviewed on 2026-10-25. These are integration proposals, not implemented MCP servers.
Only GDC and the public cBioPortal REST endpoint were exercised against live data.

## Recommended order

| Priority | Resource | Interface and coverage | Authentication | Verification |
| --- | --- | --- | --- | --- |
| 1 | TCGA via NCI GDC | REST at `https://api.gdc.cancer.gov`; projects, cases, clinical metadata, files, manifests and data downloads | Public metadata/open files do not require a token. Controlled downloads need authorization and an `X-Auth-Token` header | Live TCGA project search and open TCGA-BRCA expression-file search returned HTTP 200 |
| 2 | cBioPortal | REST at `https://www.cbioportal.org/api`; studies, samples, clinical attributes, molecular profiles and alterations. Also has an official hosted MCP | Public REST worked without credentials; private instances vary. Official hosted MCP currently requires Google OAuth | Public REST study listing returned HTTP 200; hosted MCP not connected |
| 3 | UCSC Xena | Hub-specific APIs and official `xenaPython` client; cohort datasets, samples, phenotype fields and gene-expression slices | Depends on hub; select public hubs for the first implementation | Official client/documentation reviewed; no live matrix query performed |
| 4 | CPTAC through PDC | GraphQL at `https://pdc.cancer.gov/graphql`; proteomic study catalog, study versions and associated metadata/files | GraphQL documented as open access; follow applicable file/data-use terms | Documentation reviewed; live endpoint/schema not tested |
| 5 | ICGC ARGO | Current ARGO platform and documented access workflow | Controlled data requires approved access | Documentation reviewed; verify current schemas before implementing; do not assume legacy ICGC DCC APIs still work |

## TCGA/GDC first implementation

TCGA is a program hosted by GDC rather than a separate API host. Reuse the shared
bounded HTTP helpers, but create a `gdc-mcp` provider instead of routing these calls
through NCBI Entrez.

Suggested tools:

- `gdc_projects`: filter by program, project ID and primary site; return project metadata.
- `gdc_cases`: filter cohorts and retrieve selected clinical/sample attributes with bounded pagination.
- `gdc_files`: filter by project, data category/type, workflow and access level; return UUIDs, names, sizes and checksums.
- `gdc_file`: retrieve metadata for one UUID and preserve case/sample/aliquot relationships.
- `gdc_manifest`: generate a bounded manifest for selected file UUIDs.
- `gdc_download_url`: expose the documented data endpoint for an open-access UUID, without starting a large transfer.

Use `size`/`from` pagination and explicit `fields`; JSON filters use operators such
as `in` and `and`. Preserve file UUIDs, project IDs, submitter barcodes, sample types,
workflow versions, access flags and data release information. A file count is not
a count of distinct patients or samples.

For a first RNA-seq workflow, select Gene Expression Quantification files with
`STAR - Counts` and `access=open`. Preserve counts versus TPM/FPKM column semantics;
do not combine transformed expression values as though they were raw counts.
Patient/sample pairing and reference versions must remain explicit.

If controlled access is added later, read a token from `GDC_TOKEN` in the process
environment and send it only in the required header. No token is needed or stored
for the public queries tested here.

### Live checks

Both requests below used `size=1` and no credentials:

1. `/projects`, filtered by `program.name=TCGA`: 33 projects reported; first result `TCGA-LUAD`.
2. `/files`, filtered by `cases.project.project_id=TCGA-BRCA`,
   `data_type=Gene Expression Quantification`, `access=open`: 1231 matching files
   reported. Example file `ead53b27-6ad9-4b96-b5d4-0d4f06fb2d13`, workflow
   `STAR - Counts`. File contents were not downloaded.

Counts and file availability can change. Raw request URLs and response excerpts
are saved locally in `artifacts/cancer_api_checks.json` and are not committed.

## cBioPortal: existing MCP versus a new wrapper

The official documentation lists a hosted streamable-HTTP MCP endpoint:
`https://mcp.cbioportal.org/db/mcp`. It requires Google sign-in via OAuth. Consider
reusing it if that account flow is acceptable. A public REST wrapper would fit this
repository's independent stdio server model and allow explicit endpoint/field
control. Do not assume cohorts on cBioPortal and GDC are identical processed releases.

## Sources

- [GDC API overview and authentication](https://docs.gdc.cancer.gov/API/Users_Guide/Getting_Started/)
- [GDC filtering, fields and pagination](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/)
- [cBioPortal REST and official MCP](https://docs.cbioportal.org/web-api-and-clients/)
- [Official UCSC Xena Python client](https://github.com/ucscXena/xenaPython)
- [PDC API documentation](https://pdc.cancer.gov/pdc-docs/api-documentation)
- [ICGC ARGO documentation](https://docs.icgc-argo.org/)
