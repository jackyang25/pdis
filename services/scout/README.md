# Scout

Test document targets against live evidence, comparators, and precedent.

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

## Development

Product framing, source keys, and query budgets live in `configs/`; fixed TPP
definitions and evidence domains live in `shared/attributes.yaml`. Scout uses
Chunker and Searcher only through their public packages. Model contracts are
centralized in `ai_contracts.py`, while source grammar, credentials, rate limits,
and normalization remain in Searcher adapters.
