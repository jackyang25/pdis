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
| `definition_mode` | `fixed` vocabulary or `dynamic` extraction provenance |
| `target_resolved` | Binding completed, including an intentionally absent target |
| `evidence_domain` | Closed source-applicability domain |
| `entities` | Explicit document-stated typed entities |
| `quantitative_targets` | Atomic numeric claims with one canonical field owner, one shared `NumericExpression`, immutable semantic IDs, exact provenance spans, roles, and the shared target/source semantic profile |
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
3. **resolve targets** - fixed TPP definitions are bound to the document's exact target, blocks, and explicitly stated entities; dynamic IPDP units arrive already bound. Both have the same canonical shape, including one closed evidence domain, with `definition_mode` preserving only their provider provenance. Fixed domains are authored in the shared vocabulary; dynamic domains are selected from the same enum.
4. **bind quantitative targets** - the model enumerates every independently calibratable numeric claim from the resolved field. Deterministic code verifies its exact quote, numeric token, direction, unit, role, and document blocks, then assigns its immutable target ID. This bundle becomes part of the canonical `Attribute` before retrieval.
5. **per-unit query intents** - LLM generates document-aware intents from the canonical definition and target across general, geographic, counterfactual, and precedent tracks. The general track must cover every verified quantitative target. Each intent carries both block lineage and the target IDs it was designed to cover.
6. **plan + search** - Scout converts units to Searcher's neutral `RetrievalIntent`. The generic controller compares the unit's evidence domain and document-stated entity types with each enabled adapter's declared capabilities. Applicable adapters receive the complete bundle and independently compile source-native requests; non-applicable adapters emit explicit traced skips without connector calls. The controller centrally attaches target lineage to every compiled request and verifies complete intent coverage, so source adapters do not duplicate this policy. It then executes fair per-source queues with adapter-owned rate/concurrency policy. `search_plan` retains every native request or skip, its exact input intent IDs/texts, applicability reason, status, document blocks, quantitative target IDs, track, result count, and source URLs. URL dedupe preserves every retrieval path and the exact lanes supplying title, excerpt, and publication date.
7. **deterministic projections** - typed development and safety records are grouped into a development landscape and safety-signal view. Missing fields remain missing; no LLM or source-specific parsing runs in Scout.
8. **per-variable insights** - LLM extracts atomic Insights in count- and payload-bounded batches from evidence-role Findings only. Reference-only catalog/entity records cannot influence reasoning. A deterministic pass merges duplicate facts across batch boundaries and assigns stable IDs. Insights retain which target-specific requests retrieved their sources, explicitly as coverage rather than evidence support.
9. **classify** - LLM classifies every Insight against a bounded, block-annotated context for that variable and returns validated document block IDs.
10. **evidence** - LLM assesses grounding and selects only the exact insight indices it used; the service resolves those to stable IDs and sources without allowing the canonical target to drift.
11. **quantitative calibration** - calibration consumes the already verified target bundle; it never re-extracts targets. Repeated semantic claims merge exact provenance spans, while threshold, optimal, population-specific, and time-specific targets remain separate ledgers. Document targets and source measurements share one syntax-only `NumericExpression` (`point_estimate`, `range`, `bound`, `confidence_interval`, `count`, `rate`, `other`, or `unknown`) and one seven-slot semantic profile (`measure`, `endpoint`, `intervention`, `population`, `regimen`, `time_horizon`, `statistic`) with explicit `specified`, `not_specified`, `unknown`, and `other` states. For each deduplicated source-owned passage, the model returns one `measurements_found`, `no_relevant_measurement`, or `uncertain` disposition and zero or more complete exact-quoted measurements; there is no regex-produced number-fragment fan-out. Code verifies the source ID, exact quote, every expression number/operator/unit, enums, URL, source identity, and deduplication. Only comparable atomic scalars (`point_estimate`, `count`, or `rate`) in the target unit enter minimum/maximum/mean/median/quartiles/observed standard deviation, target/ambition percentiles, and the literal target-meeting share. Contextual and incompatible measurements remain traceable without distorting statistics. These outputs describe the selected cohort only and are never confidence intervals or forecast probabilities.
12. **precedent** - LLM separately classifies coverage (direct/adjacent/none/unknown) and outcome (favorable/mixed/unfavorable/unknown), with independent supporting insight IDs and canonical document blocks.

Long documents are not truncated from the end. Fixed vocabulary units receive a
relevance-selected context with neighboring blocks and a document-wide safety
net only while their canonical binding is resolved. After that boundary, raw
bound blocks are reserved for exact fact validation; query generation and
document-aware reasoning receive the canonical target with those block markers.
Parallel calls are isolated by variable and `_parallel_map` preserves input order.

Each step is one stage in `services/scout/stages/`.

`POST /api/scout/recalibrate` is a retrieval-free repair path for a current
portable result. It deterministically revalidates the saved canonical targets
against their saved blocks, reuses only cited Insights, and returns replacement
ledgers; it cannot fetch evidence, synthesize new Insights, or extract a new
target set.

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
| `conformity_framing` | How quantitative values are selected and compared |
| `precedent_framing` | How absence or presence of prior work should be read |

`configs/evidence_methodology.yaml` contains only deterministic cohort-coverage
thresholds; product/document guidance remains in each triple-specific config.

## One LLM client

OpenAI (`shared/openai_client.py`) handles Scout's LLM stages and Searcher's web
adapter. Other Searcher adapters use their own non-LLM APIs and normalize into
the same `Finding` contract.

Scout receives its reasoning client and a generic `SearchRuntime` separately.
The API composes that runtime once, including source credentials and optional
connector integrations, so Scout never knows which adapters are enabled.

## Stateless

Scout has no hidden session state: every run is defined by its explicit upload,
configuration, and injected capabilities. Live sources and model judgments may
change between otherwise identical runs.
