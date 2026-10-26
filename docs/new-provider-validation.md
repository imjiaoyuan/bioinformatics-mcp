# Seven additional provider integrations

Validated on 2026-10-26. The repository now exposes 20 independent stdio servers;
these seven additions provide 40 tools. No credentials or new environment
variables are required for their public queries.

## Installation and compatibility

The base package uses Python 3.10+ and installs all command entry points. The six
HTTP integrations were exercised in the existing Python 3.14 environment.
CELLxGENE is an optional extra and was exercised in an isolated Python 3.12.15
environment with `cellxgene-census==1.18.0` and `tiledbsoma==1.17.1`.
The extra constrains TileDB-SOMA to the tested major version (`>=1.15.3,<2`).
The Python 3.14 attempt did not find a native wheel and its source build failed;
Python 3.12 is the documented installation path for this extra.

From the repository root, with Python 3.12 already installed:

```bash
python3.12 -m venv .venv-cellxgene
source .venv-cellxgene/bin/activate
python -m pip install -e '.[cellxgene]'
```

An additional environment manager is not required. Configure CELLxGENE's command
to use the environment containing its optional SDK. The base environment's
`cellxgene-mcp` command can initialize and list tools without that SDK; valid data
queries explain how to install the extra if it is missing.

## Automated validation

The regression suite covers every new tool's input validation and successful
response handling, provider errors, pagination, GraphQL partial/error results,
sample/gene selection bounds, measurement semantics and version metadata.
Tests use mocked HTTP/SDK responses and do not require network access or API keys.
A tiny local SOMA dataframe test exercises the actual SDK iterator and filtering;
it skips when the optional dependency is absent. Stdio tests initialize each of
the seven servers, discover its expected tools and invoke validation failures
through the MCP transport.

Validation commands:

```bash
python -m compileall -q servers common tests
python -m unittest discover -s tests -v
python -m pytest -q
python -m pip check
```

Python 3.12 passed all 81 tests, including the local SOMA test. The base Python
3.14 environment passed the suite with the optional SOMA test skipped. Dependency
checks passed in both environments. All 20 console scripts were registered and
present after editable installation. In this execution environment, thread-pool
shutdown hung inside the restricted sandbox; tests completed normally outside it.

## Public API smoke checks

Small public queries were made for the following workflows. No complete data
files were downloaded. These checks describe observed availability on the date
above; automated tests do not rely on these live records or counts.

| Provider | Checks |
| --- | --- |
| GDC | TCGA project listing; TCGA-BRCA case/file discovery; file details; TSV manifest; open-access download URL. Nested demographic, diagnosis and sample data were verified using `expand`, with no field warnings. |
| Reactome | Search for p53; entry, contained events and participants for `R-HSA-69563`; UniProt `P04637` pathway mapping. |
| CELLxGENE | Version directory; dataset/cell/gene metadata windows; raw 1-cell × 1-gene expression; source H5AD locator. `stable` resolved to `2025-11-08`; expression axes and missing-ID lists were checked. |
| ChEMBL | Aspirin search; `CHEMBL25` compound, activities and mechanisms; `CHEMBL204` target; assay referenced by a returned activity. |
| GWAS | Asthma trait/study queries; GCST study details; `rs334` variant and association queries using REST v2. |
| Open Targets | TP53 search and `ENSG00000141510` target; `EFO_0000311` disease; association ranking in both directions; `CHEMBL25` drug; evidence page for the target/disease pair. All GraphQL query templates returned without schema errors. |
| cBioPortal | Study search; `brca_tcga` samples, clinical data and profiles; mutations and TP53 expression for one explicitly selected sample, retaining profile metadata. |

Some initial requests timed out; subsequent bounded queries succeeded. Raw local
smoke outputs were kept outside the repository and are not regression fixtures.

## Interpretation and limits

- HTTP integrations reuse the common request transport, with bounded response
  bodies, rate limiting and transient-error retry for idempotent requests.
- Reactome list endpoints without pagination use explicit local slicing after a
  byte-bounded response. Narrow the query if the upstream response exceeds the cap.
- CELLxGENE metadata scans inspect bounded coordinate windows, not the entire
  Census. Follow the returned cursor and `has_more` flag with a fixed release.
  Expression queries require explicit cells and genes, capped at 100 × 100.
- GDC file counts are not patient counts. Controlled-access downloads and token
  handling are not implemented. Manifests preserve file state and report missing IDs.
- GWAS retrieves curated top associations and study links; it does not implement
  a full summary-statistics query API.
- ChEMBL activity units/operators and cBioPortal profile scales remain unchanged.
  Cross-study values, cohorts and processed releases are not automatically merged.
- The Open Targets wrapper uses fixed GraphQL templates and explicitly returns
  partial/error status. It does not expose arbitrary GraphQL execution.
- Public API access does not replace each dataset's licensing, citation and use
  conditions. No new authentication credentials are stored by these integrations.

## Official references

- [GDC API](https://docs.gdc.cancer.gov/API/Users_Guide/Getting_Started/)
- [Reactome Content Service](https://reactome.org/dev/content-service)
- [CELLxGENE Census Python API](https://chanzuckerberg.github.io/cellxgene-census/python-api.html)
- [ChEMBL web services](https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services)
- [GWAS Catalog REST v2](https://www.ebi.ac.uk/gwas/docs/programmatic-access/rest-api/)
- [Open Targets GraphQL](https://platform-docs.opentargets.org/data-access/graphql-api)
- [cBioPortal API](https://docs.cbioportal.org/web-api-and-clients/)
