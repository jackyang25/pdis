# Scout

One document's targets against external evidence: whether its numbers hold up
against live measurements, comparators, and development precedent.

## Background

Scout performs evidence diligence rather than definitive verification. It binds
document meaning once, preserves retrieval lineage, and reports independent
signals without combining them into a holistic score.

## Usage

Import `run_pipeline`, `continue_pipeline`, config lookup, public models, and
serializers from `services.scout`. The initial call returns a portable target
review draft. Retrieval begins only after required decisions are resolved; a
later evidence review finalizes quantitative admission.

Both review checkpoints separate run-level advancement from item-level decisions.
Recorded target and evidence decisions remain editable until that checkpoint is
submitted. An evidence correction replaces the whole source-unit decision, so
only one alternative can be admitted. The client recalculates the cohort using
the existing calculation rules; it retains no undo snapshots. The comparison
table shows the mapper's per-field results and explanations, with non-controlling
fields available in a disclosure. The independent AI recommendation remains
separate. The overall mapper summary stays in the artifact, not repeated in the
review panel.

Review and final comparator details share a read-only comparison component.
It exposes source-ownership reasoning and each target qualifier's retained
document citations; fields with no cited spans receive no inferred citation.
Final admitted and excluded measurements both retain this inspection path.

## Contract

### Numeric review responsibilities

The first checkpoint reviews numeric targets, not every document claim. Claims
and their cited passages live on attributes; numeric targets live once in the
quantitative ledger and link back to those attributes. Nonnumeric claims retain
their separate evidence assessment path.

Retained slide visuals provide context, not replacement text quotations. Numeric
target provenance resolves only against canonical text blocks; image markers
cannot satisfy exact-quote validation. Source extraction warnings remain visible
in review and results and travel with the saved blocks.

Numeric mapping sends one source block per request. Existing canonical field
bindings supply consistent document context; they are not additional extraction
subjects. Several numeric requirements within that block may be proposed together.
The independent target reviewer receives the actual expression, target role,
qualifiers, cited text, and complete retained document. Evidence review receives
the selected quotation and the retained passage used by its mapper, from the same
source. Missing qualifiers cannot be borrowed from unrelated sources.

`flag` means a model could not reach a confident verdict. `unavailable` is a
code-authored independent-review failure with `ai_review_failure_code`; a usable
proposal still permits a human decision. `mapping_failed` carries `failure_code`
and means no usable target was produced for that item. Source ambiguity remains
`uncertain`. Unresolved items require acknowledgement; valid siblings of a partial
extraction remain reviewable. None of these failures silently admits a proposal.

`NumericExpression.display` supplies calendar-year presentation or grammatical
unit forms. Mapping authors this metadata; the shared browser formatter consumes
it without guessing from the number. It changes neither numeric identity nor
arithmetic.

For a disposable preview of both checkpoints and their decision states, see
[the review preview guide](../../web/test-support/README.md).

TPP fields and dynamically extracted IPDP claims converge to the same
document-bound `Attribute` before retrieval. Each attribute retains its stable
identity, canonical document target, exact source spans, evidence domain,
entities, and an ordered view of applicable quantitative claim IDs. The
document-level quantitative ledger is the only canonical store for atomic
targets. Downstream stages cannot rewrite either contract.

Dynamic document units are extracted first, then reconciled once across the full
extracted set before retrieval or quantitative mapping. `unit_reconciler` decides
only identity: equivalent assertions may share an existing representative; different
milestones, dates, populations, conditions, and planned versus achieved events remain
separate. A shared name or paragraph never establishes identity. The prompt keeps
uncertain and partially overlapping claims separate rather than forcing a merge.
Code validates a complete partition of transient unit IDs, retains every member's
exact passages and entities, and derives the merged target from those passages using
the existing `Attribute` contract. Unique downstream names are assigned afterward;
name allocation makes no semantic decisions. Zero or one unit needs no reconciliation
call. A failed partition is handled as every identity layer handles it (see Identity
layers): the units continue unmerged and the run records why. No word-level citation
selection or string-based duplicate fallback is used.

When one source statement contains several atomic targets, each structurally
valid target is retained independently. A failed sibling is retried once and,
if still unresolved, remains a separately acknowledged audit remainder rather
than deleting the valid targets from that statement.

A mapping response must contain exactly one decision for every requested
statement. Missing or duplicate decisions receive one small, source-scoped
retry; a second mechanical failure stops the run instead of becoming a false
human-review item.

Fixed TPP coverage is maintained in `shared/attributes.yaml`; adding an authored
domain field extends this vocabulary without adding a pipeline branch.

`ScoutResult` contains attributes, source blocks, the retrieval scope, query and
retrieval traces, insights, independent evidence judgments, quantitative review and
calibration, deterministic landscape and safety views, and one record per identity
call. Scout's saved analysis version is 5 for this contract.

## Identity layers

Four layers decide which of their items are the same thing, each by one model call over
its set, because the answer is a statement about the set: dynamically extracted claims
(`unit_reconciler`), calculation-compatible numeric targets (`conformity`), one field's
insights (`insight_reconciler`), and program and product names before the landscape and
safety views group by them (`projection_reconciler`). Each may only partition the IDs it
was given and name an existing member as representative. Nothing else decides identity:
insights are not pre-merged for reading alike, names are not case-folded into one
program, and a source record is the record its provider identifiers name
(`Finding.record_key`, `Finding.identifiers`), never one read out of a URL or a title.

They share one mechanic (`identity.partition`) and one failure rule. A partition that
stays invalid after one retry naming the error, is refused, or whose provider fails
leaves the set unmerged, and `ScoutResult.reconciliations` records the layer, the set
(a field name for insights), `not_reconciled` and the failure's code. Stopping would
discard a run over a duplicate a reader can see; merging on a guess would hide one. A
`reconciled` record with `merged == 0` is the layer finding nothing to merge, a
different claim from a layer that never answered. Claim reconciliation runs on OpenAI:
identity is not mapping, and Anthropic is limited to target and measurement mapping.

Identical insights the layer keeps apart derive one ID; the second is given a suffixed
one, an allocation that decides nothing.

## Call policy and prompt layout

Every stage states its tier and effort beside its `*_PER_REQUEST` constant, with the
reason. The three judging stages run on the reasoning tier at low effort, chosen by a
live comparison on the RSV maternal iTPP (4 fields, 30 insights from PubMed, Europe PMC
and ClinicalTrials.gov, each judged under three policies):

| Policy | Drift relations | Grounding | Precedent | Median call (drift / grounding / precedent) |
|---|---|---|---|---|
| fast, low | 18 extends, 9 confirms, 3 contradicts | 4 of 4 as below | 2 of 4 differ | 2.3 s / 1.8 s / 2.4 s |
| reasoning, low | 30 extends | partial ×3, well_grounded | — | 2.8 s / 2.7 s / 2.9 s |
| reasoning, medium | identical to low | identical to low | identical to low | 2.8 s / 6.1 s / 4.2 s |

The fast tier's three `contradicts` were comparator shortfalls, which question 2 of the
drift procedure files as `extends`; its `confirms` credited a named comparator's result
to the document's unnamed product. Medium effort changed no verdict. Preflight and
bookkeeping stages - the context check, query planning, binding, extraction, scope and
announcement reading, projection labels - stay on the fast tier. Every request is laid out the same way: stable instructions in the system
prompt, then the document or bindings the stage's requests share, then their images,
then the one item the request is about as `trailing_text`. Anthropic caches that prefix
(`cache_control` on the last shared block); OpenAI reuses only identical requests, so
there the layout is what a future prefix cache would read. A stage that sends a whole
document or chunk with every request checks the request against
`shared.request_budget` once, before it fans out.

A run may declare `published_since`, an ISO date scoping retrieval. It is applied
where retrieved evidence enters the run rather than at display, so every insight,
precedent, and benchmark describes the cohort it admitted. The window is declared
before retrieval and carried on the reviewed draft, so a continuation searches the
window the user chose rather than widening it after targets were approved. A
finding whose source supplied no publication date is admitted — an absent date is
not evidence of age — and a date stated only to the month or year is held out only if
all of it falls before the window (`Finding.published_before`). `ScoutResult.published_since` records the window because a
benchmark read without it answers a different question, and each
`SearchTrace.excluded_before_window` names the subset of that trace's
`source_urls` the window held out.

## Retrieval coverage

Twelve lanes across six evidence classes, declared on each `SourceSpec` and checked in
`tests/test_retrieval_coverage.py`. Two classes have no lane and are declared gaps:
`access`, because the ToolUniverse catalogue exposes no procurement or financing tool,
and `news`, which the web lane's program query set reaches instead. No lane holds `lmic`
jurisdiction, for the same reason - no WHO ICTRP, CTRI, ChiCTR, ReBEC or PACTR tool is
exposed, and no national regulator outside the US. WHO Guidelines covers the normative
half of that gap at global scope, which is what LMIC ministries and procurement bodies
actually follow.

## Two ledgers

A run derives two authoritative statements from its document, and they are separate
because their consumers and their failure modes are.

Two projections group findings by the thing itself rather than by the variable that
retrieved them: `development_landscape` by program and `safety_observations` by
observation. Each is fed by a typed record an adapter built from provider fields, never by
a model reading prose - the one exception is `announcement_reader`, which exists because a
press release has no fields to map.

| Ledger | Answers | Read by | A wrong value gives you |
|---|---|---|---|
| `QuantitativeLedger` | what the document claims numerically | conformity, assessment | a wrong verdict on the right evidence |
| `RetrievalScopeLedger` | what the run is about | intent building, retrieval | a confident verdict on the wrong evidence |

Both record provenance per item rather than a bare value. The numeric ledger requires a
traced quote; the scope ledger requires a `provenance` of `header`, `document`,
`config_default` or `unset`, and a `document` value must cite the blocks it was read
from. An untraceable reading is not a reading.

The scope ledger states every dimension in `RUN_SCOPE_DIMENSIONS`, including the ones
nothing supplies. An absent entry and an `unset` one carry the same empty value and mean
opposite things: one is a dimension nobody wired, the other is a reader deliberately
widening the search. Requiring the entry is what keeps the first case visible.

`region` is supplied by the document, not the run header. Whichever attribute declares
`supplies_scope: region` in `shared/attributes.yaml` is the supplier, and
`scope_resolver` normalises its bound `document_target` into a phrase a provider's
location field can index. The declaration matters: a stage matching `*.target_countries`
by name works until an intervention class names it something else, and then finds nothing
and reports success.

That stage is a normalisation, not an extraction - the geography is already bound and
cited by the target resolver. What it decides is narrower: whether the text names an
indexable place. "LMIC focus, Gavi-eligible countries" is a real document target and not
a location any registry holds, so the honest answer is that this document narrows nothing
and `region` stays `unset`. A reading that stays invalid after its one retry stops the
run instead: recording it `unset` would widen the search on a failure and look like that
honest answer. The ledger is resolved in `run_pipeline`, before target review, and
carried on the draft as `retrieval_scope`: a failed reading stops the run before anyone
has reviewed anything, the reviewer sees the geography retrieval will use, and the
continuation searches exactly that. Diagnostic has no geography variable at all, so its region is
always unset - a vocabulary gap left as a finding, since adding a variable changes what
every diagnostic run analyses.

`build_retrieval_intents` takes the ledger rather than a parameter per dimension. Loose
parameters are how `region` went missing - adding a dimension meant adding an argument,
threading it through the caller, and remembering both, and nothing failed when you did
neither. A ledger is complete by construction.

Which dimensions are run scope and which are not is itself a decision: `text` is an
intent's own subject, `population` and `outcome` vary between the queries of one intent,
and `product` narrows a single request. None of them is a property of the run.
`tests/test_retrieval_coverage.py` closes the loop from both ends - a dimension supplied
but readable by no lane, and a dimension readable but supplied by nothing, both fail.

## Program scope

Every query belongs to a document variable, and every finding is filed under one. One
kind of question does not fit: "has anything been announced about this program" gives the
same answer whether you asked it while reading efficacy or cold chain. Asked as a track
it would be asked once per variable, twenty times, for one answer.

Those intents carry `scope_ref = PROGRAM_SCOPE_KEY` instead. The seam needs no new
structure, and each claim it rests on is checked in
`tests/test_scout_program_scope.py`:

- `findings_by_attribute` is keyed by `scope_ref`, so the key is simply another key.
- Insight extraction excludes it, because an insight is a statement about one variable.
  The result assembly already refuses an insight naming an unknown field, so the filter
  turns a runtime failure into a stated rule rather than adding a new guarantee.
- The development landscape groups by program name and ignores the key, so these findings
  reach it unchanged.
- The label layer names it "Program-wide", so it does not read as a variable the document
  does not have.

An announcement arrives as prose, and the landscape groups by program name, so
`announcement_reader` reads the name out of it - one call per announcement, since it is a
per-item decision. It cannot be the adapter's job: Searcher fetches, Scout interprets, and
a model call inside an adapter would erase that line.

News is not a second surface. `DevelopmentProgram` is a grouping of source-normalized
records, and a press release states the same kind of fact about the same programs: name,
sponsor, phase. The difference is reliability, not kind, and `evidence_role` already
carries reliability. A reader asking what competitors are doing should look in one place.

So the row shows what it rests on. `record_types` is rendered per program, because "Phase
3" from a registry and "Phase 3" from a company announcement are the same string and not
equally checkable. The reader also reports announcements read, how many named a program,
and how many could not be read after one retry - because an announcement naming none
leaves no row, so without the attempts a weak reading and a quiet week produce the same
empty view, and a failed reading is the pipeline's gap rather than an announcement that
named nothing.

The only required field is the program name. A record may not infer a missing sponsor,
phase or status, so a release naming only a candidate yields a row with that candidate and
dashes in the rest.

`PROGRAM_QUERY_SETS` declares what qualifies, and the test each entry had to pass:
**does the answer change if you ask it about a different variable?** The competitor sweep
fails that test and stays per-variable - ClinicalTrials receives an identical request for
every attribute, but the provider is hit once and each attribute ranks the same candidates
against its own queries, so the twenty it keeps differ. Regulatory approvals, precedent
and safety signals fail it for the same reason.

Each set also declares which lanes it is planned against. `events` targets the web lane
alone: the registries already receive this program's sweep once per attribute, and a
literature index does not hold press releases.

## Coverage tracks

The geographic track is the one that is about place, so it is the only one the scope
ledger reaches. It takes two halves and needs both: the config's `priority_institutions`
and `languages` are the **comparator set**, a declared statement of which settings this
programme is judged against and stable across runs; `region` is what the **document
itself** states, read from the attribute declaring `supplies_scope` and cited to its
blocks.

Given only the first half - which is what it had - this track asked about China, India,
Indonesia and Brazil for a sub-Saharan Africa programme, and wrote its native-language
queries in Chinese and Indonesian. Given only the second it would lose the comparators,
and a target has to be read against settings other than its own. So the region is
additive here exactly as this track is additive to the general one.

Languages stay declared. The region narrows which configured languages to spend budget
on; it never licenses one the configuration does not list. A language list is domain
knowledge, and letting a model choose freely would change the query set between runs.

`general`, `counterfactual` and `precedent` do not receive the region on purpose: they are
broad by design, and narrowing them to one geography answers a smaller question than the
one asked.

The ledger is resolved **before** query generation for this reason. Two layers read it -
the query prompts and the source adapters - and resolving it beside retrieval reached only
the second. That was the shape of the bug: the filters worked, the tests passed, and the
queries were aimed at the wrong places.


Four tracks per variable, additive rather than substituted, and the split is declared
once in `QUERY_TRACK_BUDGET` with the reasoning for each share:

| Track | Queries | Axis | Why this share |
|---|---|---|---|
| general | 8 | what is known | The baseline every other track qualifies, and the only one covering content, source and language at once |
| geographic | 6 | where it holds | The stated mission, and now informed by the document's own region rather than a fixed list |
| counterfactual | 4 | whether it holds at all | The check that stops an optimistic reading, which is the failure a reader cannot see |
| precedent | 3 | whether it was tried | Real value, least time-sensitive of the four |

All eleven configs previously held the same four numbers with nothing stating them, so
the balance was a coincidence eleven files agreed on rather than a decision anyone could
review. A config may still override a share, and doing so now means something: that this
document type needs a different balance.

Every query is the model's. A track missing coverage of a reviewed target is retried once;
a target still uncovered keeps only its field's general queries, which the search plan
shows as no target lineage, rather than receiving a query code assembled from its
descriptor. A track that returns no query at all stops the run, because an unsearched
field reads exactly like one the evidence was silent about. Queries collapse only when the
model wrote the same text with the same facets: a case difference or a different facet is
a different request.

## Request scope

`batching.py` owns one rule for every model stage: a request may contain several
items only when the stage's answer is a statement about the set — deduplication,
partitioning, or one aggregate judgement. A stage returning one decision per item
sends one item per request, because unrelated items in a shared prompt influence
each other and batch composition shifts between runs.

Each stage declares its choice as a `<ITEMS>_PER_REQUEST` constant carrying the
justification. Throughput comes from `map_ordered` fan-out, never from packing
unrelated items into one prompt.

## Evidence semantics

Insight extraction creates objects and decides no identity: `insight_reconciler` groups
statements of one fact, so the extraction prompt never asks the model to merge copies. A
batch that returns no valid answer after its retry stops the run rather than contributing
no insights. Insights cite their records by `record_key`, so two records sharing a page
stay two citations, and their coverage tracks and targets come from the requests that
returned those records (`lineage.RetrievalLineage`, read from each finding's retrieval
paths), not from matching query text.

The three stages that judge insights - relationship, grounding and precedent - see the
same rendering of the evidence (`insight_evidence`): each insight with every record it
rests on, named by title, lane and evidence class, publication date at the precision
the source stated, the kind of excerpt it carries, and the excerpt's verbatim opening.
Their rubrics weigh recency, study design and regulatory relevance, which a paraphrase
and a URL could not show.

Insight extraction retains source-owned facts, including explicit negative findings,
not commentary about what a search batch failed to find. Missing confirmation does
not contradict a document claim. Relationship classification treats search-only
commentary as `unrelated`; when substantive evidence is present, it judges that
evidence within its stated subject, time, and scope. These rules are shared by
fixed TPP fields and dynamically extracted IPDP claims.

An alternative product that would not meet a target is not evidence against the
intended product. A contradiction must establish an incompatible fact about the
asserted property within the claim's subject, time, conditions, and scope. Do not
equate different components or mechanisms without evidence. An explicit universal
claim can be refuted by a counterexample within its scope; a target is not such a
claim. These distinctions do not change retrieval, citation lineage, or the labels.

| Axis | Values |
|---|---|
| Relationship | `contradicts`, `extends`, `confirms`, `unrelated` |
| Grounding | `well_grounded`, `partial`, `thin`, `unsupported`, `unknown` |
| Quantitative calibration | Reviewed comparable measurements and descriptive statistics |
| Precedent | `direct`, `adjacent`, `none`, `unknown`; outcome remains separate |

General, geographic, counterfactual, and precedent query tracks are additive and
retain block, target, intent, adapter, connector, and URL lineage.
The generated source-neutral intents remain authoritative when literature
adapters compile their bounded PubMed or Semantic Scholar request grammar.

## Quantitative calibration

Anthropic Opus interprets each cited document block once, regardless of how
many fields reference it. Every atomic target is document-owned and links to
product fields through typed `defines`, `constrains`, or `context_for`
relations. Only defining and constraining links drive retrieval and
calibration; contextual links remain visible without creating statistics.
Each target separates the document's semantic profile from its direct-comparator
contract. The latter declares each semantic axis as exact, compatible within an
explicit scope, unconstrained, or unknown. Retrieval, source mapping, review,
and admission all consume that same policy, so a named document candidate does
not silently become an exact-product requirement.
The shared comparison policy separates the value being tested from independent
qualifiers: a deadline or duration being measured must not become a requirement
that evidence repeat that value, while a fixed observation window for another
measurement still controls comparability. Minimum/optimal roles are not evidence
requirements. Variation needs a supported scope, not merely a difference between
document columns. The independent target reviewer flags unsound contracts without
rewriting them; the evidence reviewer likewise flags policy violations rather
than silently repairing them. These are model instructions, not deterministic
proof of semantic correctness.
Numeric target review keeps extracted details and citations visible; the
"How evidence will be compared" disclosure retains all matching rules and their
explanations. Evidence review and final comparator details show the rules beside
the actual evidence. Presentation never changes the saved contract.
Before review, a document-wide reconciliation pass may group repeated or
paraphrased representations of the same atomic claim. It can only partition
existing, calculation-compatible target IDs; code combines their field links
and exact provenance without rewriting meaning; it runs on OpenAI, as every identity
layer does. Anthropic then maps source
passages into typed measurement candidates and classifies each source record as
one comparison unit, explicitly disjoint arms or cohorts, or overlapping and
uncertain. OpenAI independently reviews document-target proposals and all
measurement candidates from the same source record together without changing
their mapped data. Code validates structural provenance, declared-unit
compatibility, evidence-unit identity, deduplication, and arithmetic.

Measurement mapping reads only the records an insight cites, and each record's whole
excerpt as Searcher bounded it. Insight extraction is the relevance filter for a
variable, and every measurement must stay traceable to the insight whose sources it
came from. A record whose excerpt a model wrote (`excerpt_kind == "generated"`) never
supplies a number. A source record is identified by its provider identifiers:
`canonical` when a DOI, PMID, trial number or the lane's own record ID names it,
`url_fallback` when the lane stated none.

Only explicitly admitted, compatible, evidence-unit-deduplicated scalars enter
descriptive statistics. Unresolved records remain in the portable audit trail;
cohort spread is never presented as inferential uncertainty or probability of
success.

Every source passage keeps a disposition. Three of its statuses are the model's
verdict on that source; `not_assessed` means this run obtained no verdict and
names the reason in `failure_code`. A processing gap is never reported as
evidentiary uncertainty.

The same token means the same thing on every other axis. A drift relation,
grounding strength, both precedent axes, a projection's `target_relationship`,
an independent review's `unavailable` recommendation, a source passage and the
document-context check each record `not_assessed` (or `unavailable`) with a
`failure_code` from `shared.ai.FAILURE_CODES` (`response_truncated`,
`response_refused`, `invalid_model_response` or `provider_error`) when their stage
obtained no valid answer after its retry, was refused, or its provider failed. The
subject is kept; it is never filed as `unrelated`, `unknown` or `uncertain`, which
are things the model says about the evidence. No model is offered `not_assessed`.
Anything other than those failures is a programming error and still stops the run.

Every variable retrieval investigates gets one grounding record and one precedent
record. A variable no insight reached - retrieval returned nothing for it, or nothing
it returned bore on it - is `no_evidence` on both, with no model call and an empty
reason the interface states in its own voice. That is neither the model's `unknown`
("the evidence I was shown cannot be judged") nor `not_assessed` ("a stage failed").
The result contract refuses a finished run that leaves a searchable variable without
either record.

## Field selection

At the target-review checkpoint the reviewer chooses which searchable fields the
continuation searches. The draft carries the choice as `not_searched_fields` - the
exclusions, so an untouched draft searches every field as before - and the final result
keeps it. It is the one record of the selection: the interface edits it on the draft and
sends the whole draft back.

`continue_pipeline` plans queries, retrieves, extracts insights and runs every judging
stage for the selected fields only. Each excluded field is recorded `not_searched` on
grounding and both precedent axes: code-set, never offered to a model, with no failure
code, no reason and no evidence. It is the reviewer's choice, distinct from `no_evidence`
(searched, nothing reached it) and `not_assessed` (a stage failed). Its numeric targets stay
in the ledger as reviewed and receive no conformity record; a target is calibrated when any
field it defines or constrains was searched. The program-wide questions still run, because
they belong to no field and their answer does not change with the selection.

The contract holds `not_searched` to exactly the excluded fields and refuses any insight,
search trace, calibration or projection for them. A draft that excludes every searchable
field is refused with `FieldSelectionError`, which the route returns as a 400 before the
stream opens.

## Development

The opt-in `tests.test_scout_evidence_semantics_live` suite exercises extraction and
relationship judgments with synthetic sources using the configured model clients.
Set `RUN_SCOUT_SEMANTIC_EVAL=1` and supply model credentials in the environment to
run it. It incurs model usage but performs no retrieval. Ordinary offline tests
skip it; a passing sample is not a guarantee of model accuracy. Existing saved
results are not rewritten when prompts change.

`tests.test_scout_unit_reconciliation_live` uses the same opt-in flag for sampled
dynamic-claim identity checks: paraphrases, different qualifiers, and distinct claims
sharing a passage. Offline tests verify complete partitions, lineage retention,
cross-chunk reconciliation, failure behavior, and unchanged fixed-field routing.

Product framing, source keys, and query budgets live in `configs/`; fixed TPP
definitions and evidence domains live in `shared/attributes.yaml`. Scout uses
Chunker and Searcher only through their public packages. Model contracts are
centralized in `ai_contracts.py` and all model calls use schema-bound structured
output. Source grammar, credentials, rate limits, and normalization remain in
Searcher adapters.
