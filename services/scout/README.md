# Scout

Pressure-tests document targets against live evidence. Scout derives canonical
document-bound fields, traced retrieval, atomic evidence insights, target
relationships, grounding, quantitative alignment and assumption calibration,
and precedent signals.

## Canonical field contract

TPP definitions and IPDP claims converge to one `Attribute` before retrieval:

| Field | Meaning |
|---|---|
| `name` | Stable downstream reference |
| `description` | Neutral definition of the field |
| `document_target` | Faithful document claim or commitment |
| `block_ids` | Exact blocks supporting the target |
| `document_spans` | Exact quote-to-block provenance that deterministically derives the target and block IDs |
| `definition_mode` | `fixed` vocabulary or `dynamic` extraction provenance |
| `target_resolved` | Binding completed, including an intentionally absent target |
| `target_resolution_reason` | Explicit binding outcome or fail-closed reason |
| `evidence_domain` | Closed source-applicability domain |
| `entities` | Explicit document-stated typed entities |
| `quantitative_targets` | Atomic numeric claims with one canonical field owner, one shared `NumericExpression`, immutable semantic IDs, exact provenance spans, roles, and a typed target semantic profile |
| `quantitative_statement_dispositions` | Cited contextual, non-scalar, range/set, or uncertain numeric statements that were intentionally not calibrated |
| `quantitative_target_status` | Explicitly distinguishes a present target, a non-numeric field, and unresolved wording |

No reasoning stage may rewrite this canonical target.

## Public contract

```python
from services.scout import assessments_to_dicts, find_config, matches_to_dicts, run_pipeline
from services.searcher import SearchRuntime
from shared.openai_client import OpenAIClient

config = find_config("bmgf", "itpp", "vaccine")
client = OpenAIClient()
# `integrations` is a precomposed connector mapping for config.sources.
runtime = SearchRuntime(llm_client=client, integrations=integrations)
result = run_pipeline(
    ["/path/to/doc1.docx"],
    config=config,
    openai_client=client,
    retrieval_runtime=runtime,
    org="bmgf",
    source_type="itpp",
    intervention_class="vaccine",
    indication="rsv",
)
print(matches_to_dicts(result.matches)[:3])
print(assessments_to_dicts(result.assessments)[:3])
print(result.stats)
```

## What an `Insight` is

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable pipeline-derived lineage key |
| `statement` | str | One atomic factual observation from external evidence |
| `supporting_findings` | list[Finding] | Sources backing the statement |
| `query` | str | The search query that surfaced the supporting evidence |
| `retrieval_target_ids` | list[str] | Quantitative targets covered by the retrieval request; coverage lineage only, not semantic support |
| `org` / `source_type` / `intervention_class` / `indication` | str \| None | Stamped from inputs |
| `attribute_ref` | str \| None | Vocabulary or document-extracted unit this Insight relates to |

## What a `Match` is

| Field | Type | Notes |
|---|---|---|
| `insight` | Insight | The external evidence being compared |
| `relation` | str | One of `contradicts`, `extends`, `confirms`, `unrelated` |
| `reason` | str | Short explanation of how the Insight relates to the uploaded document |
| `doc_block_ids` | list[str] | Exact document blocks used for the comparison |

`Match` is the doc-aware primitive scout emits. `Insight` stays useful
as external evidence underneath it.

## What an `EvidenceAssessment` is

| Field | Type | Notes |
|---|---|---|
| `attribute_ref` | str | Vocabulary or document-extracted unit |
| `strength` | str | One of `well_grounded`, `partial`, `thin`, `unsupported`, `unknown` |
| `reason` | str | One-sentence explanation |
| `doc_target` / `doc_block_ids` | str / list[str] | Document target and its exact source blocks |
| `supporting_insight_ids` | list[str] | Exact insights used by the aggregate judgment |
| `supporting_findings` | list[Finding] | Sources reachable from those selected insights only |

## Pipeline

1. **parse** - chunker parses each uploaded doc without section mapping.
2. **validate context** - a conservative, block-cited check compares the configured indication with the document. A clear mismatch stops before retrieval; absent or ambiguous context remains `uncertain`, never guessed or silently rewritten.
3. **resolve the document claim ledger** - fixed TPP decisions are requested in bounded output groups over ordered, block-aligned document chunks. Every group sees the complete field catalog, so batching limits response size without turning fields into isolated interpretations. Decisions bind to exact quoted spans, blocks, and explicitly stated entities; the chunk decisions merge into one document ledger. Only structurally missing or invalid decisions are retried once; remaining uncertainty is retained with a reason and stops before numeric interpretation or retrieval. Dynamic IPDP units arrive already bound from their block-aligned extraction. Both paths produce the same canonical `Attribute` ledger, including one closed evidence domain, with `definition_mode` preserving only provider provenance. Fixed domains are authored in the shared vocabulary; dynamic domains are selected from the same enum.
4. **map the document-first numeric ledger** - Scout partitions all nonempty document blocks into stable, non-overlapping statement units and reviews each unit exactly once against the complete canonical field catalog. Every bounded batch also receives the already-resolved document-claim ledger as authoritative cross-block context. Numeric syntax may come only from the local statement; normalized meaning may cite either that statement or an enumerated canonical binding. For each proposed target the model selects the smallest complete literal expression and its exact value/operator/unit substrings alongside the normalized expression. Service-owned Pydantic wire models supply both the OpenAI schema and runtime shape validation. Code verifies literal presence, mechanically readable numeric equality, symbolic operators, ownership, and provenance without classifying prose-level numbers, ranges, units, or clinical meaning. Independently comparable exact or directional scalars become atomic targets owned by one resolved, document-present field; conditions, numeric categories, ranges/sets, nonnumeric text, and unresolved wording receive explicit classifications. Only structurally missing or invalid reviews are retried once by statement ID with precise rejection codes. Remaining uncertainty stays auditable and is excluded from numeric target queries and calibration; it does not discard the verified claim ledger or block qualitative evidence retrieval. Numeric expressions cannot override the claim ledger or cross a field's canonical cited blocks. Per-field target arrays and status text are projections of this ledger; no field independently re-extracts targets and no ownership-repair pass follows it.
5. **per-unit query intents** - only resolved fields with document-present targets continue. The LLM generates document-aware intents from the canonical definition and target across general, geographic, counterfactual, and precedent tracks. The general track must cover every verified quantitative target. Numeric retrieval descriptors reuse the target's canonical semantic dimensions and unit while mechanically omitting any phrase that restates its magnitude/unit, as well as its comparator and threshold/optimal role, so evidence on either side remains discoverable. Numeric-spelling variants such as decimal commas and written numbers are checked before a target-linked query is accepted. Each intent carries both block lineage and the target IDs it was designed to cover.
6. **plan + search** - Scout converts units to Searcher's neutral `RetrievalIntent`. The generic controller compares the unit's evidence domain and document-stated entity types with each enabled adapter's declared capabilities. Applicable adapters receive the complete bundle and independently compile source-native requests; non-applicable adapters emit explicit traced skips without connector calls. The controller centrally attaches target lineage to every compiled request and verifies complete intent coverage, so source adapters do not duplicate this policy. It then executes fair per-source queues with adapter-owned rate/concurrency policy. `search_plan` retains every native request or skip, its exact input intent IDs/texts, applicability reason, status, document blocks, quantitative target IDs, track, result count, and source URLs. URL dedupe preserves every retrieval path and the exact lanes supplying title, excerpt, and publication date.
7. **deterministic projections** - typed development and safety records are grouped into a development landscape and safety-signal view. Missing fields remain missing; no LLM or source-specific parsing runs in Scout.
8. **per-variable insights** - LLM extracts atomic Insights in count- and payload-bounded batches from evidence-role Findings only. Reference-only catalog/entity records cannot influence reasoning. A deterministic pass merges duplicate facts across batch boundaries and assigns stable IDs. Insights retain which target-specific requests retrieved their sources, explicitly as coverage rather than evidence support.
9. **classify** - LLM classifies every Insight against a bounded, block-annotated context for that variable and returns validated document block IDs.
10. **evidence** - LLM assesses grounding and selects only the exact insight indices it used; the service resolves those to stable IDs and sources without allowing the canonical target to drift.
11. **quantitative calibration** - calibration consumes the already verified target bundle; it never re-extracts targets. Repeated semantic claims merge exact expression and semantic provenance spans, while threshold, optimal, population-specific, and time-specific targets remain separate ledgers. Document targets and source measurements share one syntax-only `NumericExpression` (`point_estimate`, `range`, `bound`, `confidence_interval`, `count`, `rate`, `other`, or `unknown`). Targets use an eight-slot semantic profile (`measure`, `endpoint`, `intervention`, `population`, `regimen`, `time_horizon`, `statistic`, `conditions`) with explicit `specified`, `not_specified`, `unknown`, and `other` states. For each deduplicated source-owned passage, the model returns one `measurements_found`, `no_relevant_measurement`, or `uncertain` disposition and zero or more complete exact-quoted measurements; there is no regex-produced number-fragment fan-out. Target/passage batches run through one globally bounded work queue, retain the same three-passage prompt boundary and local retry, and are restored to canonical target and passage order before cohort construction. Every measurement also carries the smallest complete literal expression and exact syntax parts used to propose its normalized expression. Each semantic assessment returns only the dimensions constrained by that target, co-locating normalized source meaning and yes/no/unknown compatibility plus source ownership. Code supplies neutral values for unconstrained dimensions so the public shape remains stable. The model does not supply the aggregate cohort label: code derives `comparable`, `contextual`, `incompatible`, or `unknown`; missing ownership, required context, or ambiguous target meaning fails closed locally. Code verifies the source ID, exact quote and syntax, machine-readable numeric equality, symbolic operator, enums, URL, source identity, and deduplication. It does not independently reinterpret prose-normalized values or units. Only derived-comparable atomic scalars (`point_estimate`, `count`, or `rate`) with the same AI-produced unit identifier as the target enter minimum/maximum/mean/median/quartiles/observed standard deviation, target/ambition percentiles, and the literal target-meeting share. Contextual and incompatible measurements remain traceable without distorting statistics. These outputs describe the selected cohort only and are never confidence intervals or forecast probabilities.
12. **precedent** - LLM separately classifies coverage (direct/adjacent/none/unknown) and outcome (favorable/mixed/unfavorable/unknown), with independent supporting insight IDs and canonical document blocks.

## Context and ownership boundaries

Each model call receives only the context needed to produce its next canonical
handoff. Later stages consume that handoff; they do not independently reinterpret
the original document.

| Stage | Authoritative input and context radius | Canonical output | Explicitly not owned here |
|---|---|---|---|
| Indication preflight | Bounded document-wide block view and configured indication | Cited `DocumentContextValidation` | Fields, targets, or evidence judgments |
| Unit provider | Fixed shared vocabulary, or large block-aligned document chunks for dynamic plans | Neutral unit definition and exact document claim in `Attribute` | Retrieval grammar or evidence meaning |
| Document claim ledger | Complete fixed-field catalog plus one ordered block-aligned document chunk per bounded output group, or block-aligned dynamic-plan extraction | Canonical `Attribute`s with exact quoted targets, block IDs, explicit entities, and fail-closed unresolved reasons | Numeric calibration or external evidence |
| Numeric statement ledger | Every non-overlapping document statement, its complete local source block, and the resolved canonical document-claim ledger | One reviewed document ledger with atomic targets or explicit non-target/uncertain classifications and exact semantic source spans | Source interpretation or cohort statistics |
| Query generation | Canonical `Attribute` and threshold-neutral target descriptors | Source-neutral `QueryIntent`s with block and target lineage | Source grammar, credentials, or result parsing |
| Source planning/execution | Complete intent bundle and adapter capability metadata | Source-native requests and normalized `Finding`s | Document interpretation |
| Insight extraction | One field definition plus bounded external Findings | Atomic source-cited `Insight`s | Document comparison or target rewriting |
| Drift / grounding / precedent | Immutable canonical target binding plus selected external Insights | Independent cited axis judgments | Rebinding the target or calculating statistics |
| Source measurement mapping | One canonical target semantic profile plus one bounded, source-owned passage and source identity | Exact-quoted measurement proposals and closed yes/no/unknown semantic decisions | Document reinterpretation, target pass/fail, or aggregate cohort labels |
| Calibration admission/math | Verified target, proposals, source identity, units, and provenance | Comparable cohort, exclusions, and descriptive statistics | LLM judgment or unit conversion |

Calibration therefore needs the target expression, semantic profile, semantic
provenance, target ID, and canonical field owner from upstream. It does **not**
need the uploaded document again: rereading it there would create a second,
potentially divergent target interpretation. Conversely, a source passage never
inherits missing meaning from an Insight, title, query, or model background
knowledge.

## Structured model boundary

Every Scout model response uses one strict JSON Schema from
`services/scout/ai_contracts.py`, requested through the single gateway in
`services/scout/ai.py` and the provider wrapper in
`shared/openai_client.py`. Closed enums include honest `unknown` and, where the
domain needs a catch-all, `other`. Every selectable ID, URL, insight index,
target reference, and context reference is enumerated from that request. The
model selects opaque references; service code resolves them back to canonical
upstream objects. Terminal grounding and precedent stages therefore return only
their judgments and selected insight indices—they cannot rewrite document
targets or provenance. The schema controls wire shape; stage code
then maps it into canonical dataclasses and applies reusable deterministic checks
that JSON Schema cannot express: exact block/URL membership, quote containment,
number/operator/unit support, complete lineage, field ownership, source identity,
deduplication, and rollups. A schema-valid response therefore cannot bypass
provenance or semantic admission.

Claim-ledger schemas enumerate the complete canonical block IDs available in
their document chunk. This prevents a model from shortening a stable ID while
preserving exact membership validation; suffix and fuzzy ID repair remain
forbidden.

Fixed vocabulary units are resolved through bounded output groups over ordered
block-aligned chunks, always with the complete field catalog. This prevents
neighboring fields from independently claiming the same statement while
avoiding oversized responses. Quantitative interpretation is separate: the
complete document is partitioned into bounded batches of
non-overlapping statement units. Every unit ID must be returned exactly once,
and each batch retains its complete local source blocks while inheriting the
canonical document bindings through schema-enumerated context references.
Numeric syntax is copied from the unit; semantic provenance is resolved from
the selected unit or binding references. A numeric target may be assigned only to
a resolved field and a statement inside that field's canonical cited blocks.
Missing or invalid decisions receive one targeted retry; remaining failures stay
explicitly unresolved and are excluded from numeric target retrieval and
calibration rather than being silently repaired downstream. The independent
qualitative evidence workflow continues from the verified claim ledger.
Query generation and later reasoning consume the resulting canonical target.
Parallel calls are isolated by variable and `_parallel_map` preserves input order.

Only an explicit document/configuration mismatch or unresolved canonical claim
ledger halts the whole run. Numeric mapping uncertainty is local to its target or
source passage, source-adapter failures remain isolated to that lane, and terminal
reasoning failures degrade to their closed unknown/unrelated result.

Each step is one stage in `services/scout/stages/`.

The completed pipeline result is canonical. Downloading and importing it does
not rerun, repair, or mutate quantitative calibration. A materially newer
analysis contract requires a new Scout run, keeping one authoritative result per
run rather than creating alternate post-processed states.

For TPP runs Scout reads fixed definitions from `shared/attributes.yaml` and
binds them to document targets. For IPDP runs it dynamically extracts neutral
definitions and their checkable document claims together. Both become the same
resolved `Attribute` shape before retrieval, so downstream processing stays
symmetric.

## Evidence map

The web evidence map is a deterministic projection of a Scout result:

```text
evaluated field → canonical document target → evidence insight → cited source
```

It uses the canonical `Attribute.document_target` and its exact block IDs.

Rendered prompts identify source blocks with `[block:<id>]` markers. Model JSON
returns the complete bare ID inside the marker. A shared validator canonicalizes
the exactly wrapped legacy form, rejects shortened or invented references, and
never performs fuzzy matching. A fixed target without at least one valid source
block is retried once and then fails closed rather than entering downstream
reasoning as untraced document fact.
Relationship edges attach to that target. Focused mode displays a readable,
deterministic subset; **All evidence** maps every analyzed insight and cited
source for the selected field. `search_plan` remains the complete
request/skip/failure trace, including requests that produced no analyzed source.

## Config fields

Scout configs define query-generation guidance:

| Field | Notes |
|---|---|
| `sources` | Registered Searcher adapter keys enabled for this document type |
| `query_extraction_guidance` | Domain guidance injected into per-variable query generation |
| `queries_per_variable` | Number of focused queries generated for each shared attribute variable |
| `geographic_emphasis` | Optional emphasis groups, such as `global_south`, that add a separate query group |
| `geographic_queries_per_variable` | Additive geographic query budget per variable |
| `priority_institutions` | Optional authoritative institutions to name in neutral intents; never adapter/database keys |
| `modalities` | Optional platform technologies the query generator considers |
| `languages` | Optional languages for native-language retrieval intents |
| `drift_framing` | How Match relations interpret this document type |
| `evidence_framing` | How grounding interprets targets versus plan commitments |
| `quantitative_target_framing` | How document-stated numeric targets are interpreted before retrieval |
| `precedent_framing` | How absence or presence of prior work should be read |

`configs/evidence_methodology.yaml` contains only deterministic cohort-coverage
thresholds; product/document guidance remains in each triple-specific config.

## One LLM client

OpenAI (`shared/openai_client.py`) handles Scout's LLM stages and Searcher's web
adapter. Other Searcher adapters use their own non-LLM APIs and normalize into
the same `Finding` contract.

Scout uses OpenAI Structured Outputs rather than asking each stage to recover
free-form JSON. Provider refusals and incomplete responses fail closed at the
shared boundary; stage-specific retry/degradation behavior remains local to the
stage's responsibility.

Scout receives its reasoning client and a generic `SearchRuntime` separately.
The API composes that runtime once, including source credentials and optional
connector integrations, so Scout never knows which adapters are enabled.

## Stateless

Scout has no hidden session state: every run is defined by its explicit upload,
configuration, and injected capabilities. Live sources and model judgments may
change between otherwise identical runs.
