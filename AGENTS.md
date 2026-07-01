# PDIS — agent context

Load-bearing facts for working in this codebase. For the overview, read the root `README.md`.

## Layered architecture

```
web/ (Next.js + shadcn/ui)  →  api/ (FastAPI)  →  services/  →  shared/
```

Imports flow one way: web → api → services → shared. Never the reverse. Cross-service calls go through `__init__.py` public contracts only — no reaching into another service's `stages/` or `models.py`.

## What's domain vs engineering

Humans own the domain surface: `shared/*.yaml` (controlled vocabularies) and `services/*/configs/*.yaml` (per-service tuning). Engineers own everything else (Python, prompts, scaffolding).

Anything in `shared/` must be vocabulary-shaped — a flat `{name, description}` list keyed by intervention. Service-specific tuning belongs in that service's `configs/`, never in `shared/`.

## Services

| Folder | UI | What it does | Depends on |
|---|---|---|---|
| `services/chunker/` | Chunker | `.docx`/`.pdf` → `list[ContentBlock]`; optional LLM section labeling, and optional image description (config-gated). | — |
| `services/reviewer/` | Reviewer | Document → `ReviewResult` graded on completeness, adherence, rigor, plus a cross-section consistency pass. | chunker |
| `services/searcher/` | Searcher | Query → `list[Finding]` across three backends: OpenAI web search, NCBI PubMed/PMC, ClinicalTrials.gov. | openai_client, NCBI |
| `services/scout/` | Scout | A document's targets vs live evidence: drift `Match`es, evidence assessments, `ConformityScore`s (quantitative vars), and precedent signals. Units come from a fixed vocabulary or are extracted from the doc (per config). | chunker, searcher |
| `services/assistant/` | Ask | Read-only chat grounded in a result object. Result-agnostic. | openai_client |

## The four primitives

Every document-tool run stamps these on its output. They're required to run (the picker's `isHeaderComplete`), but the page renders without them so you can still import a saved result.

| Field | Role |
|---|---|
| `org` (`bmgf`) | config key · output tag |
| `source_type` (`itpp`, `ctpp`, `ipdp`) | config key · output tag |
| `intervention_class` (`vaccine`, `drug`, `diagnostic`, `device`) | config key |
| `indication` (`malaria`, `hiv`, `tb`, …) | tag everywhere · scopes Scout's search |

`itpp` = intervention TPP (candidate-agnostic, early); `ctpp` = candidate TPP (a specific product); `ipdp` = integrated product development plan (the development plan itself — timelines, risks, decision criteria, functional-domain strategies). The picker is four cascading dropdowns, each labeled with its per-tool role: "selects config", "labels output", or "scopes search".

## Configs and lookup

| Service | Filename | Lookup |
|---|---|---|
| chunker | `{org}_{source_type}_{intervention}.yaml` | `find_config(...)` raises `LookupError` |
| reviewer | same | `find_config(...)` returns `None` |
| scout | same | `find_config(...)` raises `LookupError` |

Each config declares its own `org`/`source_type`/`intervention_class` as data; the document-type list is built from the union of chunker configs (the picker reads YAML contents, not filenames). Reviewer configs carry `grading_guidance` (the stage bar — `itpp` grades leniently on numeric specificity, `ctpp` strictly, `ipdp` to a high-level plan). Scout configs carry `languages`, `priority_sources`, `geographic_emphasis`, per-track budgets (`geographic_`/`counterfactual_`/`precedent_queries_per_variable`), `unit_provider` (`vocabulary` for TPPs, `extract` for IPDP), and `drift_framing` / `precedent_framing` — the per-doc-type interpretive stance for the drift and precedent reasoning (empty = a generic doc-agnostic fallback; TPP configs carry the aspirational-target framing, IPDP the plan-commitment framing). The engine holds no doc-type-specific framing. Chunker configs carry an optional `image_lens`; set it to describe embedded figures (IPDP timelines), omit it to skip images.

## Reviewer grading

Three independent LLM calls per section, run in parallel, each seeing only its own rubric inputs:

- completeness — is every required variable present and filled?
- adherence — does it follow the rubric's structure and format?
- rigor — is the content specific, measurable, and sound (not just present)?

Section grades roll up from variables; document grades roll up from sections weighted by `section.weight`. Rollups are plain math, not LLM calls. Grades are `A`–`F` plus `N/A`. After grading, one whole-document pass (`check_cross_section`) finds contradictions that span multiple sections; those are doc-level findings, not attached to any one section.

## Scout shape

Per unit. Units are `Attribute`s (name + description); where they come from is the config's `unit_provider`: `vocabulary` reads the fixed `shared/attributes.yaml` list (TPPs); `extract` has an LLM pull the document's own checkable claims — milestones, timelines, cost/feasibility assumptions (IPDP). Both yield `list[Attribute]`, so everything below is identical regardless of source. Per unit:

- Query generation runs four additive tracks — general, Global-South, counterfactual (disconfirming), precedent (prior/adjacent attempts). Tracks add queries; they never replace each other. Dedup by text, capped at the summed budget.
- Search runs three lanes concurrently — web, PubMed, ClinicalTrials.gov — each emitting `Finding`s into one pool, deduped by URL. CT.gov searches by structured condition + intervention (not the free-text query) and is cached once per run.
- Findings → insights (LLM, per variable) → four reasoning layers, each answering a distinct question and kept orthogonal:
  - drift `Match` (relation to the doc: contradicts/extends/confirms/unrelated),
  - evidence assessment (is the target grounded?),
  - conformity (quantitative: weighted likelihood the numeric target is met; low can mean an ambitious target, not a failure),
  - precedent (established/emerging/novel/disconfirmed/unknown).

## Ask assistant

`services/assistant/` answers questions about a result object, read-only. It's result-agnostic: `navigator.py` walks any result as a JSON tree (`overview`, `get`, `find`, `fetch_source`), and `legends.py` supplies per-result-type meaning. `agent.py` is a small hand-rolled tool-calling loop — no framework. It only fetches URLs already cited in the result (no fresh web search), and it's stateless: the client sends the result plus conversation history each turn. Adding a new result type needs only a legend entry.

## Progress

Parallel fan-out stages report `progress(stage, completed, total)` so the UI shows a live count (Scout's search and per-variable stages; Reviewer's section grading). Single, non-fan-out stages show only a spinner.

## Naming

- Folders are action names: `chunker`, `reviewer`, `searcher`, `scout`, `assistant`.
- Data units keep their nouns: `ContentBlock`, `Finding`, `Insight`, `Match`, `EvidenceAssessment`, `ConformityScore`, `PrecedentSignal`, `CrossSectionFinding`.
- Web routes: `/chunker`, `/reviewer`, `/searcher`, `/scout`. API routes: `/api/{tool}/run`, plus `/api/assistant/ask`.
- `displayLabel()` in `web/components/header-picker.tsx` uppercases acronyms (WHO, TPP, …) and special-cases `iTPP`/`cTPP`.
- The field is `indication` everywhere, not `therapeutic_area`.

## Hard rules

1. One config per domain change. A new triple is a YAML drop, no code.
2. Services are stateless: same input, same output (modulo LLM/web drift).
3. No cross-service internals — reach only through `__init__.py`.
4. Code is infrastructure; config is domain content. Prompts in `stages/*.py`, rubric/query content in YAML.
5. No speculative fields or stages. If it isn't wired end to end, it doesn't get a placeholder.
6. One provider (OpenAI), via `shared/openai_client.py`. Don't add another without a design discussion.

## API contract

- Tool routes stream NDJSON. Each line is `{"event":"stage",...}` (optionally with `completed`/`total`), `{"event":"complete","result":...}`, or `{"event":"error","detail":...}`. `streamRequest` in `web/lib/api.ts` consumes them. `/api/assistant/ask` is a plain JSON POST (result + messages → answer).
- Tool form fields: `file(s)`, `org`, `source_type`, `intervention_class`, `indication`.
- Keys are read server-side from `.env` (`OPENAI_API_KEY`; optional `NCBI_API_KEY`). The browser never sees them.

## Pitfalls (learned the hard way)

- Don't pass `provider`/`model` per request. The tools use fixed OpenAI defaults; change them in `shared/openai_client.py`.
- Python 3.9 + Pydantic with `str | None` defaults needs `eval-type-backport` (pinned in `api/requirements.txt`).
- Run uvicorn as `python -m uvicorn api.main:app --reload --port 8000` so the venv interpreter is used (a bare `uvicorn` can spawn a worker that misses venv packages).
- Frontend hits `http://localhost:8000` directly. Don't restore the Next.js rewrite proxy — multipart uploads flake through it.
- Block IDs look like `b-0032`. A `tmp{hash}/b-0032` in the UI means the route didn't pass `doc_id` (the filename stem) into `run_pipeline`.

## File map

```
shared/openai_client.py             OpenAI client (text, web_search, tool-calling chat, vision describe_image)
shared/{indications,attributes}.yaml  controlled vocabularies per intervention
services/chunker/stages/            parser_docx, parser_pdf, mapper, image_describer
services/reviewer/stages/grader.py  3-dimension parallel grader + cross-section pass
services/searcher/stages/           searcher (web), pubmed, clinicaltrials
services/scout/stages/              query_extractor, unit_extractor, insight_extractor,
                                    drift_classifier, evidence_assessor, conformity,
                                    precedent_classifier
services/assistant/                 navigator, legends, agent (Ask)
api/main.py                         FastAPI app + route registration
api/routes/                         chunker, reviewer, searcher, scout, assistant, configs
api/{schemas,streaming,deps}.py     wire models · NDJSON streaming · client factory
web/lib/{api,store,session}.ts      typed client · header store · per-tool sessions
web/components/                     header-picker, sidebar, run-panel, assistant/ask, ...
web/app/{chunker,reviewer,searcher,scout}/page.tsx
```
