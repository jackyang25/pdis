# Product Development Intelligence Suite (PDIS)

Traceable document intelligence for product-development plans, evidence, and decisions.

![PDIS tools dashboard](./docs/pdis-tools-dashboard.png)

PDIS turns DOCX and PPTX product-development documents into citable
analysis. It supports target product profiles and development plans for
vaccines, drugs, diagnostics, and devices while preserving the source blocks
behind every result.
Screener also accepts text-based PDFs, with the extraction limits described in its
[document contract](services/screener/README.md#one-document-collection).

## Contents

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

Archivist reads a curated corpus of human-reviewed historical profiles without
making model calls.

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

An optional employee-authenticated [MCP interface](api/mcp/README.md) exposes
Searcher to compatible clients. It is disabled until explicitly configured.

### Native development

Native development requires Python 3.11 and Node.js 22, and [uv](https://docs.astral.sh/uv/)
to install from the lockfile. ToolUniverse can remain in Docker while the API and
web application run locally.

Use Python 3.11 to match the deployed image.

```sh
docker compose up -d tooluniverse

uv sync --frozen --all-groups
uv run uvicorn api.main:app --reload --port 8000
```

After changing dependencies in `pyproject.toml`, run `uv lock` and commit the
updated lockfile.

In another terminal:

```sh
cd web
npm ci
npm run dev
```

## Usage

1. Open the workspace and choose a tool.
2. Select the requested product context.
3. Upload the source document or documents.
4. Resolve any Scout review checkpoint.
5. Inspect cited blocks and sources, then download the final result.

[Assistant](services/assistant/README.md) explains results, active Scout reviews,
and cited sources without changing decisions or retrieving new evidence.
Workspace context stays in browser memory; export final results to retain them.

Run errors keep their stage and original detail. Known model-response and temporary
service failures suggest another attempt; size and access failures give different
recovery guidance. Input errors and extraction limitations do not acquire blanket
retry advice. Inspector's optional consistency failure leaves section assessments
intact. Recovery wording does not change validation or automatic retry counts.

![PDIS Assistant workspace](./docs/pdis-assistant.png)

## Tools

| Tool                                      | Responsibility                                                      |
| ----------------------------------------- | ------------------------------------------------------------------- |
| [Inspector](services/inspector/README.md) | Review document content against authored template and applicable guideline-derived rubrics, with separate results and one consistency check. |
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

Document workflows share `org`, `intervention_class`, and `indication`.
Document types select configuration where required; Screener selects its question
bank by organization and stage gate. Configuration details live in each service's
README.

Server credentials belong in `.env`; the browser environment contains only the
API origin. See [.env.example](.env.example) and
[web/.env.local.example](web/.env.local.example) for the supported variables.
Human-owned product rules live under `services/*/configs/` and `shared/`.
Public product documentation lives in `shared/product_knowledge.json`; the web
documentation page and Assistant read that same versioned source.

## Development

Document citations share a [bounded reference transport](docs/structured-references.md)
that preserves canonical IDs when structured-output schemas exceed enum limits.

Preview Scout's numeric-target and evidence review panels without an AI run:
`npm --prefix web run preview:scout`. See the
[preview guide](web/test-support/README.md) for states, containment, and cleanup.

Run the contract and build checks before merging cross-layer changes.

```sh
make check
git diff --check
```

`make check` runs Ruff, backend and web tests, TypeScript checks, and the
production web build, matching CI. See [Makefile](Makefile) for individual targets.
The web scripts use webpack to support shared JSON imports outside `web/`.

Build the images when a Dockerfile or a published `shared/` artifact changes, since
the image build has its own copy rules.

```sh
docker compose build
```

Implementation invariants are documented in [AGENTS.md](AGENTS.md).

## Deployment

PDIS runs on the foundation's Nomad cluster. Acceptance deploys on merge;
production requires promotion of an accepted build.

See [deployment and releases](docs/deployment.md) for infrastructure configuration,
production promotion, and the release checklist.
[web/lib/releases.ts](web/lib/releases.ts) owns the release history shown in the app.

## Contributing

Questions and bug reports are welcome in
[GitHub Issues](https://github.com/jackyang25/pdis/issues). Pull requests should
preserve the contracts in [AGENTS.md](AGENTS.md) and pass the development checks
above.

## License

UNLICENSED.
