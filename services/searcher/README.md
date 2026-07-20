# Searcher

Pluggable retrieval service. Source adapters turn neutral retrieval intent into
native requests and normalize every response to source-attributed `Finding`s.

## Inputs and outputs

| | |
|---|---|
| Input | A free-text query, or canonical `RetrievalIntent[]` from an upstream service, plus injected runtime capabilities |
| Output | `list[Finding]` - each finding is a source URL, page title, optional excerpt, original query, retrieval timestamp, and source modality |

Free-query Searcher does not use document headers or the four primitives. Scout
supplies indication/intervention context and document lineage through the
neutral `RetrievalIntent` contract rather than exposing its own models.

## Files

| File | Purpose |
|---|---|
| `models.py` | Stable intent, request, outcome, source metadata, and `Finding` contracts. |
| `controller.py` | Source-agnostic planning, validation, concurrency, and failure isolation. |
| `sources/` | One adapter per source plus the explicit engineering registry. |
| `connectors/` | Injected integration clients, currently the authenticated ToolUniverse HTTP boundary. |
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
| `evidence_role` | `evidence` \| `reference` | Reference-only catalog/entity records are retained for deterministic projections but excluded from Scout evidence reasoning. |
| `development_records` | list[DevelopmentRecord] | Explicit normalized program, sponsor, phase, status, and record identity fields. |
| `safety_records` | list[SafetyRecord] | Explicit warning/report/recall observations with source qualifications; never causal inference. |
| `source_labels` | dict[str, str] | Adapter-owned display metadata; clients do not mirror source names |
| `source_attributions` | dict[str, SourceAttribution] | Optional adapter-owned public attribution notices, retained through deduplication and saved results |
| `retrieval_paths` | list[RetrievalPath] | Exact query, source, connector, and operation path for every retrieval |

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
- **Lossless planning contract** - every adapter sees the complete neutral
  bundle. It may consolidate intents into fewer native requests, but each
  request records the exact intent IDs and original texts it compiled; the
  controller rejects silent omissions.
- **Controller-owned execution** - orchestration has no source `if/elif`
  branch. Fair source queues enforce the global cap and per-adapter concurrency
  without letting a slow lane occupy another lane's runnable capacity.
- **Deterministic applicability** - adapters declare supported evidence domains
  and any required entity types. The controller compares those capabilities to
  the canonical unit metadata, records non-applicable lanes as traced skips,
  and never calls their connector. Free-query Searcher remains explicitly
  source-selected and bypasses document-field applicability.
- **One closed vocabulary** - evidence domains and entity types are owned by
  Searcher's public neutral contract and reused by Scout and adapter metadata;
  misspelled capabilities fail during construction.
- **Minimal API route and UI** - exposed as a debug surface for sanity-checking
  retrieval; both discover registered source metadata dynamically.
- **No 4-primitive stamping** - those are document-centric; a freeform
  query is not a document.

## Backends

- `web` - OpenAI Responses API `web_search` via `OpenAIClient.search_web()`.
- `pubmed` - NCBI PubMed abstracts plus PMC full text when open-access text is available.
- `clinicaltrials` - structured ClinicalTrials.gov condition/intervention candidate
  retrieval, followed by deterministic field-query ranking.
- `ctis` - structured EU Clinical Trials Information System retrieval through
  ToolUniverse, followed by deterministic field-query ranking.
- `isrctn` - structured ISRCTN condition/intervention retrieval through
  ToolUniverse, followed by deterministic field-query ranking.
- `semantic_scholar` - plain-text relevance search through the optional, injected
  ToolUniverse HTTP connector. It remains off by default on the free-query
  Searcher surface; Scout configs opt into it explicitly. Its registered
  execution policy spaces request starts by 1.1 seconds to remain below the
  issued 1 RPS cumulative limit.
- `open_targets` - target-disease evidence for drug biological fields with a
  document-stated gene or protein target.
- `chembl` - compound and molecular-target records for document-stated drug,
  compound, protein, gene, antigen, or biomarker entities in biological fields.
- `uniprot` - protein records for document-stated protein, gene, antigen, or
  biomarker entities in biological fields.
- `fda` - FDA regulatory retrieval through ToolUniverse. The adapter chooses
  FDA drug labels for drugs/vaccines and 510(k) records for devices/diagnostics.
- `fda_safety` - named-product safety retrieval through ToolUniverse. Drug and
  vaccine entities use official label warnings and FAERS report counts; device
  entities use MAUDE reports and device recalls. Every surveillance record is
  explicitly qualified as non-causal; raw FAERS counts and individual MAUDE
  reports are reference-role records excluded from Scout evidence reasoning.

Native request counts intentionally differ by lane. Web executes each generated
variant. PubMed compiles all variants in a track into one Boolean query.
Semantic Scholar creates one focused plain-text query per track using terms from
every variant because its relevance endpoint has no special query syntax.
ClinicalTrials.gov, CTIS, ISRCTN, and FDA issue one structured candidate request
per field and rank the returned records deterministically against every neutral
query carried by that request. Rate limits affect when requests run, never which
neutral intents are retained.
Specialized sources may be intentionally skipped before native planning. Their
skip trace still carries every neutral intent ID/text and document block, so
"not applicable" is distinguishable from an empty search and a source failure.

`run_pipeline()` defaults to `sources=("web",)` for direct library callers.
The API and debug UI discover the registry and select adapters marked
`default_enabled`; Scout uses the explicit source set in its config.
`NCBI_API_KEY` is optional and only increases NCBI rate limits.

## Adding a ToolUniverse-backed or direct source

1. Add an adapter under `sources/` implementing `SourceAdapter.plan()` and
   `SourceAdapter.search()`. It receives neutral context (`topic`, description,
   indication, intervention class, document-aware query intents and tracks).
2. Register it once in `sources/__init__.py` with its key, label, and worker limit.
3. Inject its connector through `SearchRuntime.integrations`; do not import it
   into Scout or shared domain code.
4. Map every received intent into one or more native requests and populate its
   intent IDs/input texts. Planning fails if any intent disappears silently.
5. Opt selected Scout configs into the new key through `sources: [...]`.

No Scout pipeline, API allowlist, Ask logic, or source-label UI branch changes
are required. A ToolUniverse adapter declares a static operation allowlist and
selects deterministically within it; do not delegate source or tool selection to
ToolUniverse's agent/tool-finder layer. Every output normalizes to `Finding`,
while `SearchTrace` and `RetrievalPath` retain the connector and exact operation.

PDIS uses ToolUniverse's official HTTP boundary. The full SDK runs separately;
`api/deps.py` creates a minimal `ToolUniverseHTTPConnector` from an explicit
`TOOLUNIVERSE_BASE_URL` locally or Render-injected private host/port values.
`TOOLUNIVERSE_API_TOKEN` authenticates that connection. Database-specific
credentials belong on the ToolUniverse server.

## Stateless

Same query -> same output (modulo LLM and web drift). No persistence.

## Dependencies

Dependencies are adapter-owned and injected through `SearchRuntime`: the web
adapter uses `OpenAIClient`, PubMed uses NCBI, and ToolUniverse-backed adapters
reuse `integrations["tooluniverse"]`. Searcher does not import from chunker,
reviewer, or scout. The controller enforces adapter request spacing,
adapter-owned worker limits, and one global worker cap. Provider endpoints
invoked multiple times inside one adapter request retain their finer throttle
inside that adapter's stage.
