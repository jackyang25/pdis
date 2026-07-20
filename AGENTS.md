# PDIS — implementation invariants

Read the root `README.md` for product setup and the service READMEs for local
details. This file contains only the decisions an implementation agent must
preserve.

## Architecture and ownership

```text
web/ → api/ → services/ → shared/
```

- Imports flow only in that direction.
- Services may use another service only through its package `__init__.py`; never
  import another service's `stages/` or `models.py`.
- Services are stateless. Variability from LLMs and live retrieval is expected;
  hidden server-side session state is not.
- OpenAI is the sole model provider, constructed in `shared/openai_client.py`.
  Do not add per-request provider/model switches.
- Engineering behavior belongs in Python/TypeScript. Human-owned domain content
  belongs in `services/*/configs/*.yaml`; controlled vocabularies belong in
  `shared/*.yaml` as flat records keyed by intervention. Scout attributes also
  carry their authored `evidence_domain`; do not infer fixed-field domains in
  code.
- Adding an `(org, source_type, intervention_class)` product configuration is a
  YAML change, not a code branch.

Document tools use four primitives: `org`, `source_type`,
`intervention_class`, and `indication`. The first three select configs; all four
are output provenance, and `indication` scopes Scout retrieval. Use
`indication` everywhere—never reintroduce `therapeutic_area`.

`itpp` is an early candidate-agnostic TPP, `ctpp` is candidate-specific, and
`ipdp` is the development plan. Their different interpretation belongs in
config framing, not engine conditionals.

## Document and visual contract

- Chunker emits ordered, citable `ContentBlock`s with stable IDs. API routes
  must pass the original filename stem as `doc_id`; temporary filenames must
  never leak into block IDs.
- Embedded DOCX visuals are `block_type="image"` blocks carrying a typed
  `ImageAsset` (`media_type`, base64 bytes, SHA-256, source media type).
- Supported raster bytes are retained; Pillow normalizes other raster formats;
  LibreOffice is an optional fallback only for EMF/WMF/SVG → PNG.
- Images are canonical visual data. Do not replace them with generated prose,
  restore `image_lens`, or add a separate image-description stage.
- Multimodal calls label every image with its exact block ID. Mapper, Reviewer,
  Scout document reasoning, and Ask must preserve that association.
- The image bytes travel in result JSON. This keeps the system portable and
  stateless, but makes image-bearing artifacts larger.

## Reviewer contract

- Per section, completeness, adherence, and rigor are three independent LLM
  judgments with only their responsibility-specific rubric inputs.
- Variable → section → document rollups are deterministic math, not additional
  LLM synthesis.
- The whole-document consistency pass reports only cross-section conflicts.
- Grades are `A`–`F` plus `N/A`; do not merge or rename the three dimensions.

## Scout and retrieval contract

Scout operates per `Attribute`. TPP attributes come from
`shared/attributes.yaml`; IPDP attributes are checkable claims extracted from
the document. Both must converge before retrieval to the same document-bound
`Attribute`: stable name, neutral definition, canonical `document_target`, exact
block IDs, resolved status, one closed `evidence_domain`, and zero or more
document-stated typed entities. `definition_mode` (`fixed | dynamic`) records
only how the definition was supplied; downstream fields must not change meaning
by document type. Fixed domains are authored in `shared/attributes.yaml`;
dynamic domains and entities are extracted into the same closed contract. No
reasoning layer may independently rewrite a resolved document target.

The retrieval flow is deliberately split:

```text
relevant document blocks
→ source-neutral query intents
→ source adapter planning
→ source-native requests
→ normalized Findings
→ Insights
→ independent reasoning layers
```

Preserve these invariants:

- Query generation sees the relevant uploaded-document blocks and returns the
  exact `doc_block_ids` that shaped each query.
- General, geographic, counterfactual, and precedent tracks are additive. Their
  budgets come from Scout config; deduplication must not erase track lineage.
- Scout owns document meaning. Searcher adapters own source-specific query
  grammar, credentials, concurrency, execution, and response normalization.
- Every enabled adapter receives the complete neutral intent bundle for a
  field. Native requests may consolidate intents, but each request must carry
  the exact `intent_ids` and input query texts it compiled; the controller must
  reject silent omissions or altered lineage.
- The static adapter registry is engineering code. Enabled source keys are
  dynamic Scout config. API and UI discover registry metadata rather than
  mirroring source allowlists or labels.
- Source-specific public attribution belongs in `SourceSpec` and travels on
  normalized `Finding` provenance. UI surfaces render it generically; do not
  add provider-name conditionals to views.
- The generic Searcher controller validates keys, isolates source failures,
  preserves request order, schedules source queues fairly, and emits
  `SearchOutcome`s. A slow or rate-constrained lane must not block runnable
  work in another lane. Unknown keys must fail explicitly.
- Source applicability is deterministic metadata matching: compare the unit's
  closed evidence domain and document-stated entity types with `SourceSpec`
  capabilities. Never use another LLM router. A non-applicable enabled lane
  must emit a traced `skipped` outcome with the full neutral intent lineage and
  must not call its connector.
- URL deduplication must retain every query, source lane, retrieval path, and
  field-level source lane. `SearchTrace` records the native request, compiled
  intent IDs/input queries, track, document blocks, status/error, count, and
  returned URLs.
- Adding a source means: implement an adapter, register it, inject its connector
  through `SearchRuntime.integrations`, and opt configs into its key. Do not add
  source branches to Scout, API schemas, Ask, or UI.
- ToolUniverse is an optional authenticated HTTP connector injected through
  `SearchRuntime.integrations`. Each ToolUniverse-backed database remains its
  own registered source adapter and user-facing lane; adapters use a static
  tool allowlist and traces record the connector, exact operation, arguments,
  and URLs. Do not introduce autonomous tool routing or a generic
  `tooluniverse` evidence lane.
- Structured source tools may retrieve a bounded condition/intervention
  candidate set and rank it deterministically against every neutral input
  query. The request must retain the full intent bundle and record the native
  filters and ranking policy; never describe a broad provider filter as though
  it were the generated field query.

Scout's four result axes are intentionally orthogonal:

- drift: `contradicts | extends | confirms | unrelated`
- grounding: `well_grounded | partial | thin | unsupported | unknown`
- quantitative alignment: deterministic calculation over validated comparable
  measurements; never silently convert incompatible units
- precedent: coverage `direct | adjacent | none | unknown`, with outcome tracked
  separately as `favorable | mixed | unfavorable | unknown`

AI may select or label evidence only from closed, semantically distinct enums.
Deterministic code validates document IDs, insight IDs, URLs, units, provenance,
weights, deduplication, and rollups. Do not restore holistic “basis” tags.

## Ask and saved-result contract

- Ask is read-only and result-agnostic. It navigates result JSON, parsed document
  blocks, retained visuals, and URLs already cited by the result. It does not run
  fresh searches.
- Ask is stateless: the client sends the result, source document, and conversation
  history every turn.
- Portable Reviewer/Scout downloads use the versioned `pdis.result` envelope
  (`web/lib/result-file.ts`), currently version 7, separating analysis from
  `source_documents`.
- Backward compatibility belongs only in the import normalizer. Runtime UI and
  services consume the current contract without legacy branches.
- Old JSON may remain viewable, but missing images, query lineage, and retrieval
  provenance cannot be reconstructed. A rerun is required for a fully current
  result.

## API and progress contract

- Tool routes stream NDJSON: `stage`, `complete`, or `error`. Fan-out stages also
  report `completed`/`total`; single stages use a spinner.
- `web/lib/api.ts::streamRequest` is the browser consumer. Keep multipart uploads
  pointed directly at the FastAPI origin; do not restore the Next.js rewrite
  proxy.
- Ask has JSON `/api/assistant/ask` and plain-text streaming
  `/api/assistant/ask/stream` endpoints.
- Secrets remain server-side: `OPENAI_API_KEY`, optional `NCBI_API_KEY`, the
  ToolUniverse bearer token, and provider credentials held by that private
  connector service.

## Change checklist

Before finishing a cross-layer change, verify:

1. The data is wired parser/model → service → API schema → TypeScript type → UI
   or import/export boundary; do not add speculative placeholders.
2. Provenance survives every synthesis or deduplication step.
3. Prompts/configs have one clear responsibility and use the current enums.
4. No service reaches into another service's internals.
5. Old compatibility logic, when necessary, is isolated at an import boundary.
6. Run Python compilation/tests, `npm --prefix web run typecheck`, the production
   web build for UI changes, and `git diff --check`.

## Primary anchors

```text
shared/openai_client.py
services/chunker/{models.py,pipeline.py,stages/image_assets.py,stages/rasterizer.py}
services/reviewer/stages/grader.py
services/searcher/{models.py,controller.py,sources/}
services/scout/{context.py,pipeline.py,stages/}
services/assistant/{agent.py,navigator.py,document.py,legends.py}
api/{schemas.py,streaming.py,deps.py,routes/}
web/lib/{api.ts,result-file.ts,session.ts}
web/app/{chunker,reviewer,searcher,scout}/
```
