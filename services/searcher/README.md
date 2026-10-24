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
only place an empty lane stays distinguishable from a skipped or failed one. A failed
outcome carries `error_code` beside the provider's message; a complete one may carry
`provider_query` (what the provider says it ran, e.g. PubMed's query translation) and
`warnings` (a phrase it searched without, a page it could not return).

`condition` and `intervention` are what a field-addressed source scopes its request by.
Omitted, each such adapter falls back to the intent's own scope, so a free-text
question becomes the value of a structured field and matches nothing. A caller with
a condition to state should state it.

`intervention` is the class; `product` is one named product. They are separate because
they do different work: the class scopes the request, and the product is added beside it
as a narrower one, so a name a registry files differently still returns the broader
result. Passing a product in place of a class loses that broader request.

A date bound is stated on the intent, not written into the query. An index reads a
year as a term to match, so `2026` in a query finds records that mention it rather
than records published in it; `published_since` reaches a source's own date parameter
instead. A source declares `honors_date_bound` when it can apply the bound at the
provider, which changes what gets ranked; the rest are filtered after retrieval, which
only changes what survives. The caller's own filter stays as the backstop for both.

Dates keep the precision the provider stated. `published_at` is the first day the
date allows and `published_precision` is `day`, `month` or `year`; a caller applying
a lower bound uses `Finding.published_before`, which compares the latest day the
date allows, so a paper dated "2024" is not dropped by a window opening in June 2024.
A registry record is dated by when it was first posted (ClinicalTrials.gov's
`studyFirstPostDate`), never by its last edit. CTIS and ISRCTN search results state
no publication date, so their findings carry none and a window admits them.

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
| Output | Ordered search outcomes or record-deduplicated findings with retrieval lineage |

Unknown keys fail explicitly, non-applicable lanes emit traced skips, and
adapter failures remain isolated. Web citation context is not treated as a
verbatim source passage.

A finding's identity is its record, not its URL. Adapters set `record_key`
(`<lane>:<provider id>`, e.g. `pubmed:39746212`, `fda_safety:faers:<product>:<term>`)
and `identifiers` by scheme (`doi`, `pmid`, `pmcid`, `nct`, `euct`, `eudract`,
`isrctn`, `setid`, `spl_id`, `k_number`, `chembl`) from the provider's own fields; a
value that does not match its scheme's syntax ("Nil known") is dropped. `url` is where
a reader checks the record, and several records may share a page. `dedupe_findings`
merges findings with one `record_key`, or one cross-lane identifier (DOI, PMID, PMCID,
trial numbers) - so one paper from PubMed and Europe PMC is one finding listing both
lanes - and a web finding joins the record on the page it cites. Every query, lane
and retrieval path survives a merge. A record with no stable provider identity is not
kept: a URL invented for it (a fragment, a row position, the API's documentation page)
used to merge distinct records or misdirect a reader.

`excerpt_kind` says what an excerpt is: `passage` (the source's own words),
`structured_fields` (this service's labels around provider values) or `generated`
(model-written: the web lane, a Semantic Scholar TLDR). A structured excerpt renders
a record's fields in declared order, so one record reads the same whichever request
returned it.

A request asks for the number of records it keeps (`SourceSpec.max_results`) and
keeps them in the provider's order. Lanes used to ask for 50 or 100 and keep the top
10 or 20 by counting query words in the record's flattened JSON; that decided which
records existed by substring matches over field names and boilerplate.

Every provider call goes through `transport.py`: transient failures (429, 502, 503,
504, a reset connection, a timeout) are retried with jittered backoff or the
provider's `Retry-After`, within one total deadline, and failures raise
`RetrievalError` with a code and the provider's own message, secrets removed. Calls
are paced per `SourceSpec.rate_group` - `fda` and `fda_safety` share openFDA's - and
per call rather than per request, since WHO reads a page per result and PubMed
fetches after searching. Within a run, identical native calls are made once
(`SearchRuntime.calls`); each request still yields its own outcome and lineage. The
transport prefers IPv4 for the connections it opens and leaves the process's name
resolution alone. The User-Agent names the product, adding a contact only when
`SearchRuntime.contact_email` is configured.

A query intent carries its natural-language text and the facets its author stated
(`condition`, `intervention`, `population`, `outcome`). An adapter selects
whichever its API accepts and reads a blank facet as the intent's own scope. No
adapter recovers a facet by re-parsing the text.

Facets carry roles. `condition` anchors every request for one intent, one subject
phrase is what a single query asks, and the rest qualify meaning. Whether a
qualifier enters a request depends on that grammar: a Boolean conjunct is another
coincidence a record must satisfy, while a plain-text term only sharpens ranking.
Narrowed requests are added to the intent-scope request rather than replacing it,
and a source bounds its own fan-out with `max_requests_per_intent`, counted over every
request it plans - region twins included - by `planned_variants`.

An anchor is one value, applied once. The other names a document shares are not
further anchors: a Boolean grammar takes the anchor alone, while a plain-text
grammar keeps them all as hints. A field-addressed source declares its anchor
field to `facet_groups`, so a query restating the intent's scope in its own words
narrows nothing and cannot consume one of that source's requests. A source whose only
field is its anchor (CTIS, WHO, FDA) plans one request per intent directly.

PubMed and Europe PMC both compile `anchor AND (subject OR subject ...)`, because both
AND bare words. The anchor is never quoted: a quoted phrase turns off PubMed's
Automatic Term Mapping, and the quoted condition "respiratory syncytial virus
infection" returned 2 records live where the unquoted one, mapped to its MeSH heading,
returned 33. PubMed subjects stay quoted, since PubMed searches an unindexed quoted
phrase as its words and says so on the outcome; Europe PMC subjects are grouped words,
because Europe PMC searches a quoted phrase exactly with no fallback. A free-text
intent is asked once - its anchor is its own text, which used to be repeated as its
subject. Semantic Scholar, which has no Boolean grammar, keeps the plain-text compiler.

Adapters may compact several neutral intents into one native request, but the
native query must retain their document-specific concepts and the request must
carry every input intent ID and text. A field-addressed source varies its request
by the facets it uses and collapses identical native requests, so request count
follows what its grammar expresses losslessly rather than how many queries arrived.

## Sources

Every lane declares what it is responsible for, whose setting it describes, and
what its output reaches. The declaration is on its `SourceSpec`, and
`tests/test_retrieval_coverage.py` checks each declaration against its adapter. The
table below restates those fields for a reader, so it can fall behind them - the specs
are the authority, and the tests are what keep them honest.

| Lane | Class | Jurisdiction | Reads | Feeds |
|---|---|---|---|---|
| Web | general | global | text | insights |
| PubMed | literature | global | text, condition, intervention, product, population, outcome, subject | insights |
| Semantic Scholar | literature | global | same as PubMed | insights |
| Europe PMC | literature | global | same as PubMed | insights |
| WHO Guidelines | guidance | global | text, condition | insights |
| ClinicalTrials.gov | registry | us | text, condition, intervention, product, region | insights, landscape |
| EU CTIS | registry | eu | text, condition | insights, landscape |
| ISRCTN | registry | uk | text, condition, intervention, product, region | insights, landscape |
| FDA Regulatory | regulatory | us | text, condition, intervention | insights, landscape |
| FDA Safety | regulatory | us | subject | safety |
| ChEMBL | molecular | global | subject (compounds) | landscape |
| Open Targets | molecular | global | subject, condition | insights |

`reads` and `feeds` are the two ends of one wire, and both may not be empty. `reads`
is what a lane can be told; `feeds` is where its findings go. Declaring them together
is what makes a hole visible from either side: a lane nothing reads, or a dimension no
lane can act on.

Europe PMC is a third literature lane and not a redundant one: it indexes what PubMed
does and adds preprints from bioRxiv and medRxiv plus open-access full text. A trial
result reaches a preprint server before a journal, so a set of lanes that sees only
journals sees the competitive landscape late.

WHO Guidelines is the only lane in the `guidance` class, which is separate from
`regulatory` for a reason a reader can check: someone asking what a label permits would
not accept a WHO recommendation, and someone asking what the recommended regimen is would
not accept an FDA label. Sources in one class have to be alternatives.

It is also the one lane that makes two calls per result. Its search returns a title and a
URL and no text at all, so a finding built from that alone would be a title - and a lane
whose findings carry no passage feeds nothing while declaring that it does. `MAX_RESULTS`
is correspondingly small: WHO's guideline set for one condition is a curated handful
rather than a corpus. A page that will not load degrades that finding to its title rather
than failing the request, and the outcome carries a `content_unavailable` warning saying so.

PubMed's excerpt is the abstract followed by the article's Results section where PMC
holds open-access full text and the article declares the section (JATS
`sec-type="results"`). It used to append the first characters of the body, which in a
research article is the Introduction. A section only titled "Results" is not guessed at.

PubMed, Europe PMC and ClinicalTrials.gov (`filter.advanced` on the first-posted date)
declare `honors_date_bound`. The rest have the window applied after retrieval.
ClinicalTrials.gov requests only the fields the lane reads (`fields=`): 100 full study
records measured 7 MB against 0.4 MB projected.

`feeds` is the wire, and it may not be empty. A lane whose findings no consumer
reads is a lane a reader can enable, wait for, and be told nothing by: UniProt was
registered and enabled in seven configs while its `reference` findings were filtered
out of insight extraction and it built no records, so it reached nothing. It has been
removed, and `SourceSpec` now refuses a lane that declares no output.

Reference-only records stay available to deterministic views but do not enter Scout
evidence reasoning, so a lane whose every finding is `reference` must declare
`landscape` or `safety` rather than `insights`.

A narrowing adds a request beside the broad one and never replaces it. That is already
`facet_groups`' rule for query facets, and it holds identically for a run-scope
narrowing: a stated region produces the unscoped request *and* a region-restricted twin,
because a programme aimed at one geography still has to be judged against trials run
elsewhere. `tests/test_retrieval_coverage.py` holds this as a standard for every
narrowing dimension rather than as a fact about one adapter.

`region` is run scope, not a per-query facet, for the same reason `condition` is: it
qualifies every query in a run, so stating it once is what lets an attribute whose own
text never names a country still be searched in the right one. ClinicalTrials.gov reads
it through the provider's own `query.locn`, and ISRCTN through `country`, which its tool
compiles to `recruitmentCountry` - so the narrowed request asks where a trial recruited
rather than where its text happens to mention a place. CTIS cannot: its `country`
parameter takes Member State Concerned codes, so the only geographies it can be asked
about are EU member states, and a programme's region usually is not one. That is a
difference in kind rather than unfinished work, and it is declared in
`REGION_UNWIRED_REGISTRIES`.

Every dimension a caller can state now reaches at least one lane, so
`MISSING_SCOPE_CONSUMERS` is empty. The document also states an epidemiological setting,
and it is deliberately absent from `SCOPE_DIMENSIONS`: no source has such a field, so
naming it would add a dimension nothing supplies and nothing consumes, kept alive by two
gap entries. It goes in when a lane can use it.

Two evidence classes have no lane and are declared as gaps in
`tests/test_retrieval_coverage.py`: **access** (procurement and financing bodies) and
**news** (company announcements). No lane holds `lmic` jurisdiction. These are the
classes the Scout configs name as priority institutions, so today those queries reach
only the web lane, whose excerpts are model-written and cannot support a quantitative
claim. Closing a gap means deleting a line from that test.

ChEMBL searches compounds only; a target record carries no development facts, so its
`reference` findings reached nothing. Its `max_phase` is read as ChEMBL defines it:
0.5 is early phase 1, and -1 (unknown) or null states no phase rather than
"Preclinical". The FDA 510(k) request searches both the trade name and the
classification name (`device_name` and `openfda.device_name`), since a condition is
usually only in the second.

## Development

Add a source by implementing and registering one adapter, injecting any optional
connector through `SearchRuntime.integrations`, preserving input lineage, and
enabling its key in Scout config. ToolUniverse is a connector, not an autonomous
router or generic evidence lane. An adapter makes provider calls through
`calls.provider_call` (or `tooluniverse_records.run_tool`) and `transport.fetch`,
sets `record_key` and `identifiers`, and asks for `spec.max_results`.

The website and [PDIS MCP server](../../api/mcp/README.md) call the same
`api/operations/searcher.py` application operation for validation, runtime setup,
and public result assembly. Their transport formats differ; this service does not.
