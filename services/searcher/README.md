# Searcher

LLM-driven web search service. Returns atomic, source-attributed `Finding`s.

## Inputs and outputs

| | |
|---|---|
| Input | One free-text query + an injected `SearcherLLMClientProtocol` implementation |
| Output | `list[Finding]` - each finding is a source URL, page title, optional cited excerpt, original query, and retrieval timestamp |

Searcher does not use document headers or the four primitives. A query is not a document.

## Files

| File | Purpose |
|---|---|
| `models.py` | `Finding`, `SearcherLLMClientProtocol`, and `findings_to_dicts`. |
| `pipeline.py` | `run_pipeline(query, ...)` - orchestrates the single search stage. |
| `stages/searcher.py` | OpenAI web-search call and citation parser. |
| `requirements.txt` | No service-specific dependencies. |

## Public contract

```python
from services.searcher import Finding, run_pipeline
from shared.openai_client import OpenAIClient

llm = OpenAIClient()
findings: list[Finding] = run_pipeline(
    "recent FDA guidance on RSV vaccines",
    llm_client=llm,
)

for f in findings:
    print(f.url, "-", f.title)
    if f.excerpt:
        print(f.excerpt[:200])
```

## What a `Finding` is

| Field | Type | Notes |
|---|---|---|
| `url` | str | Source URL |
| `title` | str | Page title (or URL if title missing) |
| `query` | str | The original query that produced this finding |
| `retrieved_at` | datetime | UTC timestamp of the search |
| `excerpt` | str \| None | Cited text span from the model output when available; otherwise `None`. |
| `published_at` | datetime \| None | Only set when reliably known |

**Why excerpt is optional:** OpenAI's web_search response includes cited
URLs as annotations on the model output. When a cited text span is
available, we attach it as the excerpt. When it is not, the Finding is
still useful as source attribution.

## Architecture

One stage, one shape, one job. Mirrors the layout of other services
(`chunker`, `benchmarker`, `reviewer`) but intentionally lighter:

- **No `configs/`** - searcher has no natural per-domain keying.
- **Minimal API route and UI** - exposed as a debug surface for sanity-checking
  web search results.
- **No 4-primitive stamping** - those are document-centric; a freeform
  query is not a document.

## Backend

Uses OpenAI's Responses API `web_search` tool via
`shared/openai_client.py::OpenAIClient.search_web()`.

## Stateless

Same query -> same output (modulo LLM and web drift). No persistence.

## Dependencies

Uses `shared.openai_client.OpenAIClient` by dependency injection. Does not import from chunker, benchmarker, or reviewer.
