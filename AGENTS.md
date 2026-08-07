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
- Model stages use schema-bound structured outputs. Do not add plain-text JSON,
  markdown-fence recovery, or provider-signature compatibility to runtime
  services; saved-result compatibility belongs only at the import boundary.
- One request carries several items only when the stage's answer is about the set —
  deduplication, partitioning, or one aggregate judgement. A stage returning one
  decision per item sends one item per request, because unrelated items in a shared
  prompt influence each other and batch composition shifts between runs. Each stage
  states its choice in an `<ITEMS>_PER_REQUEST` constant carrying the justification;
  throughput comes from fan-out, never from packing unrelated items.
- A schema states every constraint its receiving code enforces. A required field
  is declared required, and non-empty text declares it; a validator that rejects
  what its own schema permits creates answers the model cannot get right.
- A model's verdict and a pipeline failure are different claims and never share a
  status value. Closed enums offered to a model exclude the failure members, so
  only code can record one, and a failure carries a machine-readable code beside
  its prose. Retain the subject either way — dropping it silently is worse than
  reporting that nothing was concluded about it.
- One layer decides meaning and downstream layers translate it. The stage that
  authors a value states the structured parts consumers need, in the same
  schema-bound response; no consumer recovers them by re-parsing finished text.
  Lexical term extraction, stopword lists, and synonym tables may reorder results
  already returned, never construct the request that returns them.
- Run-to-run consistency comes from request scope and schema, not from provider
  sampling parameters; current model tiers reject them. Identity and duplicate
  decisions are their own model layer, never folded into the prompt that creates
  the objects, and never approximated by string normalization in deterministic
  code.
- OpenAI is the default provider through `shared/openai_client.py`. Anthropic is
  limited to Scout's schema-bound document-target and external-measurement
  mapping through `shared/anthropic_client.py`; OpenAI independently reviews
  both quantitative proposal types.
- Engineering behavior belongs in Python/TypeScript. Domain content belongs in
  `services/*/configs/*.yaml`; shared controlled vocabularies belong in
  `shared/*.yaml`. Adding a normal `(org, source_type, intervention_class)`
  configuration is a YAML change, not an engine branch.
- A mechanic needed by two services lives in `shared/`, not once per service:
  request batching and fan-out in `shared/batching.py`, the schema-bound call in
  `shared/ai.py`, cross-service vocabularies in `shared/vocabulary.py`. Move a
  mechanic there on the second consumer, not the third.
- Services present one shape to their caller: `find_config` raises `LookupError`
  when a configuration is absent, optional configuration is asked about with a
  predicate, `validate_result_contract` returns the result it validated, and every
  service that needs a model client exports its `LLMClientProtocol`. A capability
  that genuinely differs keeps a different name.
- Document tools use `org`, `source_type`, `intervention_class`, and
  `indication`. The first three select configuration; all four are output
  provenance. Never reintroduce `therapeutic_area`.
- A tool's configuration rail holds three buckets, and which one a field belongs
  to is decided by a single question: **does the value leave the tool?**
  1. **Context** — `org`, `intervention_class`, `indication`. Always one each,
     every tool, from the shared store via `ContextFields`.
  2. **Document type** — `source_type`, via `SourceTypeField`. One per document,
     so one for most tools and several for Aligner.
  3. **Run parameters** — a tool's own knobs. Composed from the primitives in
     `ui/config-field.tsx`, owned entirely by that tool's page.

  Buckets 1 and 2 are contract data: they select configuration, are stamped on
  every block, travel in saved results, and are read across tools by Ask. They
  have one implementation each and take no field list — a shared component that
  could be configured is one that lets two tools disagree. Bucket 3 never leaves
  its tool, so nothing shared owns it. The split between 1 and 2 is cardinality,
  not status.
- `itpp`, `ctpp`, and `ipdp` differences belong in configuration framing and
  unit providers, not downstream conditionals.

## Documents and visuals

- Chunker emits ordered, citable `ContentBlock`s with stable IDs. API routes
  pass the original filename stem as `doc_id`; temporary filenames must never
  appear in block IDs.
- A supported document format declares its own structure, so tables, rows,
  headings, and reading order are read from the file rather than inferred from
  where glyphs landed on a page. `DOCUMENT_SUFFIXES` is the one authority for that
  set, and every layer gates on it rather than restating it. Do not add a
  rendering format: a table reconstructed from geometry can merge unrelated
  columns into one block whose text still satisfies exact-quote validation, and no
  structural check downstream can detect that. A format carrying declared
  structure — a tagged PDF, for example — would qualify; a rendered one never
  does. PDF remains an internal rasterizing step for slide rendering, never a
  document source.
- Images are canonical blocks, not generated descriptions. Retain supported
  raster bytes, normalize other rasters with Pillow, and use LibreOffice only
  for vector fallback and PPTX slide rendering.
- Every multimodal call labels an image with its exact block ID. Preserve that
  association through Inspector, Aligner, Scout, Ask, and portable JSON.
- Result JSON embeds parsed blocks and image bytes, not the original uploaded
  binary. Larger image-bearing artifacts are expected.

## Tool contracts

Each tool judges a document against a different authority: Inspector against an
authored rubric, Aligner against a second document, Scout against external
evidence. Those comparison targets are not interchangeable.

Every user-facing description of these tools states that in one shape — *what it
reads* against *the authority it is judged by* — so a reader can tell the tools
apart without any of them saying what it does not do. A negative clause ("Aligner
does not grade quality") means the positive statement is too weak; tighten the
positive statement instead. Guidance for the model, such as the Ask legends, is
the exception: there a negative is a guardrail, not a definition.

Those descriptions are read side by side, so they must be comparable as well as
correct. One sentence, 13–24 words, artifacts named by acronym (iTPP, cTPP, IPDP),
the clause after the colon saying what you learn rather than what was searched, and
no domain examples — naming vaccine attributes couples the copy to one of five
intervention classes. Utility and external tools are a separate family in
imperative voice; keep each family internally consistent. The rules and their
reasons live on `description` in `web/lib/tools.ts`.

Where the tools sit in a PPL's process is a separate statement and is made once,
in the section above the tool cards: between stage gates the document set drifts,
and these tools keep it true to its rubric, true to itself, and true to the
evidence before the next gate. Repeating that per tool guarantees the copies
drift.

### Inspector

Inspector publishes one atom under one vocabulary. `sections[]` holds every rubric
section, each with `units[]`, each unit owning the `Finding` objects raised against
it. `document_findings[]` holds the conflicts no unit owns.

- A `Finding` is one statement, one recommendation, one `reason`, and the blocks it
  was read from. It replaced three shapes for the same concept - a dimension
  assessment holding an issue list against a single recommendation, a ranked copy of
  the worst of them, and a cross-section conflict with different field names.
- `FINDING_REASONS` is the whole vocabulary: `missing | placeholder | unmet |
  off_template | unclear | conflicting`. `conflicting` is the only one no unit can
  raise. Adding a reason means one entry there and one label in `web/lib/api.ts`;
  nothing between the two branches on a reason's value.
- `level` derives from `reason` and a unit's `status` derives from its findings'
  levels, so `met` means exactly zero findings and no consumer can differ. Nothing
  stores a severity beside a reason.
- Conformance language, never severity language. Inspector knows what the rubric
  asked and what the document supplies, not what a shortfall costs a programme.
  There is no letter grade, no score, and no averaging.
- `not_applicable` comes only from the rubric's `optional` flag. Whether absence is
  acceptable is the author's decision, never the model's.
- **One model call per rubric unit.** Not one per axis: three calls cost three times
  the requests and each could report the same defect under its own name. A unit
  raises each reason at most once and `missing` silences the rest, enforced at parse
  time so a bad reply gets the retry, and again in `contract.py` for an imported
  result.
- `missing` is the only reason that cites nothing and the only one exempt from
  citing. Every other finding names the block it was read from.
- Ordering is `level`, then the sequence the rubric author wrote. That is the only
  authored priority signal; there is no section `weight`, which had one consumer and
  sat in eleven configs.
- A section and a variable declare the same four config keys - `name`,
  `description`, `optional`, `expectations` - so a section adds only `variables`.
  `expectations` is where an external standard belongs when one applies, as the
  expectation a unit is held to rather than as a second rubric.
- `assessment_status` and `consistency_status` are process facts outside the
  assessment: "not checked" must never read as "nothing found". A failed unit stops
  the run; the additive cross-section pass reports its own failure instead.
- Module responsibilities do not overlap: `models.py` declares shapes, `assembly.py`
  joins and ranks, `stages/assessor.py` owns the prompt and what is accepted back,
  `contract.py` owns the deterministic checks, `pipeline.py` owns the order.
- A derived value is computed, never defaulted. A default on one can only mask a
  missing derivation, so the published models declare derived fields required and
  `test_inspector_contract` reads the derived set from the serializer rather than
  keeping a list. And a fact has one representation: `is_present` is a property over
  `mapped_block_ids` because storing it made one fact carried three ways, which a
  contract check then had to police.
- A rubric mirrors an authored source template for its structure and records which
  one in `mirrors:`. Everything that makes it assessable - unit `description`,
  `stage_guidance`, `optional`, `expectations` - is authored here and is not in the
  source. `mirrors:` is a pointer for re-syncing, never a drift check: the source
  lives outside the repository and nothing here can verify it.
- Inspector evaluates document quality. It does not assign program risk,
  feasibility, funding decisions, or investment recommendations.

### Aligner

- Aligner currently reports no findings. A run parses its documents and returns
  them with the comparisons they resolve. When an analysis vocabulary is added it
  belongs in `configs/alignment.yaml`, never in code.
- **No stage knows how many documents a run holds or which types compare.**
  `document_roles` names the types and `edges` declares the ordered pairs; a run
  makes every declared comparison whose documents were both supplied, so two
  documents produce one and three produce two. Supporting a new document type is
  a config edit and must not reach `run_pipeline`, the route, the schema, or the
  upload form.
- An `edges` entry is ordered: `reference` is the document being honoured,
  `comparison` is the one measured against it. Direction lives on the edge, never
  on the document, because a document can sit on either side — the cTPP is
  compared against the iTPP and is the reference for the IPDP.
- Documents that resolve no declared comparison, or two documents of one type,
  fail loudly before parsing. A run that silently compares nothing is
  indistinguishable from one that found nothing wrong.
- Aligner never grades quality and never retrieves external evidence. Those are
  Inspector's and Scout's authorities, and a tool with two authorities can
  contradict the tool that owns one.

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
- Quantitative extraction receives already-owned canonical spans. It may split
  a span into multiple atomic targets but may not rescan unrelated blocks or
  choose field ownership again. Atomic targets are document-owned and link to
  fields through typed `defines | constrains | context_for` relations. Only
  defining and constraining links drive retrieval and calibration; contextual
  links remain traceable without creating statistics.
- A target's semantic profile records what the document says. Its separate
  direct-comparator contract records, for every semantic axis, whether external
  evidence must be exact, may vary within a compatible scope, is unconstrained,
  or remains unknown. Query generation, measurement mapping, review, and
  admission consume that one contract; they must not infer exact product
  identity from a document candidate name.
- Before review, document-wide reconciliation may group repeated or paraphrased
  representations of the same atomic claim. It may only partition existing,
  calculation-compatible target IDs; merge their declared links and exact
  provenance, and never rewrite the target meaning.
- AI owns prose meaning: written numbers, comparators, units, and clinical
  semantics. Pydantic/JSON Schema owns wire shape. Deterministic code checks only
  structural safety: known IDs, exact cited-excerpt existence, link and
  provenance membership, declared-unit compatibility, deduplication, and
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
- A requested publication window is applied where retrieved evidence enters the
  run, never at display. Every insight, precedent, and benchmark must describe the
  cohort that window admitted; filtering later would leave statistics computed over
  a wider set than the one shown. The window is declared before retrieval and
  carried on the reviewed draft, so a continuation cannot widen it after targets
  were approved. A finding whose source supplied no publication date is admitted —
  an absent date is not evidence of age. The retrieval record stays complete: a
  trace's `source_urls` is what the source returned, and
  `excluded_before_window` names which of those the window held out.
- Searcher adapters own source grammar, applicability metadata, credentials,
  rate limits, concurrency, execution, and normalization. Scout supplies neutral
  intents and config-selected adapter keys.
- A query intent carries both its natural-language text and the facets its author
  stated. An adapter selects whichever its API accepts and treats a blank facet as
  the intent's own scope; a field-addressed source varies its request by those
  facets and collapses identical native requests while keeping every contributing
  intent in lineage. Request cardinality follows what a source's grammar can
  express losslessly, not how many queries arrived.
- A request must be reachable, not merely precise. Facets carry roles: the
  condition anchors an intent's requests, one subject phrase is what a query asks,
  and remaining facets qualify meaning. Whether a qualifier joins the request
  depends on what that grammar does with it — an extra Boolean conjunct is a
  further coincidence a record must satisfy, while an extra plain-text term only
  sharpens ranking. Precision that returns nothing is not precision; retrieval owes
  coverage and the semantic stages supply the judgement.
- An anchor is one value, applied once. The other names a document shares are not
  further anchors, because requiring every pathogen, product, and institution it
  mentions at the same time describes no real record. A field-addressed source
  takes its anchor field from the intent, so a query restating that scope in its
  own words — a translation, a synonym — cannot spend one of the source's
  requests; only the narrowing fields vary.
- Narrowed requests are added to a source's intent-scope request, never
  substituted for it. The scope request is the only one guaranteed to match the
  source's own vocabulary, so it survives any request budget while precision is
  what gets dropped. A source declares that budget in its `SourceSpec` beside its
  concurrency and interval, because those limits belong to the source.
- A failed retrieval records the provider's message, not just the exception type.
  A saved result that says only `RuntimeError` cannot be diagnosed later.
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
  - a record's `target_relationship` (`direct | analogous | adjacent | unrelated |
    unknown`) asks what a record is ABOUT; `relationship` asks what an insight DOES
    to a claim. They share the token `unrelated` and mean different things by it, so
    a record may be `analogous` while its insight is `unrelated`. Separate stages
    assign them, neither prompt sees the other's vocabulary, and neither consumes the
    other's output.
- Scout's three negatives are distinct and none implies another: `contradicts` says
  the document's claim is disproven, precedent `unfavorable` says the approach has a
  poor track record, and the `counterfactual` query track only says where the
  evidence was looked for. A discovery track never determines a relation.
- Do not restore holistic “basis” labels or present descriptive cohort statistics
  as confidence intervals, success probabilities, or causal estimates.

## Results, Ask, and API

- A prompt that inserts configured text declares the slot on its catalog entry, and
  `scripts/generate_prompt_reference.py` reads the slots from the catalogs rather
  than a list of its own. A declared slot that publishes nothing, or inserted text no
  entry declares, is a documentation gap the generator can no longer hide.
- Inspector, Aligner, and Scout use the versioned `pdis.result` envelope in
  `web/lib/result-file.ts`, separating `analysis` from `source_documents`.
- A saved file carries two versions, and they answer different questions.
  `ENVELOPE_VERSION` covers the wrapper all three tools share, so bumping it
  invalidates every saved result. `ANALYSIS_VERSIONS[tool]` covers one tool's own
  shape, so bumping it invalidates only that tool's files. Change a tool's result
  shape, bump its entry — never the envelope. They were one number, which meant an
  Inspector change rejected saved Scout results that were still readable.
- Import validity is decided by the version, not by a field check: only a version
  can catch a field whose name and type survive while its meaning changes. A per-tool
  contract in `web/lib/result-contracts.ts` is the backstop for the version gate's
  weak point - a shape changed without its number bumped - and every tool has exactly
  one, run by both `pack` and `unpack` so a file that could not be read is never
  written. Those contracts sit outside every functional pipeline; nothing there runs
  during an analysis.
- A tool's top-of-page priorities render through the shared `ui/priority-panel`,
  which owns the container and decides nothing. What qualifies and in what order is
  one selector per tool in `web/lib/*-priorities.ts`, so improving priorities is an
  edit to that selector or to what it is handed - never to the panel, a page, or
  another tool. Every selector returns the same `PriorityItem`, and each states how
  its order was decided, because the AI glyph marks the wording as the model's and
  says nothing about the ranking.
- Review drafts are portable client state but are not downloadable final results.
  Final results are immutable: import, export, and Ask never recalculate them.
- Imports accept only the current final-result envelope, and report which version
  failed so a reader knows whether to re-run one tool or all of them. Runtime
  services and UI consume one contract without migration or legacy branches.
- Ask is stateless and read-only. The client submits the tool catalog, current
  final analyses, and direct utility outputs as one workspace bundle. Ask may
  inspect those result trees, parsed blocks, retained images, and URLs already
  cited by an analysis. Transient conversation attachments use the same block
  contract and remain user-supplied context; Ask never runs a new evidence
  search.
- Assistant conversation state shares the in-memory lifecycle of its submitted
  workspace bundle. Do not persist chat separately from results, parsed blocks,
  review state, or attachments. Final-result export/import is the durable seam.
- Stable public process and architecture documentation lives in
  `shared/product_knowledge.json`. The web documentation page and Ask consume
  that source; do not duplicate its prose in either layer. Tool metadata,
  controlled vocabularies, and run results remain separate authorities.
- Scout's model stages own their prompt text. `shared/prompt_reference.json` is
  generated from `services/scout/prompt_catalog.py`, never authored; a test
  regenerates it and fails on drift. Published prompts carry placeholder slots,
  not run content, and are process documentation rather than run provenance.
- A route constructs provider clients before opening its stream, and services raise
  domain errors that the route maps to a status code. A missing credential or an
  invalid request must fail the request, never arrive as an error event on a
  successful response.
- Tool routes stream NDJSON `stage`, `complete`, or `error` events. Fan-out
  stages report `completed`/`total`; single stages use indeterminate progress.
- Browser multipart uploads go directly to FastAPI. Keep all secrets server-side.
- Bespoke identity icons live in `web/public/icons/pdis/` and are mapped through
  `web/components/ui/pdis-icon.tsx`; use Lucide for generic actions.
- A negative *result* — a critical gap, a contradiction, an unfavorable
  precedent — uses `--tone-danger`. `--destructive` is reserved for a system
  error. They are different claims and must not be interchanged.
- Motion durations, easings, and reduced-motion opt-outs come from the tokens in
  `web/tailwind.config.ts` and the recipes in `web/lib/motion.ts`;
  `npm run test:motion` enforces both. A spinner and a streaming caret keep
  moving under reduced motion because their movement is the status.

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
5. Remove superseded paths; do not add compatibility migrations without an
   explicit product requirement.
6. Run Python compilation/tests, all relevant web `test:*` scripts,
   `npm --prefix web run typecheck`, the production web build for UI changes,
   and `git diff --check`.
