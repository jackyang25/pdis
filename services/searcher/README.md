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

report = run_pipeline(
    "recent RSV vaccine efficacy review",
    runtime=SearchRuntime(llm_client=OpenAIClient()),
    sources=("web", "pubmed"),
    condition="respiratory syncytial virus infection",
)
```

Direct callers default to `sources=("web",)`. The report carries the
deduplicated `findings` and one `outcomes` entry per native request, which is the
only place an empty lane stays distinguishable from a skipped or failed one.

`condition` and `intervention` are what a field-addressed source scopes its request by.
Omitted, each such adapter falls back to the intent's own scope, so a free-text
question becomes the value of a structured field and matches nothing. A caller with
a condition to state should state it.

`intervention` is the class; `product` is one named product. They are separate because
they do different work: the class scopes the request, and the product is added beside it
as a narrower one, so a name a registry files differently still returns the broader
result. Passing a product in place of a class loses that broader request.

`entities` are the named subjects a source may address its API by. A source declaring
`required_entity_types` plans nothing without one, because it has no subject to name,
so a caller passing none is limited to the sources that read prose. Scout takes these
from a parsed document; a free-text caller states them.

`population` and `outcome` are the remaining subject facets. A literature adapter asks
about one phrase per query and picks it in the order outcome, intervention, population,
falling back to the query text; the structured sources have no such field. Together with
`condition`, `intervention` and `entities` these are the whole of what a caller states,
and `tests/test_interface_parity.py` holds every contract field to being offered,
carried as lineage, or declined for a stated reason. Import registry metadata,
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

An anchor is one value, applied once. The other names a document shares are not
further anchors: a Boolean grammar takes the anchor alone, while a plain-text
grammar keeps them all as hints. A field-addressed source declares its anchor
field to `facet_groups`, so a query restating the intent's scope in its own words
narrows nothing and cannot consume one of that source's requests.

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
