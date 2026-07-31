# Searcher

Translate neutral retrieval intent into source-native requests and findings.

## Background

Searcher is the external-evidence boundary. Its controller is source-agnostic;
adapters own query grammar, applicability, credentials, rate limits, execution,
and response normalization.

## Usage

```python
from services.searcher import SearchRuntime, run_pipeline
from shared.openai_client import OpenAIClient

findings = run_pipeline(
    "recent RSV vaccine efficacy review",
    runtime=SearchRuntime(llm_client=OpenAIClient()),
    sources=("web", "pubmed"),
)
```

Direct callers default to `sources=("web",)`. Import registry metadata,
planning and execution helpers, connectors, models, and serializers from
`services.searcher`.

## Contract

| Direction | Value |
|---|---|
| Input | Free text or retrieval intents, source keys, and injected runtime capabilities |
| Output | Ordered search outcomes or URL-deduplicated findings with retrieval lineage |

Unknown keys fail explicitly, non-applicable lanes emit traced skips, and
adapter failures remain isolated. URL deduplication preserves every query,
source lane, and retrieval path. Web citation context is not treated as a
verbatim source passage.

A query intent carries its natural-language text and the facets its author stated
(`condition`, `intervention`, `population`, `outcome`). An adapter selects
whichever its API accepts and reads a blank facet as the intent's own scope. No
adapter recovers a facet by re-parsing the text.

Facets carry roles. `condition` anchors every request for one intent, one subject
phrase is what a single query asks, and the rest qualify meaning. Whether a
qualifier enters a request depends on that grammar: a Boolean conjunct is another
coincidence a record must satisfy, while a plain-text term only sharpens ranking.
Narrowed requests are added to the intent-scope request rather than replacing it,
and a source bounds its own fan-out with `max_requests_per_intent`.

Adapters may compact several neutral intents into one native request, but the
native query must retain their document-specific concepts and the request must
carry every input intent ID and text. A field-addressed source varies its request
by the facets it uses and collapses identical native requests, so request count
follows what its grammar expresses losslessly rather than how many queries arrived.

## Sources

| Boundary | Sources |
|---|---|
| Direct | OpenAI web search, PubMed/PMC, ClinicalTrials.gov |
| ToolUniverse literature and trials | CTIS, ISRCTN, Semantic Scholar |
| ToolUniverse biological and regulatory | Open Targets, ChEMBL, UniProt, FDA, FDA Safety |

Specialized sources declare supported evidence domains and entity requirements.
Reference-only catalog records remain available for deterministic views but do
not enter Scout evidence reasoning.

## Development

Add a source by implementing and registering one adapter, injecting any optional
connector through `SearchRuntime.integrations`, preserving input lineage, and
enabling its key in Scout config. ToolUniverse is a connector, not an autonomous
router or generic evidence lane.
