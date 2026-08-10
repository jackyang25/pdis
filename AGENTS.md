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
- The two tags that name subject matter — `indication` and `intervention_class` — are
  each a key **and** a search term, so the tag is spelled as the term a literature
  search actually uses (`tuberculosis`, not `tb`; `monoclonal_antibody`, not `mab`;
  `hiv` stays, because that is what the literature indexes). Multi-word names join
  with underscores and pass through `shared.vocabulary.search_term` on their way into
  text — once in Scout's pipeline for values that arrive as arguments, and via
  `config.intervention_term` where a stage holds a config instead. The text form is
  always derived, never a second stored field: the tag selects configuration and is
  stamped on every block, so a stored spelling could disagree with the key it was
  selected by. Reading `{config.intervention_class}` aloud in a prompt is what
  `test_indication_vocabulary.py` forbids.
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
- A result view is read by someone who learned the previous tool, so nine things
  are the same everywhere and none of them is checkable by a type:
  1. **`PriorityPanel` is the opening panel**, and `attribution` is always
     `by <Tool>` — never a description of the ordering, which is what `orderNote`
     is for. A tool may decline the panel only when its atom does not fit
     `PriorityItem`; Expert is the one case, because a 40–60 word gate question has
     nowhere to go in that shape and the panel would restate a list already flat.
     Record the reason at the call site, as Expert does.
  2. **One count grammar per page:** `<title> <count>`, the count in muted
     tabular figures beside the heading. Not `Title · 7`, and never both on one
     screen. `SectionHeading` takes a node rather than a string so a caller does
     not have to pre-format one into the other.
  3. **A number the model produced is shown even at zero**, because zero means the
     check ran and found nothing. A number config or the inputs produced is hidden
     at zero, because there is nothing to report. Hiding `0 answered` once made a
     run that assessed almost nothing look like a run with no such concept, and the
     figures still summed to the total, so nothing looked wrong.
  4. **`SignalHelp` is an affordance, not a section.** It sits right-aligned on the
     control row beside what it explains — Inspector's and Scout's tab rows, Expert's
     count row — never as its own left-aligned block in the vertical stack, where a
     reader takes it for a heading.
  5. **A trace places only lineage the result carries.** An annotation with no cited
     passage does not get anchored at a probable block to make the viewer look
     complete: that would turn a hint into provenance. Expert places answers read from
     a document and nothing else — an unanswered question has no passage, and an answer
     from pasted context was never chunked. A document with no marks is accounted for in
     the panels, not papered over in the trace.
  6. **Lineage is listed, never counted.** A trace inspector shows every passage its
     result was read from, each one openable, via the shared `TracePassageList`. Three
     tools printed "4 source passages" beside the one passage the reader arrived at, so
     the other three were asserted and unreachable — a count reads as provenance while
     being the one thing a trace exists to let you check. The list carries where each
     passage sits and its opening words, names its document only when the result spans
     more than one, and marks the passage the panel was opened from.
  7. **Revealing a passage centres it and selects nothing.** One path serves every
     caller — a result row, a coverage cell, the passage list — because they are the
     same act: switch document if the passage is elsewhere, widen the layer if its mark
     is filtered out, scroll to the middle, ring it. Opening the details panel is a
     second, deliberate click on the mark. Auto-opening it put a reader in front of a
     panel restating the row they had just left, and where that panel is a sheet it
     covered the very passage it was sent to reveal.
  8. **One tab per view, not one per document**, and it is labelled **Documents**.
     `DocumentTraceViewer` already switches between the documents a result carries, so
     per-document tabs would be a second mechanism for the same thing and would break
     at one document. The label names what is behind it, not the mechanism: it read
     "Document", "Document trace" and "Documents" across three tools, and "trace" is
     jargon a reader has to be taught. Plural everywhere rather than varying with the
     count — one string beats three, and a tool holding one document is not misled by
     it. `value="trace"` stays as the internal key.
  9. **Weight follows consequence.** The most consequential fact in a result gets
     the strongest treatment — amber and an icon, as Scout's context-validation
     notice does — and provenance gets the weakest, at the foot of the card. A
     result whose review mostly could not be run must not read as a completed one.

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
  association through Inspector, Aligner, Expert, Scout, Ask, and portable JSON.
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
correct. One sentence, 12–24 words, artifacts named by acronym (iTPP, cTPP, IPDP),
the clause after the colon saying what you learn rather than what was searched, and
no domain examples — naming vaccine attributes couples the copy to one of five
intervention classes. Utility and external tools are a separate family in
imperative voice; keep each family internally consistent. The rules and their
reasons live on `description` in `web/lib/tools.ts`.

Where the tools sit in a PPL's process is a separate statement and is made once,
in the section copy above the tool cards: between stage gates the documents drift
apart, and these tools keep each one true to its rubric, its targets true to the
evidence, and the documents true to each other before the next gate. Repeating that
per tool guarantees the copies drift. Its clauses stay in the same order as the
cards, so the sentence reads as what the cards say.

Sections themselves group by **audience** and by nothing else. A section named
after a phase of the process or a kind of analysis puts two axes at one heading
level, and a reader can no longer tell what a heading is telling them. A tool's
kind of work is already carried per card by `capability`, which is where a second
axis belongs. `web/lib/tool-sections.test.ts` enforces this.

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

- **A comparison runs one way.** The reference document's requirements are the rubric
  and the other document is measured against them, one requirement per call. The
  vocabulary this replaced — `aligned | modified | conflict | missing | introduced` —
  described how two documents *differ*, so "annual dosing" against "every 6 months" and
  against "every 2 years" carried one label with opposite meanings for the investment.
  Never reintroduce a symmetric relation.
- Verdicts are `meets | exceeds | falls_short | not_comparable | not_addressed`, closed
  and asymmetric. `exceeds` is never folded into `meets`: a candidate well past its
  target may mean the target is stale. `not_comparable` exists so vagueness is not
  reported as a shortfall — a qualitative claim against a numeric bar is neither worse
  nor silent, and calling it either is a judgement the text does not support.
- `falls_short` and `not_comparable` carry `gap`; the other three refuse it. That
  sentence is what a PPL takes back to whoever wrote the document, so leaving it to
  prose would make it usually present and never guaranteed.
- A requirement is read out of the reference document, cites the passage that states it,
  and is atomic — compound sentences are split at extraction, because one verdict cannot
  honestly cover three facts. Aligner never decides what matters.
- **A finding's two citation lists are not interchangeable.** `reference_block_ids` must
  be blocks of the document that sets the bar and `comparison_block_ids` blocks of the
  document measured; the schema offers only the latter to the model, and the contract
  checks both. A result that mixed them would read perfectly and be unfalsifiable.
- Extraction is one call per comparison because how many requirements a document states
  is a fact about the whole document — the case the one-item-per-request rule exempts.
  Judgement is one call per requirement, always.
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
  indistinguishable from one that found nothing wrong — which is also why the result
  contract refuses an alignment carrying zero findings.
- **Two comparisons are linked at the document they share, by block id and nothing
  else.** With three documents the middle one is measured in one comparison and
  authoritative in the next, so a plan can faithfully deliver a commitment that itself
  falls short — every verdict correct, and the second list all good news. `chainWarnings`
  finds it by intersecting the upstream finding's cited passages with the downstream
  requirement's, derived on read, no model and no stored field. It is **not** an
  `itpp → ipdp` edge: that would re-report the same gap and blame the plan for a bar it
  was never written against. The note claims something about the *passage*, never that
  the two requirements are the same one, because a dense block can carry several facts —
  and it under-reports rather than guessing, since matching requirement text would be the
  fuzzy comparison this codebase refuses everywhere else.
- There is no compliance score and no percentage: one figure blending "it meets this",
  "it beats this", "it says something incomparable" and "it does not cover this" would
  tell a committee something untrue. Totals are not comparable across comparisons
  either, because the denominator is however many requirements that reference document
  happens to state.
- Aligner never grades quality and never retrieves external evidence. Those are
  Inspector's and Scout's authorities, and a tool with two authorities can
  contradict the tool that owns one.

### Expert

Expert's authority is one stage gate's SME question bank. It reads several documents at
once and **renders no verdict on them**: it reports which of the gate's questions the
supplied material answers and which it does not.

- The boundary against Inspector, which shares no code or config with it: Inspector
  asks whether *one* document is complete against its own template; Expert asks
  whether the evidence exists *anywhere in the set* for a reviewer to close a
  question. The resemblance is structural — a list of sections holding units, one call
  per unit — and structural only.
- The bank is **transcribed** into `services/expert/configs/*.yaml`, never parsed from
  the SME document. A reader for someone else's prose format is a normalization layer
  that breaks whenever that document is edited.
- **Only what the source document guarantees may decide anything.** That is the gate,
  the owning discipline, the question text, the `[PQ]` markers, and the eleven
  questions whose own text states a class restriction. Everything else the bank
  carries is a tag: displayed, never gating. This is the invariant the tool exists
  under, and it was learned by violating it — a per-question judgment about which
  document type could answer a question drove two of five states, so a wrong judgment
  withheld a question from assessment or attributed a gap to a grantee for something no
  document was ever meant to hold.
- `likely_in` is that judgment, demoted. It never reaches resolution, never reaches
  the model, and is presented as "usually answered in". A wrong value costs a
  misleading hint.
- `applies_to` is the one field that removes a question from a run, so it is set only
  where the question text states the restriction, never by reading subject matter and
  inferring a class. A wrongly inapplicable question vanishes silently and reports as
  "not a shortfall", which is the least detectable error the bank can hold.
- Four states, and every one is traceable: `not_applicable` from the question text,
  and `answered`, `partly_answered`, `not_found` from one model call. A model is
  offered only the last three, ordered by how much of the question is closed.
  `not_found` is named for what is true regardless of any hint — "not found in what was
  supplied" — because `absent` invites the reader to hear a fault.
- `partly_answered` exists because the bank's questions are compound: each asks three
  to five things in one sentence, so a binary forced the model to file "four of five
  clauses answered" as if nothing were there, and a whole gate read the same whether
  the plan was thorough or blank. That is a number carrying no information. It is not a
  return of the two states that were removed — those came from a judgment about which
  document should hold an answer, while this is an observation of the material.
- A partial carries `missing`: one sentence naming what the question still leaves open,
  required by the contract on that state and refused on every other. It is the sentence
  a PPL takes back to the grantee, and leaving it to prose meant it was usually present
  and never guaranteed. `partly_answered` is never presented as progress and never
  added to `answered`: there is no score.
- The assessor's decision enum is the cross product of completeness and source, not two
  fields. Five values reads wide, but a conditional requirement — "`missing` is required
  only when partial" — is the one thing the schema cannot express, so the decision
  carries the condition and code checks the pairing.
- **The routing is the discipline**, which the source document guarantees. Grouping
  unanswered questions by discipline is the tool's main output; a claim that no
  document could ever answer one is not.
- Every applicable question is read against **everything supplied**. That is what
  makes the run honest, and it is also what makes it affordable: identical material on
  every call is a cacheable prompt prefix, so the supplied documents precede the
  question in the user message and the expensive half is paid for once.
- Banks are keyed `(org, gate)`; the intervention class filters questions inside a
  bank rather than selecting which to read, so `find_config` takes two keys.
- `load_config` raises on a bank naming an unknown intervention class or document
  type, and `available_gates` does not swallow load errors — a malformed bank is a
  broken gate, not a scaffold to skip. Swallowing them once emptied the gate selector
  with no error anywhere.
- The denominator never shrinks, and counts are derived by readers rather than carried:
  a stored count is a second authority that can disagree with its own list. Never
  publish a combined coverage figure.
- Transient context is prompt-only: pasted, never chunked, never stored. Only its label
  reaches the result, so an answer sourced from it carries attribution without lineage
  and can never be presented as cited. A label is free text the user typed, never a
  `source_type`.
- **No reconciliation or deduplication stage.** The bank's coordination map has
  Translational Medicine and Clinical Pharmacology reach dose selection independently
  and disagree in public at EOP1 and EOP2. Merging their answers would destroy the one
  thing the bank was built to produce.
- Order is the bank's own: discipline sequence, then question number. Nothing re-ranks,
  so two runs on one gate compare line by line.

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
- Inspector, Aligner, Expert, and Scout use the versioned `pdis.result` envelope in
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
- A cross-tool synthesis lives in a skill, never in a service. Each tool judges
  against one authority and reads no other tool's output, so the only place two results
  may be combined is a reader that issues no verdict of its own: one markdown file in
  `services/assistant/skills/`, cited on both sides. `requires` names result types that
  must all be held; `requires_any` names types of which one is enough, which is what
  distinguishes a pairing from a workflow that applies to whatever a reader holds.
  Adding one is a file — no agent, registry, or schema change.
- A skill's prose is an untyped reader of a result contract, and nothing breaks when the
  contract moves. `compare-drift-against-evidence` went on instructing the model to read
  Aligner's deleted `links` and `modified` relations for a whole redesign, because no
  import, type, or test touched it. `test_assistant_resources` now fails on retired
  vocabulary in backticks; extend that list whenever a published state or field is
  renamed, in the same change.
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
