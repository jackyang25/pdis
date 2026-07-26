# PDIS implementation invariants

Read `README.md` for setup and each `services/*/README.md` for service details.
This file contains only constraints whose violation would change system meaning,
provenance, or portability.

## Boundaries

```text
web/ → api/ → services/ → shared/
```

- Imports flow only in that direction. A service may use another service only
  through its package `__init__.py`; never import another service's `stages/` or
  `models.py`.
- Services are stateless. The client carries review drafts, source documents,
  and result state; do not introduce hidden server sessions.
- API composition owns provider clients, credentials, and connector injection.
  Browser requests cannot choose providers or model names.
- OpenAI is the default provider through `shared/openai_client.py`. Anthropic is
  limited to Scout's schema-bound document-target and external-measurement
  mapping through `shared/anthropic_client.py`; OpenAI independently reviews
  both quantitative proposal types.
- Engineering behavior belongs in Python/TypeScript. Domain content belongs in
  `services/*/configs/*.yaml`; shared controlled vocabularies belong in
  `shared/*.yaml`. Adding a normal `(org, source_type, intervention_class)`
  configuration is a YAML change, not an engine branch.
- Document tools use `org`, `source_type`, `intervention_class`, and
  `indication`. The first three select configuration; all four are output
  provenance. Never reintroduce `therapeutic_area`.
- `itpp`, `ctpp`, and `ipdp` differences belong in configuration framing and
  unit providers, not downstream conditionals.

## Documents and visuals

- Chunker emits ordered, citable `ContentBlock`s with stable IDs. API routes
  pass the original filename stem as `doc_id`; temporary filenames must never
  appear in block IDs.
- Images are canonical blocks, not generated descriptions. Retain supported
  raster bytes, normalize other rasters with Pillow, and use LibreOffice only
  for vector fallback and PPTX slide rendering.
- Every multimodal call labels an image with its exact block ID. Preserve that
  association through Inspector, Aligner, Scout, Ask, and portable JSON.
- Result JSON embeds parsed blocks and image bytes, not the original uploaded
  binary. Larger image-bearing artifacts are expected.

## Tool contracts

### Inspector

- Completeness, adherence, and rigor are independent LLM judgments. Grades are
  `A`–`F` plus `N/A`.
- Variable → section → document rollups are deterministic. The authored rubric
  is the denominator; model omissions cannot improve a grade.
- The document-wide pass reports only cross-section conflicts with exact block
  lineage and an explicit completion status.
- Inspector evaluates document quality. It does not assign program risk,
  feasibility, funding decisions, or investment recommendations.

### Aligner

- Aligner compares exactly one reference document with one comparison document.
- Units use the closed vocabulary `target | activity | milestone | requirement |
  dependency | risk_response`. Relations are `aligned | modified | conflict |
  missing | introduced`.
- Every unit and relation retains both documents' exact block lineage. Code
  derives omitted `missing`/`introduced` relations and counts deterministically.
- Document-type differences remain configuration; both inputs converge to the
  same unit and relation contracts.

### Scout

- TPP vocabulary fields and dynamically extracted IPDP claims converge before
  retrieval to one document-bound `Attribute`: stable name, neutral definition,
  canonical target, exact spans/blocks, resolution status, closed evidence
  domain, and typed entities. Downstream stages may not rewrite it.
- Document authority narrows monotonically:

  ```text
  parsed blocks
  → canonical claim ledger
  → quantitative proposals from those exact spans
  → reviewed targets
  → source-neutral intents
  → source-native requests
  → Findings → Insights → independent result axes
  ```

- Validate the configured indication before retrieval. Only a clear, block-cited
  mismatch stops the run; ambiguity remains explicit.
- Fixed fields are resolved in bounded, block-aligned batches that see the full
  field catalog. Cite exact block IDs and source spans. Retry only structurally
  invalid or missing decisions once; unresolved canonical fields stop retrieval.
- Quantitative extraction receives already-owned canonical spans. It may split a
  span into multiple atomic targets but may not rescan unrelated blocks or
  choose field ownership again.
- AI owns prose meaning: written numbers, comparators, units, and clinical
  semantics. Pydantic/JSON Schema owns wire shape. Deterministic code checks only
  structural safety: known IDs, exact cited-excerpt existence, provenance and
  ownership membership, declared-unit compatibility, deduplication, and
  arithmetic invariants. Never re-parse prose to require normalized digits,
  symbols, or unit spellings.
- Structural checks authorize model output; they do not replace semantic review.
  Never treat schema validity alone as provenance validity.
- Target proposals are reviewed before retrieval. Prose-derived evidence
  measurements receive an independent recommendation and require explicit
  admission before statistics; rejected and uncertain records remain auditable.
  Final calculations use only admitted,
  source-owned, evidence-unit-deduplicated scalars. Default to one evidence unit
  per source record; split only explicitly distinct, non-overlapping arms or
  cohorts. Alternative estimates within one unit remain one review choice.
  Never silently convert units.
- Query tracks (`general`, `geographic`, `counterfactual`, `precedent`) are
  additive. Preserve track, block, intent, target, source-lane, connector, and
  URL lineage through planning and deduplication. Target IDs indicate retrieval
  coverage, not evidentiary support.
- Searcher adapters own source grammar, applicability metadata, credentials,
  rate limits, concurrency, execution, and normalization. Scout supplies neutral
  intents and config-selected adapter keys.
- The static source registry is code; enabled keys are configuration. Adding a
  source means implementing and registering an adapter, injecting any connector,
  and opting configuration into its key—never adding source branches to Scout,
  API schemas, Ask, or UI.
- ToolUniverse is an authenticated injected connector, not a generic evidence
  lane or autonomous router. Every database remains a distinct adapter with a
  fixed operation allowlist and complete trace.
- Source failures are isolated. Independent fan-outs use bounded concurrency,
  request-local inputs, lock-guarded progress, and order-preserving assembly. A
  slow source lane must not occupy capacity reserved for runnable lanes.
- `Finding.evidence_role` separates evidence from reference metadata.
  Reference-only catalog records and raw surveillance reports must not enter
  grounding, drift, calibration, or precedent reasoning.
- Web-search excerpts may support qualitative discovery but are not verbatim
  source passages and must never enter quantitative calibration.
- Scout's axes remain orthogonal:
  - relationship: `contradicts | extends | confirms | unrelated`
  - grounding: `well_grounded | partial | thin | unsupported | unknown`
  - quantitative calibration: reviewed comparable measurements plus
    deterministic descriptive statistics
  - precedent: coverage `direct | adjacent | none | unknown`, with outcome
    `favorable | mixed | unfavorable | unknown` stored separately
- Do not restore holistic “basis” labels or present descriptive cohort statistics
  as confidence intervals, success probabilities, or causal estimates.

## Results, Ask, and API

- Inspector, Aligner, and Scout use the versioned `pdis.result` envelope in
  `web/lib/result-file.ts`, separating `analysis` from `source_documents`.
- Review drafts are portable client state but are not downloadable final results.
  Final results are immutable: import, export, and Ask never recalculate them.
- Backward compatibility lives only in the import normalizer. Runtime services
  and UI consume the current contract without legacy branches.
- Ask is stateless and read-only. It may inspect result JSON, parsed blocks,
  retained images, and URLs already cited by the result; it never runs a new
  evidence search.
- Tool routes stream NDJSON `stage`, `complete`, or `error` events. Fan-out
  stages report `completed`/`total`; single stages use indeterminate progress.
- Browser multipart uploads go directly to FastAPI. Keep all secrets server-side.
- Bespoke identity icons live in `web/public/icons/pdis/` and are mapped through
  `web/components/ui/pdis-icon.tsx`; use Lucide for generic actions.

## Change checklist

Before finishing a cross-layer change:

1. Wire data through model/parser → service → API schema → TypeScript → UI or
   import/export boundary.
2. Preserve provenance through synthesis, batching, parallel assembly, and
   deduplication.
3. Give every model stage one responsibility, one schema, and only its required
   context. Use closed enums with explicit `unknown`/`other` where appropriate.
4. Keep deterministic checks structural and calculations reproducible; do not
   encode semantic interpretation as string heuristics.
5. Keep compatibility code at import boundaries and remove superseded runtime
   paths.
6. Run Python compilation/tests, all relevant web `test:*` scripts,
   `npm --prefix web run typecheck`, the production web build for UI changes,
   and `git diff --check`.
