# PDIS — Agent context

Load-bearing facts for working on this codebase. Not a tutorial; read the root `README.md` for that.

## Layered architecture

```
web/ (Next.js + shadcn/ui)  →  api/ (FastAPI)  →  services/  →  data/
                                                  shared/ (cross-cutting)
```

Imports flow one way only: `web → api → services → (shared, data)`. **Never** the reverse. Cross-service imports must go through `__init__.py` public contracts — no reaching into `stages/`, `models.py`, or other internals from another service.

## File roles (location encodes role)

| Role | Shape | Location | Maintained by |
|---|---|---|---|
| Vocabulary | flat `{name, description}` keyed by intervention | `shared/` | humans (domain) |
| Service config | that service's own schema | `services/X/configs/` | humans (domain) |
| Template | mirrors its target's shape | beside what it templates | engineers |
| Code / scaffold | Python | `services/X/*.py`, `shared/*.py` | engineers |

**Rule:** anything in `shared/` is a controlled vocabulary and MUST be vocab-shaped (a flat term list). Service-specific tuning lives in that service's `configs/`. Never put a service-shaped config in `shared/`.

**Human-maintained domain surface:** `shared/*.yaml` (vocabularies) + `services/*/configs/*.yaml` (per-service configs). Everything else is engineer-maintained.

## Four services

| Folder | UI label | What it does | Depends on |
|---|---|---|---|
| `services/chunker/` | Chunker | Parses `.docx`/`.pdf` → `list[ContentBlock]`. Optionally labels sections via LLM mapper. | — |
| `services/reviewer/` | Reviewer | Document → `ReviewResult` graded across completeness and adherence. | chunker |
| `services/searcher/` | Searcher | Query → `list[Finding]`. Web retrieval via OpenAI plus optional literature retrieval via NCBI PubMed/PMC. | shared/openai_client, NCBI |
| `services/monitor/` | Monitor | Files + 4 primitives → drift `Match` records plus evidence assessments over attribute variables from `shared/attributes.yaml`. | chunker, searcher |

## Cross-cutting (`shared/`)

- `shared/openai_client.py` — OpenAI client (gpt-5.5), including `search_web()`. Used by **all services**.
- `shared/indications.yaml` — controlled vocabulary of indications per intervention class. Read by `/api/configs/indications` and stamped on every document-derived output. **Indications are NOT owned by any service config.**
- `shared/attributes.yaml` — controlled vocabulary of TPP attributes per intervention class (e.g. `vaccine.efficacy`, `vaccine.safety`). Read by monitor for its per-variable search loop. **Attributes are NOT owned by any service config** — same principle as indications.

## The 4 primitives (required for every document tool run)

Every document-tool request stamps these 4 fields on every document-derived output. All 4 are required at the UI level (`isHeaderComplete` enforces).

| Field | Role |
|---|---|
| `org` (`bmgf`, `who`) | chunker/reviewer config key · monitor tag |
| `source_type` (`tpp`, `ppc`) | chunker/reviewer config key · monitor tag |
| `intervention_class` (`vaccine`, `drug`, `diagnostic`, `device`) | config key for document tools |
| `indication` (`malaria`, `hiv`, `tb`, …) | tag everywhere · scopes monitor search |

Picker is 4 cascading dropdowns; each shows a per-tool role label ("selects config" / "tags output").

## Configs And Vocabularies

| Service | Filename pattern | Lookup |
|---|---|---|
| chunker | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` raises `LookupError` |
| reviewer | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` returns `None` |
| monitor | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` raises `LookupError` |

Configs declare their own `org`/`source_type`/`intervention_class` as data inside the YAML — the picker reads YAML contents, not filename parts. The vocabulary of valid (org, source_type, intervention) triples emerges from the union of chunker configs.

Monitor configs may also include `priority_sources`, `modalities`, `languages`,
`geographic_emphasis`, and `geographic_queries_per_variable`. These are domain
vocabulary and additive query budgets injected into per-variable query generation.

## Reviewer grading shape

**Two independent LLM calls per section, parallelized.** Each call sees only its dimension's inputs:

- **Completeness**: rubric + draft.
- **Adherence**: rubric + draft.

Section dimensions roll up from variables; document dimensions roll up from sections weighted by `section.weight`. **Rollups are mechanical math, not LLM calls.**

Grade scale: `A`/`B`/`C`/`D`/`F`/`N/A`. Same scale per dimension.

## Naming conventions

- Folders use **action names**: `services/chunker/`, `services/reviewer/`, `services/searcher/`, `services/monitor/`.
- Data units stay as their nouns: `ContentBlock`, `Finding`, `Insight`, `Match`, `EvidenceAssessment`.
- UI labels: **Chunker**, **Reviewer**, **Searcher**, **Monitor** (sidebar nav).
- Web routes: `/chunker`, `/reviewer`, `/searcher`, `/monitor`. (`/` redirects to `/chunker`.)
- API routes: `/api/chunker/run`, `/api/reviewer/run`, `/api/searcher/run`, `/api/monitor/run`.
- Acronyms (BMGF, WHO, TPP, PPC, HIV, TB, RSV, HPV, COVID19) display uppercase via `displayLabel()` in `web/components/header-picker.tsx`.
- The field is `indication` (singular) everywhere — **not** `therapeutic_area` (renamed).

## Hard rules

1. **One config per domain change.** Adding an (org × source_type × intervention) triple is a YAML drop — no code.
2. **Services are stateless.** Same input → same output (modulo LLM drift). No persistence in the active path.
3. **No cross-service internals.** Reach only through `__init__.py`.
4. **Code = infrastructure, config = domain content.** Prompts live in `stages/*.py`. Domain rubric/query content lives in YAML.
5. **No speculative fields or stages.** If a feature isn't wired end-to-end, it doesn't get a placeholder slot. Wait for the actual use case.
6. **Single provider (OpenAI).** All services share `shared/openai_client.py`. Anthropic support was removed; do not add it back without an explicit design discussion.

## API contract

- All routes return `StreamingResponse` of NDJSON. Each line is one of: `{"event":"stage","name":"..."}`, `{"event":"complete","result":...}`, `{"event":"error","detail":"..."}`. Frontend's `streamRequest` in `web/lib/api.ts` consumes them.
- Form fields on every tool route: `file`, `org`, `source_type`, `intervention_class`, `indication`. All required.
- API keys read server-side from `.env` (`OPENAI_API_KEY`; optional `NCBI_API_KEY` for higher PubMed/PMC rate limits). Browser never sees them.

## Common pitfalls (don't repeat)

- Don't pass `provider` / `model` form fields per request. The document tools use fixed OpenAI defaults; swap by editing `shared/openai_client.py`, not by adding form fields.
- Don't use Pydantic models with `str | None` defaults on Python 3.9 without `eval-type-backport`. Already pinned in `api/requirements.txt`.
- Don't run `uvicorn` from the base conda Python; it spawns a worker that won't see venv packages. Use `python -m uvicorn api.main:app --reload --port 8000` so the venv's interpreter handles both.
- For Next.js dev, frontend hits `http://localhost:8000` directly. **Do not** restore the Next.js rewrite proxy — multipart uploads flake through it.
- Block IDs in citations look like `b-0032`. If you see `tmp{hash}/b-0032` in the UI, the doc_id is being derived from the temp filename — make sure routes pass `doc_id` (filename stem) into `run_pipeline`.

## Theme / typography (web)

Warm cream palette (`hsl(40 38% 97%)` background, warm-dark text, muted yellow accent). Defined in `web/app/globals.css`. Font: Inter via `--font-sans` variable, tightened letter-spacing for an agent-surface feel.

## Where things live (file map for quick lookup)

```
shared/openai_client.py          OpenAI client (all services, including web_search)
shared/indications.yaml          indication vocabulary per intervention
shared/attributes.yaml           attribute taxonomy vocabulary per intervention
services/chunker/pipeline.py     run_pipeline (parse + optional label)
services/chunker/stages/         parser_docx, parser_pdf, mapper
services/reviewer/pipeline.py    run_pipeline (parse + label → grade)
services/reviewer/stages/grader.py  2-dimension parallel grader
services/searcher/pipeline.py    run_pipeline (query -> Findings)
services/searcher/stages/searcher.py  OpenAI web-search stage
services/searcher/stages/pubmed.py    NCBI PubMed/PMC literature stage
services/searcher/models.py      Finding dataclass + protocol
services/monitor/pipeline.py     run_pipeline (files + primitives -> MonitorResult)
services/monitor/stages/query_extractor.py    LLM: attribute variables -> search queries
services/monitor/stages/insight_extractor.py  LLM: findings -> Insights
services/monitor/stages/drift_classifier.py   LLM: insights x doc -> relations
services/monitor/stages/evidence_assessor.py  LLM: variable evidence -> strength
services/monitor/models.py       Insight + Match + EvidenceAssessment dataclasses + config
api/main.py                      FastAPI app + route registration
api/routes/{chunker,reviewer,configs}.py
api/routes/searcher.py           POST /api/searcher/run (query -> Findings)
api/routes/monitor.py            POST /api/monitor/run (files + primitives -> MonitorResult)
api/schemas.py                   Pydantic wire models (ReviewerRunResponse, MonitorRunResponse, ...)
api/streaming.py                 NDJSON streaming helper (background thread + queue)
web/lib/api.ts                   typed API client (runChunker, runReviewer, runSearcher, runMonitor)
web/lib/store.ts                 zustand: useHeaderStore + isHeaderComplete
web/lib/session.ts               zustand: per-tool result/busy/stage sessions
web/components/header-picker.tsx 4-primitive cascading picker
web/components/sidebar.tsx       static title (non-clickable) + nav + picker
web/app/{chunker,reviewer}/page.tsx  document-tool views
web/app/searcher/page.tsx        searcher debug UI (no picker)
web/app/monitor/page.tsx         monitor UI (picker + multi-file upload + field grid)
```
