# Searcher

Pluggable retrieval service. Source adapters turn neutral retrieval intent into
native requests and normalize every response to source-attributed `Finding`s.

## Inputs and outputs

| | |
|---|---|
| Input | One free-text query + an injected `SearcherLLMClientProtocol` implementation |
| Output | `list[Finding]` - each finding is a source URL, page title, optional excerpt, original query, retrieval timestamp, and source modality |

Searcher does not use document headers or the four primitives. A query is not a document.

## Files

| File | Purpose |
|---|---|
| `models.py` | Stable intent, request, outcome, source metadata, and `Finding` contracts. |
| `controller.py` | Source-agnostic planning, validation, concurrency, and failure isolation. |
| `sources/` | One adapter per source plus the explicit engineering registry. |
| `pipeline.py` | Free-query Searcher facade over the same controller. |
| `stages/searcher.py` | OpenAI web-search call and citation parser. |
| `stages/pubmed.py` | Direct NCBI PubMed/PMC retrieval. |
| `requirements.txt` | No service-specific dependencies. |

## Public contract

```python
from services.searcher import Finding, SearchRuntime, run_pipeline
from shared.openai_client import OpenAIClient

llm = OpenAIClient()
findings: list[Finding] = run_pipeline(
    "recent FDA guidance on RSV vaccines",
    runtime=SearchRuntime(llm_client=llm),
)

literature_and_web = run_pipeline(
    "recent RSV vaccine efficacy systematic review",
    runtime=SearchRuntime(llm_client=llm),
    sources=("web", "pubmed"),
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
| `source` / `source_lanes` | str / list[str] | Adapter key and every lane that retrieved a merged URL |
| `source_labels` | dict[str, str] | Adapter-owned display metadata; clients do not mirror source names |
| `retrieval_paths` | list[RetrievalPath] | Exact query + source path for every retrieval |

**Why excerpt is optional:** OpenAI's web_search response includes cited
URLs as annotations on the model output. When a cited text span is
available, we attach it as the excerpt. When it is not, the Finding is
still useful as source attribution.

## Architecture

The stable boundary is intent/request/outcome, not a fixed backend list:

- **Static engineering registry** - adapters and credentials are capabilities,
  so registration is explicit code in `sources/__init__.py`.
- **Dynamic product selection** - callers choose registered source keys; Scout
  stores those keys in its per-document-type config.
- **Adapter-owned behavior** - native query grammar, concurrency, dependencies,
  and response normalization live with the source.
- **Controller-owned execution** - orchestration has no source `if/elif` branch.
- **Minimal API route and UI** - exposed as a debug surface for sanity-checking
  retrieval; both discover registered source metadata dynamically.
- **No 4-primitive stamping** - those are document-centric; a freeform
  query is not a document.

## Backends

- `web` - OpenAI Responses API `web_search` via `OpenAIClient.search_web()`.
- `pubmed` - NCBI PubMed abstracts plus PMC full text when open-access text is available.
- `clinicaltrials` - structured ClinicalTrials.gov condition/intervention/topic retrieval.

`run_pipeline()` defaults to `sources=("web",)` for direct library callers.
The API and debug UI discover the registry and select adapters marked
`default_enabled`; Scout uses the explicit source set in its config.
`NCBI_API_KEY` is optional and only increases NCBI rate limits.

## Adding ToolUniverse or another source

1. Add an adapter under `sources/` implementing `SourceAdapter.plan()` and
   `SourceAdapter.search()`. It receives neutral context (`topic`, description,
   indication, intervention class, document-aware query intents and tracks).
2. Register it once in `sources/__init__.py` with its key, label, and worker limit.
3. Inject its connector through `SearchRuntime.integrations`; do not import it
   into Scout or shared domain code.
4. Opt selected Scout configs into the new key through `sources: [...]`.

No Scout pipeline, API allowlist, result schema, Ask logic, or source-label UI
branch changes are required. A ToolUniverse adapter may choose among its own
tools dynamically, but that choice remains inside the adapter and every output
must normalize to `Finding` with exact retrieval provenance.

## Stateless

Same query -> same output (modulo LLM and web drift). No persistence.

## Dependencies

Dependencies are adapter-owned and injected through `SearchRuntime`: the web
adapter uses `OpenAIClient`, PubMed uses NCBI, and future connectors such as
ToolUniverse use `integrations`. Searcher does not import from chunker,
reviewer, or scout.
