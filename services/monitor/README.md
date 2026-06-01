# Monitor

Derives doc-aware `Match` records from uploaded documents + the 4 primitives.

## Public contract

```python
from services.monitor import find_config, matches_to_dicts, run_pipeline
from shared.openai_client import OpenAIClient

config = find_config("bmgf", "tpp", "vaccine")
client = OpenAIClient()
matches = run_pipeline(
    ["/path/to/doc1.docx"],
    config=config,
    openai_client=client,
    search_client=client,
    org="bmgf",
    source_type="tpp",
    intervention_class="vaccine",
    indication="rsv",
)
print(matches_to_dicts(matches)[:3])
```

## What an `Insight` is

| Field | Type | Notes |
|---|---|---|
| `statement` | str | One atomic factual observation |
| `supporting_findings` | list[Finding] | Sources backing the statement |
| `query` | str | The search query that surfaced the supporting evidence |
| `org` / `source_type` / `intervention_class` / `indication` | str \| None | Stamped from inputs |
| `section_label` | str \| None | Chunker section/variable label this Insight relates to |

## What a `Match` is

| Field | Type | Notes |
|---|---|---|
| `insight` | Insight | The pure web evidence being compared |
| `relation` | str | One of `contradicts`, `extends`, `confirms`, `unrelated` |
| `reason` | str | Short explanation of how the Insight relates to the uploaded document |

`Match` is the doc-aware primitive monitor emits. `Insight` stays useful
as pure web evidence underneath it.

## Pipeline

1. **parse + label** - chunker parses each uploaded doc and labels blocks by section.
2. **per-section queries** - LLM extracts focused web queries for each non-metadata section.
3. **search** - searcher runs all section queries in parallel; findings are grouped back by section.
4. **per-section insights** - LLM extracts atomic Insights per section and stamps `section_label`.
5. **classify** - LLM classifies each Insight against the uploaded doc as `contradicts`, `extends`, `confirms`, or `unrelated`.

Each step is one stage in `services/monitor/stages/`.

Monitor reuses chunker's section labeling to scope web searches to the
document variables that matter. This avoids truncating the whole document
into one query prompt and lets downstream views answer which section is
drifting.

## One LLM client

OpenAI (`shared/openai_client.py`) handles query extraction, web search
via searcher, insight extraction, and drift classification.

Monitor's `run_pipeline` keeps separate `openai_client` and
`search_client` parameters because those are separate contracts, but the
same `OpenAIClient` satisfies both.

## What v0 does NOT do (deferred)

- **No comparison against doc Claims.** Benchmarker integration is a
  v1 layer that will enrich Matches with `claim_id` pointers to the
  specific doc Claims involved in the comparison.
- **No persistence.** Stateless; same input -> same output (mod LLM/web drift).

## Stateless

Same inputs -> same outputs. No persistence in the active path.
