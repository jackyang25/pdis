# Scout

Pressure-tests document targets against live evidence. Scout derives canonical
document-bound fields, traced retrieval, atomic evidence insights, target
relationships, grounding, quantitative alignment, and precedent signals.

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
2. **resolve targets** - fixed TPP definitions are bound to the document's exact target, blocks, and explicitly stated entities; dynamic IPDP units arrive already bound. Both have the same canonical shape, including one closed evidence domain, with `definition_mode` preserving only their provider provenance. Fixed domains are authored in the shared vocabulary; dynamic domains are selected from the same enum.
3. **per-unit query intents** - LLM generates document-aware intents from the canonical definition and target across general, geographic, counterfactual, and precedent tracks.
4. **plan + search** - Scout converts units to Searcher's neutral `RetrievalIntent`. The generic controller compares the unit's evidence domain and document-stated entity types with each enabled adapter's declared capabilities. Applicable adapters receive the complete bundle and independently compile source-native requests; non-applicable adapters emit explicit traced skips without connector calls. The controller verifies complete intent coverage, then executes fair per-source queues with adapter-owned rate/concurrency policy. `search_plan` retains every native request or skip, its exact input intent IDs/texts, applicability reason, status, document blocks, track, result count, and source URLs. URL dedupe preserves every retrieval path and the exact lanes supplying title, excerpt, and publication date.
5. **per-variable insights** - LLM extracts atomic Insights in count- and payload-bounded batches. A deterministic pass merges duplicate facts across batch boundaries and assigns stable IDs.
6. **classify** - LLM classifies every Insight against a bounded, block-annotated context for that variable and returns validated document block IDs.
7. **evidence** - LLM assesses grounding and selects only the exact insight indices it used; the service resolves those to stable IDs and sources without allowing the canonical target to drift.
8. **conformity** - quantitative values are extracted from the canonical target; every measurement URL must belong to its selected insight and retain the same unit as the target (no silent conversion). The LLM separately labels evidence form, development phase, and source-record type; deterministic methodology config supplies weights.
9. **precedent** - LLM separately classifies coverage (direct/adjacent/none/unknown) and outcome (favorable/mixed/unfavorable/unknown), with independent supporting insight IDs and canonical document blocks.

Long documents are not truncated from the end. Vocabulary units receive a
relevance-selected context with neighboring blocks and a document-wide safety
net; extracted units additionally seed their originating blocks. Parallel calls
are isolated by variable and `_parallel_map` preserves input order.

Each step is one stage in `services/scout/stages/`.

For TPP runs Scout reads fixed definitions from `shared/attributes.yaml` and
binds them to document targets. For IPDP runs it dynamically extracts neutral
definitions and their checkable document claims together. Both become the same
resolved `Attribute` shape before retrieval, so downstream processing stays
symmetric.

## Evidence map

The web evidence map is a bounded, deterministic projection of a Scout result:

```text
evaluated field → canonical document target → evidence insight → cited source
```

It uses the canonical `Attribute.document_target` and its exact block IDs.
Relationship edges attach to that target. The map intentionally omits most
retrieval requests and displays a readable subset; `search_plan` remains the
complete request/skip/failure trace and the Fields view retains all analyzed
evidence.

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

`configs/evidence_methodology.yaml` contains only cross-domain quantitative
weighting policy; product/document guidance remains in each triple-specific config.

## One LLM client

OpenAI (`shared/openai_client.py`) handles Scout's LLM stages and Searcher's web
adapter. Other Searcher adapters use their own non-LLM APIs and normalize into
the same `Finding` contract.

Scout receives its reasoning client and a generic `SearchRuntime` separately.
The API composes that runtime once, including source credentials and optional
connector integrations, so Scout never knows which adapters are enabled.

## Stateless

Same inputs -> same outputs. No persistence in the active path.
