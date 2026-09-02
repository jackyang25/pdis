# Product Development Intelligence Suite (PDIS) for Health Interventions

Traceable document intelligence for product-development plans, evidence, and decisions.

![PDIS tools dashboard](./docs/pdis-tools-dashboard.png)

PDIS turns DOCX and PPTX product-development documents into citable
analysis. It supports target product profiles and development plans for
vaccines, drugs, diagnostics, and devices while preserving the source blocks
behind every result.

## Table of Contents

- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Tools](#tools)
- [Configuration](#configuration)
- [Development](#development)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)



## Background

Product-development work spans several distinct questions: whether a document
is complete, whether two documents agree, and whether stated targets are
supported by external evidence. PDIS keeps those responsibilities separate
instead of collapsing them into one score.

The system is stateless. Inspector, Aligner, Screener, and Scout produce portable,
versioned result files containing their parsed source blocks and retained
visuals. Imported final results are read-only and Assistant never performs a new
search.

Archivist is the one tool that reads a stored artifact rather than the document in
front of you, and it is stored for a reason: every row is a model's reading of a past
document, verified against a quote and then reviewed by a person before anyone relies
on it. Reading it involves no model call.

## Install

Docker Desktop is the recommended local environment.

```sh
make dev
docker compose up --build
```

`make dev` copies the three example environment files and installs
dependencies; `make help` lists every target.

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and a shared
`TOOLUNIVERSE_API_TOKEN` in `.env`. Set `SEMANTIC_SCHOLAR_API_KEY` in
`.env.tooluniverse` when that source is enabled.

Open the application at [http://localhost:3000](http://localhost:3000). The API health endpoint and
OpenAPI reference are available at [http://localhost:8000/api/health](http://localhost:8000/api/health) and
[http://localhost:8000/api/docs](http://localhost:8000/api/docs).

Every backend route lives under `/api`, including the OpenAPI documents. That is
what lets one hostname serve both the client and the gateway in a deployment,
and it makes browser calls same-origin.

### Dependencies

Native development requires Python 3.11 and Node.js 20, and [uv](https://docs.astral.sh/uv/)
to install from the lockfile. ToolUniverse can remain in Docker while the API and
web application run locally.

Python is pinned to 3.11 in `pyproject.toml` because that is what the image
ships. An older interpreter will run the suite, and will run it against
semantics the deployed image does not have.

```sh
docker compose up -d tooluniverse

uv sync --frozen --all-groups
uv run uvicorn api.main:app --reload --port 8000
```

`uv.lock` is committed and `--frozen` refuses to resolve around it, so two
installs of one commit produce the same dependency set. After changing a
dependency in `pyproject.toml`, run `uv lock` and commit the result.

In another terminal:

```sh
cd web
npm install
npm run dev
```



## Usage

1. Open the workspace and choose a tool.
2. Select the requested product context.
3. Upload the source document or documents.
4. Resolve any Scout review checkpoint.
5. Inspect cited blocks and sources, then download the final result.

Assistant can navigate canonical PDIS process and architecture documentation,
the tool catalog, current client-held analyses and utility outputs, their
embedded source blocks, retained visuals, and already-cited URLs. Users may
also attach transient documents or images as conversation context. Assistant
cannot mutate results or retrieve new evidence. Conversation text, loaded
results, and attachments share one in-memory workspace lifecycle; final-result
export/import is the durable boundary.

![PDIS Assistant workspace](./docs/pdis-assistant.png)

## Tools


| Tool                                      | Responsibility                                                      |
| ----------------------------------------- | ------------------------------------------------------------------- |
| [Inspector](services/inspector/README.md) | Grade document completeness, adherence, rigor, and consistency.     |
| [Aligner](services/aligner/README.md)     | Check one document against another's requirements, one requirement at a time. |
| [Scout](services/scout/README.md)         | Test document targets against evidence, comparators, and precedent. |
| [Screener](services/screener/README.md)       | Decide which stage-gate questions the supplied documents answer.    |
| [Archivist](services/archivist/README.md) | Report what past profiles required for an attribute, and how many said nothing. |
| [Chunker](services/chunker/README.md)     | Produce ordered, citable text, table, and image blocks.             |
| [Searcher](services/searcher/README.md)   | Execute normalized retrieval across registered evidence sources.    |
| [Assistant](services/assistant/README.md) | Navigate available results and cited material across the workspace. |


External GHIDE decision workflows appear as labeled shortcuts in the workspace;
they are not executed by this repository.

## Configuration

Document workflows use four inputs: `org`, `source_type`,
`intervention_class`, and `indication`. The first three select YAML
configuration; `indication` scopes provenance and Scout retrieval.

Server credentials belong in `.env`; the browser environment contains only the
API origin. See [.env.example](.env.example) and
[web/.env.local.example](web/.env.local.example) for the supported variables.
Human-owned product rules live under `services/*/configs/` and `shared/`.
Public product documentation lives in `shared/product_knowledge.json`; the web
documentation page and Assistant read that same versioned source.

## Development

Run the contract and build checks before merging cross-layer changes.

```sh
make check
git diff --check
```

`make check` runs Ruff, the backend suite, the web tests, the type check, and the
production web build - the same commands, under the same names, that `.drone.yml`
runs in CI. The suite is written against `unittest`, so
`python -m unittest discover -s tests` remains valid.

Build the images when a Dockerfile or a published `shared/` artifact changes, since
the image build has its own copy rules.

```sh
docker compose build
```

Implementation invariants are documented in [AGENTS.md](AGENTS.md).

## Deployment

PDIS deploys to the foundation's Nomad cluster. Three files in this repository
describe it, and a fourth lives in the tenant repository.

| File | Owns |
| --- | --- |
| [.drone.yml](.drone.yml) | Test, build, and push the three images; deploy to acceptance on merge and to production on promote |
| [jobspec.nomad](jobspec.nomad) | The production job: three groups, their resources, and the ingress rules |
| [jobspec_acc.nomad](jobspec_acc.nomad) | The acceptance job, identical but for its hostname |
| `tf_nomad_tenant_configuration/prod/main` | The `module "aws-pdis"` block that creates the namespace and the CI secrets |

The client and the gateway share one hostname. Traefik routes `/api/*` to the
gateway and everything else to the client, which is why the client's bundle
carries no API hostname and why CORS is unset in production. The ToolUniverse
connector carries no routing tag at all: that absence is the only thing keeping
it off the public internet, and `tests/test_jobspec_parity.py` asserts it.

Onboarding is a pull request to `tf_nomad_tenant_configuration/prod/main`:

```hcl
module "aws-pdis" {
  source                   = "../_modules/aws_application"
  namespace                = "pdis"
  repo                     = "pdis"
  zone_id                  = var.zone_id
  cluster_ingress_hostname = var.aws_cluster_ingress_hostname
  docker_password          = var.docker_password
  acceptance_domain        = "pdis-acc.bmgf.io"
  production_domain        = "pdis.bmgf.io"
}
```

Merging it creates the Nomad namespace and the Drone secrets the pipeline
expects: `AWS_NOMAD_TOKEN`, `DOCKER_PASSWORD`, `NAMESPACE`,
`NOMAD_VAR_domain_acc_aws`, and `NOMAD_VAR_domain_prod_aws`. Activate the
repository at [cicd.bmgf.io](https://cicd.bmgf.io) first.

Acceptance deploys automatically on merge to `main`. Production is a manual
promote of a build that already passed acceptance:

```sh
drone build promote gatesfoundation/pdis <build> production
```

Both jobspecs and the pipeline are drafts pending reconciliation with
[nomad-sre-patterns](https://github.com/gatesfoundation/nomad-sre-patterns);
the entries marked `TODO` are cluster facts this repository cannot know.

## Contributing

Questions and bug reports are welcome in
[GitHub Issues](https://github.com/jackyang25/pdis/issues). Pull requests should
preserve the contracts in [AGENTS.md](AGENTS.md) and pass the development checks
above.

## License

UNLICENSED.
