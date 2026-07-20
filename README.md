![PDIS — Product Development Intelligence Suite](docs/banner.png)

# PDIS — Product Development Intelligence Suite

<p align="center">
  <img alt="Python 3.11" src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=nextdotjs&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white">
</p>
<p align="center">
  <img alt="OpenAI" src="https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=openai&logoColor=white">
  <img alt="PubMed / NCBI E-utilities" src="https://img.shields.io/badge/PubMed-NCBI%20E--utilities-326295?style=flat-square">
  <img alt="ClinicalTrials.gov API v2" src="https://img.shields.io/badge/ClinicalTrials.gov-API%20v2-2A6EBB?style=flat-square">
  <img alt="LibreOffice (headless figure rasterization)" src="https://img.shields.io/badge/LibreOffice-headless-18A303?style=flat-square&logo=libreoffice&logoColor=white">
</p>

PDIS helps teams write and pressure-test product-development documents — Target Product Profiles (TPPs) and Integrated Product Development Plans (IPDPs). You upload a document and it comes back three ways: parsed into citable blocks, graded against a rubric, or tested against external evidence. A chat assistant ("Ask") answers questions about any result.

## Architecture

```
web/ (Next.js)  →  api/ (FastAPI)  →  services/  →  shared/
```

Imports go one direction only: web → api → services → shared, never the reverse. Services reach each other only through their `__init__.py` public contract — not into another service's `stages/` or `models.py`.

`shared/` holds the cross-cutting pieces: the OpenAI client and two controlled vocabularies (`indications.yaml`, `attributes.yaml`).

## Services

| Folder | UI | What it does | Depends on |
|---|---|---|---|
| `chunker` | Chunker | Parse `.docx`/`.pdf` into ordered, citable `ContentBlock`s, retain embedded images, and optionally label sections. | — |
| `reviewer` | Reviewer | Grade a document against its rubric on completeness, adherence, and rigor, then check consistency across sections. | chunker |
| `searcher` | Searcher | Turn neutral intent into source-attributed `Finding`s through registered source adapters and a source-agnostic controller. | adapter-specific |
| `scout` | Scout | Test a document's targets against live evidence — drift, evidence weight, conformity, and precedent. Targets come from a fixed attribute list (TPP) or are extracted from the document (IPDP). | chunker, searcher |
| `assistant` | Ask | Read-only chat grounded in a Scout or Reviewer result; navigates the result and can open the sources it already cites. | openai_client |

Each service has its own README with its file map and public contract.

## Portable results

Reviewer and Scout downloads use a versioned `pdis.result` envelope with three
separate concerns: `analysis`, `source_documents` (parsed, citable blocks), and
artifact metadata (`version` and `result_type`). The original PDF/DOCX binary is
not embedded; extracted DOCX visuals are embedded on their image blocks. Imports remain backward-compatible with legacy result JSON that
stored `blocks` directly on the analysis; legacy files without blocks still
render, but Ask is analysis-only until the document is run again.

## The four inputs

Document tools take four fields, chosen once in the sidebar:

| Field | What it's for |
|---|---|
| `org` | who published the source (e.g. `bmgf`) |
| `source_type` | document type: `itpp` (intervention TPP), `ctpp` (candidate TPP), or `ipdp` (integrated product development plan) |
| `intervention_class` | `vaccine`, `drug`, `diagnostic`, `device` |
| `indication` | disease, e.g. `malaria`, `hiv`, `tb` |

The first three select configs; all four are stamped on every output, and `indication` also scopes Scout's search. You only need them to *run* — the page loads without them, so you can import a saved result anytime. Searcher is query-only and ignores these.

## Configs and vocabularies

Domain content lives in YAML, maintained by hand:

| Surface | Path | Role |
|---|---|---|
| chunker config | `services/chunker/configs/{org}_{source_type}_{intervention}.yaml` | section taxonomy and mapper guidance |
| reviewer config | `services/reviewer/configs/…` | grading rubric + stage bar (`grading_guidance`) |
| scout config | `services/scout/configs/…` | query tuning (languages, priority sources, per-track budgets) + `unit_provider` |
| indications | `shared/indications.yaml` | indication vocabulary per intervention |
| attributes | `shared/attributes.yaml` | TPP attribute vocabulary per intervention (used when `unit_provider: vocabulary`) |

Adding an `(org × source_type × intervention)` is a YAML drop into the matching `configs/` folders. No code changes for ordinary domain additions.

## Repository layout

```
pdis/
  shared/        openai_client.py, indications.yaml, attributes.yaml
  services/      chunker/  reviewer/  searcher/  scout/  assistant/
  api/           main.py, routes/, schemas.py, deps.py, streaming.py
  web/           app/ (routes: /chunker, /reviewer, /searcher, /scout), components/, lib/
```

## Design rules

1. One config per domain change — adding a triple is YAML only.
2. Services are stateless: same input, same output (modulo LLM/web drift). No persistence in the active path.
3. Cross-service calls go through `__init__.py` — never reach into `stages/` or other internals.
4. Code is infrastructure, config is domain content. Prompts live in `stages/*.py`; rubric and query content live in YAML.
5. One provider. All services share `shared/openai_client.py`.

## Running locally

For the closest match to production, keep API credentials in `.env`, put only
ToolUniverse provider credentials in `.env.tooluniverse`, and keep browser-safe
configuration in `web/.env.local`. These files are Git-ignored. Then start all
three isolated services through Docker Compose:

```bash
cp .env.example .env
cp .env.tooluniverse.example .env.tooluniverse
cp web/.env.local.example web/.env.local
# Fill the two server-side files once, then:
docker compose up --build
```

After the first build, `docker compose up` is sufficient. Docker Desktop can
also start and stop the saved `pdis` stack without re-entering credentials.
The API receives `TOOLUNIVERSE_API_TOKEN` from `.env`; Compose injects that same
value into ToolUniverse without duplicating it in another file. Only
`SEMANTIC_SCHOLAR_API_KEY` belongs in `.env.tooluniverse`.

For the faster native development loop, run the backend and frontend as two
processes. Keys are read server-side from `.env`; the browser never sees them.

```bash
# Backend (fast dev loop)
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn api.main:app --reload --port 8000

# Frontend
cd web && npm install && npm run dev   # http://localhost:3000
```

**Backend in Docker** — packages LibreOffice for the uncommon EMF/WMF/SVG figures that require PNG rasterization. Standard raster images need no converter. Native runs everything except those vector conversions unless LibreOffice is installed locally.

```bash
docker build -t pdis-api .
docker run --rm -p 8000:8000 --env-file .env pdis-api
```

### ToolUniverse sources

PDIS connects to ToolUniverse through its authenticated HTTP API rather than
installing the full scientific/agent SDK into the API image. The official
package is pinned in `deploy/tooluniverse/Dockerfile`. To build or start only
that local service while retaining the same environment wiring, use Compose:

```bash
docker compose up --build tooluniverse
```

Registered ToolUniverse-backed lanes are `semantic_scholar`, `ctis`, `isrctn`,
`open_targets`, `chembl`, `uniprot`, and `fda`. Each is a separate PDIS source
with its own label, capabilities, execution policy, normalizer, attribution,
and allowlisted operation; ToolUniverse is never shown as a generic evidence
source. Scout configs opt into those lanes alongside the direct sources. The
controller runs broad literature lanes for every field and invokes specialized
lanes only when the field's closed evidence domain and document-stated entities
match their capabilities. Every non-applicable lane is retained as a traced
skip. `SEMANTIC_SCHOLAR_API_KEY` belongs in the ToolUniverse server environment,
not the browser or PDIS API. The configured CTIS, ISRCTN, Open Targets, ChEMBL,
UniProt, and FDA operations do not require additional credentials.

## Deploying on Render

`render.yaml` defines three independently deployed services:

- `pdis-web`: public Next.js service.
- `pdis-api`: public Docker service.
- `pdis-tooluniverse`: private Docker service reachable only over Render's
  internal network.

Create a Render Blueprint from this repository. Render derives the web/API
addresses, private ToolUniverse host and port, and a shared 256-bit bearer
token automatically. Enter only the provider credentials requested during the
initial Blueprint setup: `OPENAI_API_KEY`, optional `NCBI_API_KEY`, and
`SEMANTIC_SCHOLAR_API_KEY`. They persist in Render and are never committed.
