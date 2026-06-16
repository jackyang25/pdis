# Monitor

Derives doc-aware `Match` records and per-variable `EvidenceAssessment`
records from uploaded documents + the 4 primitives.

## Public contract

```python
from services.monitor import assessments_to_dicts, find_config, matches_to_dicts, run_pipeline
from shared.openai_client import OpenAIClient

config = find_config("bmgf", "tpp", "vaccine")
client = OpenAIClient()
result = run_pipeline(
    ["/path/to/doc1.docx"],
    config=config,
    openai_client=client,
    search_client=client,
    org="bmgf",
    source_type="tpp",
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
| `statement` | str | One atomic factual observation |
| `supporting_findings` | list[Finding] | Sources backing the statement |
| `query` | str | The search query that surfaced the supporting evidence |
| `org` / `source_type` / `intervention_class` / `indication` | str \| None | Stamped from inputs |
| `attribute_ref` | str \| None | Shared TPP attribute variable this Insight relates to |

## What a `Match` is

| Field | Type | Notes |
|---|---|---|
| `insight` | Insight | The pure web evidence being compared |
| `relation` | str | One of `contradicts`, `extends`, `confirms`, `unrelated` |
| `reason` | str | Short explanation of how the Insight relates to the uploaded document |

`Match` is the doc-aware primitive monitor emits. `Insight` stays useful
as pure web evidence underneath it.

## What an `EvidenceAssessment` is

| Field | Type | Notes |
|---|---|---|
| `attribute_ref` | str | Shared TPP attribute variable |
| `strength` | str | One of `well_grounded`, `partial`, `thin`, `unsupported`, `unknown` |
| `basis` | list[str] | Supported evidence bases: `standard_of_care`, `modeling`, `study_strength`, `regulatory_precedent` |
| `reason` | str | One-sentence explanation |
| `supporting_findings` | list[Finding] | Deduped sources backing the assessment |

## Pipeline

1. **parse** - chunker parses each uploaded doc without section mapping.
2. **per-variable queries** - LLM extracts focused web queries for each shared attribute variable across content, source, and language axes, then adds any configured geographic-emphasis query budget.
3. **search** - searcher runs all variable queries in parallel against web and PubMed/PMC literature backends; findings are grouped back by attribute and deduped by URL.
4. **per-variable insights** - LLM extracts atomic Insights per attribute across all findings, batching when needed, and stamps `attribute_ref`.
5. **classify** - LLM classifies every Insight against the uploaded doc as `contradicts`, `extends`, `confirms`, or `unrelated`, batching when needed.
6. **evidence** - LLM assesses the weight of evidence for each attribute variable.

Each step is one stage in `services/monitor/stages/`.

Monitor reads the variable list from `shared/attributes.yaml` for the
run's intervention class. It parses the uploaded document for classifier
context, then searches per attribute variable so downstream views can
show which TPP variable is drifting.

## Config fields

Monitor configs define query-generation guidance:

| Field | Notes |
|---|---|
| `query_extraction_guidance` | Domain guidance injected into per-variable query generation |
| `queries_per_variable` | Number of focused queries generated for each shared attribute variable |
| `geographic_emphasis` | Optional emphasis groups, such as `global_south`, that add a separate query group |
| `geographic_queries_per_variable` | Additive geographic query budget per variable |
| `priority_sources` | Optional authoritative sources to name in generated queries |
| `modalities` | Optional platform technologies the query generator considers |
| `languages` | Optional query languages for native-language web searches |

## One LLM client

OpenAI (`shared/openai_client.py`) handles query extraction, web search
via searcher, insight extraction, drift classification, and evidence
assessment. Searcher also unions NCBI PubMed/PMC literature findings for
monitor runs.

Monitor's `run_pipeline` keeps separate `openai_client` and
`search_client` parameters because those are separate contracts, but the
same `OpenAIClient` satisfies both.

## Stateless

Same inputs -> same outputs. No persistence in the active path.
