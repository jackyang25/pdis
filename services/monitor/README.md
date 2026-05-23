# Monitor

Derives web `Insight`s from uploaded documents + the 4 primitives. v0
backend only - no UI yet.

## Public contract

```python
from services.monitor import find_config, run_pipeline
from shared.openai_client import OpenAIClient

config = find_config("bmgf", "tpp", "vaccine")
client = OpenAIClient()
insights = run_pipeline(
    ["/path/to/doc1.docx"],
    config=config,
    openai_client=client,
    search_client=client,
    org="bmgf",
    source_type="tpp",
    intervention_class="vaccine",
    indication="rsv",
)
```

## What an `Insight` is

| Field | Type | Notes |
|---|---|---|
| `statement` | str | One atomic factual observation |
| `supporting_findings` | list[Finding] | Sources backing the statement |
| `query` | str | The search query that surfaced the supporting evidence |
| `org` / `source_type` / `intervention_class` / `indication` | str \| None | Stamped from inputs |

## Pipeline

1. **parse** - chunker parses each uploaded doc into blocks (no mapper).
2. **queries** - LLM extracts ~5 search queries grounded in doc content + 4 primitives + config guidance.
3. **search** - searcher runs each query in parallel; findings dedup by URL.
4. **insights** - LLM extracts atomic Insights from the deduped findings.

Each step is one stage in `services/monitor/stages/`.

## One LLM client

OpenAI (`shared/openai_client.py`) handles query extraction, web search
via searcher, and insight extraction.

Monitor's `run_pipeline` keeps separate `openai_client` and
`search_client` parameters because those are separate contracts, but the
same `OpenAIClient` satisfies both.

## What v0 does NOT do (deferred)

- **No comparison against doc Claims.** Benchmarker integration is a
  v1 layer that will compare Insights (from web) against Claims (from
  docs) and produce `Match` records.
- **No persistence.** Stateless; same input -> same output (mod LLM/web drift).

## Stateless

Same inputs -> same outputs. No persistence in the active path.
