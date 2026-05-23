# PDIS — Agent context

Load-bearing facts for working on this codebase. Not a tutorial; read the root `README.md` for that.

## Layered architecture

```
web/ (Next.js + shadcn/ui)  →  api/ (FastAPI)  →  services/  →  data/
                                                  shared/ (cross-cutting)
```

Imports flow one way only: `web → api → services → (shared, data)`. **Never** the reverse. Cross-service imports must go through `__init__.py` public contracts — no reaching into `stages/`, `models.py`, or other internals from another service.

## Five services

| Folder | UI label | What it does | Depends on |
|---|---|---|---|
| `services/chunker/` | Chunker | Parses `.docx`/`.pdf` → `list[ContentBlock]`. Optionally labels sections via LLM mapper. | — |
| `services/benchmarker/` | Benchmarker | Document → `list[Claim]`. Builds the peer corpus stored under `data/claims/`. | chunker |
| `services/reviewer/` | Reviewer | Document → `ReviewResult` graded across 3 dimensions. | chunker, benchmarker (`FileClaimsStore`) |
| `services/searcher/` | Searcher | Query → `list[Finding]`. LLM-driven web search via OpenAI. | shared/openai_client |
| `services/monitor/` | Monitor | Files + 4 primitives → `list[Insight]`. Reuses chunker + searcher. | chunker, searcher |

## Cross-cutting (`shared/`)

- `shared/openai_client.py` — OpenAI client (gpt-5.5), including `search_web()`. Used by **all services**.
- `shared/indications.yaml` — controlled vocabulary of indications per intervention class. Read by `/api/configs/indications` and stamped on every document-derived output. **Indications are NOT owned by any service config.**

## The 4 primitives (required for every document tool run)

Every document-tool request stamps these 4 fields on every document-derived output. All 4 are required at the UI level (`isHeaderComplete` enforces).

| Field | Role |
|---|---|
| `org` (`bmgf`, `who`) | chunker/reviewer config key · benchmarker tag |
| `source_type` (`tpp`, `ppc`) | chunker/reviewer config key · benchmarker tag |
| `intervention_class` (`vaccine`, `drug`, `diagnostic`, `device`) | config key for all three |
| `indication` (`malaria`, `hiv`, `tb`, …) | tag everywhere · scopes peer claims in reviewer |

Picker is 4 cascading dropdowns; each shows a per-tool role label ("selects config" / "tags output" / "scopes peer claims").

## Configs (the only human-edit surface)

| Service | Filename pattern | Lookup |
|---|---|---|
| chunker | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` raises `LookupError` |
| benchmarker | `{intervention}.yaml` | `find_config(intervention)` raises `LookupError` |
| reviewer | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` returns `None` |
| monitor | `{org}_{source_type}_{intervention}.yaml` | `find_config(org, source_type, intervention)` raises `LookupError` |

Configs declare their own `org`/`source_type`/`intervention_class` as data inside the YAML — the picker reads YAML contents, not filename parts. The vocabulary of valid (org, source_type, intervention) triples emerges from the union of chunker configs.

## Reviewer grading shape (option B — fully implemented)

**Three independent LLM calls per section, parallelized.** Each call sees only its dimension's inputs:

- **Completeness**: rubric + draft. **No peer claims.**
- **Adherence**: rubric + draft. **No peer claims.**
- **Expertise**: rubric + draft + peer claims (the only dimension that sees them).

Peer claims are routed per variable via `attribute_ref` and filtered by `indication`. Section dimensions roll up from variables; document dimensions roll up from sections weighted by `section.weight`. **Rollups are mechanical math, not LLM calls.**

Grade scale: `A`/`B`/`C`/`D`/`F`/`N/A`. Same scale per dimension.

## Claim schema — primitives only

`Claim` carries only facts and constrained enums. **Do not reintroduce** these previously-removed fields:
- `evidence_strength` (LLM judgment without methodology)
- `binding_confidence` (same)
- `recency_tier` (lossy derivation of dates)
- `label_confidence` (on ContentBlock — same)
- `review_status`, `version`, `superseded_by`, `notes` (speculative — for unbuilt curation/supersession workflows)

The `services/benchmarker/stages/appraiser.py` stage is **deleted** — don't recreate it. Recency reasoning uses raw `extracted_at` / `valid_as_of` dates in the prompt; bucketing is the consumer's job.

## Naming conventions

- Folders use **action names**: `services/chunker/`, `services/benchmarker/`, `services/reviewer/`, `services/searcher/`, `services/monitor/`.
- Data units stay as their nouns: `Claim`, `ClaimsStore`, `data/claims/`, `ContentBlock`, `Finding`, `Insight`.
- UI labels: **Chunker**, **Benchmarker**, **Reviewer**, **Searcher**, **Monitor** (sidebar nav).
- Web routes: `/chunker`, `/benchmarker`, `/reviewer`, `/searcher`, `/monitor`. (`/` redirects to `/chunker`.)
- API routes: `/api/chunker/run`, `/api/benchmarker/run`, `/api/reviewer/run`, `/api/searcher/run`, `/api/monitor/run`.
- Acronyms (BMGF, WHO, TPP, PPC, HIV, TB, RSV, HPV, COVID19) display uppercase via `displayLabel()` in `web/components/header-picker.tsx`.
- The field is `indication` (singular) everywhere — **not** `therapeutic_area` (renamed).

## Hard rules

1. **One config per domain change.** Adding an (org × source_type × intervention) triple is a YAML drop — no code.
2. **Services are stateless.** Same input → same output (modulo LLM drift). No persistence in the active path.
3. **No cross-service internals.** Reach only through `__init__.py`.
4. **Code = infrastructure, config = domain content.** Prompts live in `stages/*.py` (versioned via `prompt_hash` on claims). Domain rubric content lives in YAML.
5. **No speculative fields or stages.** If a feature isn't wired end-to-end, it doesn't get a placeholder slot. Wait for the actual use case.
6. **Single provider (OpenAI).** All services share `shared/openai_client.py`. Anthropic support was removed; do not add it back without an explicit design discussion.

## API contract

- All routes return `StreamingResponse` of NDJSON. Each line is one of: `{"event":"stage","name":"..."}`, `{"event":"complete","result":...}`, `{"event":"error","detail":"..."}`. Frontend's `streamRequest` in `web/lib/api.ts` consumes them.
- Form fields on every tool route: `file`, `org`, `source_type`, `intervention_class`, `indication`. All required.
- API keys read server-side from `.env` (`OPENAI_API_KEY`). Browser never sees them.

## Common pitfalls (don't repeat)

- Don't pass `provider` / `model` form fields per request. The document tools use fixed OpenAI defaults; swap by editing `shared/openai_client.py`, not by adding form fields.
- Don't use Pydantic models with `str | None` defaults on Python 3.9 without `eval-type-backport`. Already pinned in `api/requirements.txt`.
- Don't run `uvicorn` from the base conda Python; it spawns a worker that won't see venv packages. Use `python -m uvicorn api.main:app --reload --port 8000` so the venv's interpreter handles both.
- For Next.js dev, frontend hits `http://localhost:8000` directly. **Do not** restore the Next.js rewrite proxy — multipart uploads flake through it.
- Block IDs in citations look like `b-0032`. If you see `tmp{hash}/b-0032` in the UI, the doc_id is being derived from the temp filename — make sure routes pass `doc_id` (filename stem) into `run_pipeline`.

## Theme / typography (web)

Warm cream palette (`hsl(40 38% 97%)` background, warm-dark text, muted yellow accent). Defined in `web/app/globals.css`. Font: Inter via `--font-sans` variable, tightened letter-spacing for an agent-surface feel.

## What's deferred (don't preempt)

- **Persistence**: `FileClaimsStore` reads a folder of JSONL; the Protocol matches a future Delta backend. No persistence code in the active path.
- **More extractors**: only `product_profile` extractor exists. `paper`, `trial`, `regulatory_doc`, `model_run`, etc. are file slots in the design but not implemented.
- **`pd_watch` and `pd_gate_assembler`**: planned services, not built. Don't add stubs.
- **Curation / supersession workflow**: removed all placeholder fields. Don't add back until there's a real curation pipeline.
- **Golden-set regression tests for prompts**: not built. Prompt edits today are silently breakable.
- **Searcher 4-primitive stamping**: Do NOT add 4-primitive stamping to Findings — they aren't documents.
- **Monitor v1 with benchmarker integration**: v0 produces Insights from
  web findings only. Comparing Insights against doc Claims (and emitting
  `Match` records) is the v1 layer — deferred.

## Where things live (file map for quick lookup)

```
shared/openai_client.py          OpenAI client (all services, including web_search)
shared/indications.yaml          indication vocabulary per intervention
services/chunker/pipeline.py     run_pipeline (parse + optional label)
services/chunker/stages/         parser_docx, parser_pdf, mapper
services/benchmarker/pipeline.py run_pipeline (parse → extract → bind)
services/benchmarker/stages/     extractor_product_profile, binder
services/benchmarker/store.py    ClaimsStore Protocol + FileClaimsStore
services/reviewer/pipeline.py    run_pipeline (parse + label → grade)
services/reviewer/stages/grader.py  3-dimension parallel grader
services/searcher/pipeline.py    run_pipeline (query -> Findings)
services/searcher/stages/searcher.py  single LLM web-search stage
services/searcher/models.py      Finding dataclass + protocol
services/monitor/pipeline.py     run_pipeline (files + primitives -> Insights)
services/monitor/stages/query_extractor.py    LLM: docs -> search queries
services/monitor/stages/insight_extractor.py  LLM: findings -> Insights
services/monitor/models.py       Insight dataclass + config
api/main.py                      FastAPI app + route registration
api/routes/{chunker,benchmarker,reviewer,configs}.py
api/routes/searcher.py           POST /api/searcher/run (query -> Findings)
api/routes/monitor.py            POST /api/monitor/run (files + primitives -> Insights)
api/schemas.py                   Pydantic wire models (ClaimOut, ReviewerRunResponse, ...)
api/streaming.py                 NDJSON streaming helper (background thread + queue)
web/lib/api.ts                   typed API client (runChunker, runBenchmarker, runReviewer)
web/lib/store.ts                 zustand: useHeaderStore + isHeaderComplete
web/lib/session.ts               zustand: per-tool result/busy/stage sessions
web/components/header-picker.tsx 4-primitive cascading picker
web/components/sidebar.tsx       static title (non-clickable) + nav + picker
web/app/{chunker,benchmarker,reviewer}/page.tsx  per-tool views
web/app/searcher/page.tsx        searcher debug UI (no picker)
web/app/monitor/page.tsx         monitor UI (picker + multi-file upload + insight list)
data/claims/                     JSONL claim store (gitignored)
```
