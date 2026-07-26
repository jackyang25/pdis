# Product Development Intelligence Suite (PDIS) for Health Intervention

![PDIS product-development workflow](./docs/banner.png)

PDIS — Product Development Intelligence Suite

Traceable document intelligence for product-development plans, evidence, and decisions.

PDIS turns DOCX, PDF, and PPTX product-development documents into citable
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

The system is stateless. Inspector, Aligner, and Scout produce portable,
versioned result files containing their parsed source blocks and retained
visuals. Imported final results are read-only and Ask never performs a new
search.

## Install

Docker Desktop is the recommended local environment.

```sh
cp .env.example .env
cp .env.tooluniverse.example .env.tooluniverse
cp web/.env.local.example web/.env.local
docker compose up --build
```

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, and a shared
`TOOLUNIVERSE_API_TOKEN` in `.env`. Set `SEMANTIC_SCHOLAR_API_KEY` in
`.env.tooluniverse` when that source is enabled.

Open the application at [http://localhost:3000](http://localhost:3000). The API health endpoint and
OpenAPI reference are available at [http://localhost:8000/api/health](http://localhost:8000/api/health) and
[http://localhost:8000/docs](http://localhost:8000/docs).

### Dependencies

Native development requires Python 3.11 and Node.js 20. ToolUniverse can remain
in Docker while the API and web application run locally.

```sh
docker compose up -d tooluniverse

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn api.main:app --reload --port 8000
```

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

Ask can navigate a supplied result, its embedded source blocks, retained
visuals, and already-cited URLs. It cannot mutate the result or retrieve new
evidence.

## Tools


| Tool                                      | Responsibility                                                      |
| ----------------------------------------- | ------------------------------------------------------------------- |
| [Inspector](services/inspector/README.md) | Grade document completeness, adherence, rigor, and consistency.     |
| [Aligner](services/aligner/README.md)     | Trace commitments and changes across two documents.                 |
| [Scout](services/scout/README.md)         | Test document targets against evidence, comparators, and precedent. |
| [Chunker](services/chunker/README.md)     | Produce ordered, citable text, table, and image blocks.             |
| [Searcher](services/searcher/README.md)   | Execute normalized retrieval across registered evidence sources.    |
| [Ask](services/assistant/README.md)       | Answer read-only questions from saved results and cited material.   |


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

## Development

Run the contract and build checks before merging cross-layer changes.

```sh
PYTHONPYCACHEPREFIX=/tmp/pdis-pycache \
  .venv/bin/python -m compileall -q shared services api tests
.venv/bin/python -m unittest discover -s tests
npm --prefix web run typecheck
npm --prefix web run build
git diff --check
```

Implementation invariants are documented in [AGENTS.md](AGENTS.md). The web
application also includes focused test scripts for portable results, Scout
review state, evidence maps, and quantitative displays.

## Deployment

[render.yaml](render.yaml) defines the public Next.js application, public
FastAPI service, and private ToolUniverse service. Create a Render Blueprint
from the repository and provide the prompted secrets in the Render dashboard.

## Contributing

Questions and bug reports are welcome in
[GitHub Issues](https://github.com/jackyang25/pdis/issues). Pull requests should
preserve the contracts in [AGENTS.md](AGENTS.md) and pass the development checks
above.

## License

UNLICENSED.
