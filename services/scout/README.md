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

## Contract

TPP fields and dynamically extracted IPDP claims converge to the same
document-bound `Attribute` before retrieval. Each attribute retains its stable
identity, canonical document target, exact source spans, evidence domain,
entities, and an ordered view of applicable quantitative claim IDs. The
document-level quantitative ledger is the only canonical store for atomic
targets. Downstream stages cannot rewrite either contract.

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

`ScoutResult` contains attributes, source blocks, query and retrieval traces,
insights, independent evidence judgments, quantitative review and calibration,
and deterministic landscape and safety views.

A run may declare `published_since`, an ISO date scoping retrieval. It is applied
where retrieved evidence enters the run rather than at display, so every insight,
precedent, and benchmark describes the cohort it admitted. The window is declared
before retrieval and carried on the reviewed draft, so a continuation searches the
window the user chose rather than widening it after targets were approved. A
finding whose source supplied no publication date is admitted — an absent date is
not evidence of age. `ScoutResult.published_since` records the window because a
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
and `region` stays `unset`. Diagnostic has no geography variable at all, so its region is
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
equally checkable. The reader also reports a pair - announcements read, and how many named
a program - because an announcement naming none leaves no row, so without the attempts a
weak reading and a quiet week produce the same empty view.

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
Before review, a document-wide reconciliation pass may group repeated or
paraphrased representations of the same atomic claim. It can only partition
existing, calculation-compatible target IDs; code combines their field links
and exact provenance without rewriting meaning. Anthropic then maps source
passages into typed measurement candidates and classifies each source record as
one comparison unit, explicitly disjoint arms or cohorts, or overlapping and
uncertain. OpenAI independently reviews document-target proposals and all
measurement candidates from the same source record together without changing
their mapped data. Code validates structural provenance, declared-unit
compatibility, evidence-unit identity, deduplication, and arithmetic.

Only explicitly admitted, compatible, evidence-unit-deduplicated scalars enter
descriptive statistics. Unresolved records remain in the portable audit trail;
cohort spread is never presented as inferential uncertainty or probability of
success.

Every source passage keeps a disposition. Three of its statuses are the model's
verdict on that source; `not_assessed` means this run obtained no verdict and
names the reason in `failure_code`. A processing gap is never reported as
evidentiary uncertainty.

## Development

Product framing, source keys, and query budgets live in `configs/`; fixed TPP
definitions and evidence domains live in `shared/attributes.yaml`. Scout uses
Chunker and Searcher only through their public packages. Model contracts are
centralized in `ai_contracts.py` and all model calls use schema-bound structured
output. Source grammar, credentials, rate limits, and normalization remain in
Searcher adapters.
