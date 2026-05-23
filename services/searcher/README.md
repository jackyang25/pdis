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
| `stages/searcher.py` | Anthropic web-search call and citation parser. |
| `requirements.txt` | Anthropic SDK dependency. |

## Public contract

```python
from services.searcher import Finding, run_pipeline
from shared.anthropic_client import AnthropicClient

llm = AnthropicClient()
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
| `excerpt` | str \| None | Cited passage from the source page when the model quoted it; otherwise `None`. URL still appears in the list either way. |
| `published_at` | datetime \| None | Only set when reliably known |

**Why excerpt is optional:** searcher returns every URL the web_search
backend surfaced, not just the ones the model decided to cite. When the
model quoted a source in its response, we attach that quoted text as
the excerpt. When it didn't (or didn't write a text response at all),
the URL still appears with `excerpt=None` - consumers can fetch the page
themselves if they need content.

## Architecture

One stage, one shape, one job. Mirrors the layout of other services
(`chunker`, `benchmarker`, `reviewer`) but intentionally lighter:

- **No `configs/`** - searcher has no natural per-domain keying.
- **Minimal API route and UI** - exposed as a debug surface for sanity-checking
  web search results.
- **No 4-primitive stamping** - those are document-centric; a freeform
  query is not a document.

## Backend

Uses Anthropic's native `web_search` server tool via
`shared/anthropic_client.py::AnthropicClient.search_web()`.

**Why Anthropic and not the shared OpenAI client?** Searcher is the
only service today that needs web search. Anthropic's native web_search
returns cited passages from source pages (used as `Finding.excerpt`),
which is exactly the primitive we want. Other services stay on OpenAI
via `shared/openai_client.py`. This is a deliberate per-service provider
choice via dependency injection, not a global migration.

## Stateless

Same query -> same output (modulo LLM and web drift). No persistence.

## Dependencies

Uses `shared.anthropic_client.AnthropicClient` by dependency injection. Does not import from chunker, benchmarker, or reviewer.
