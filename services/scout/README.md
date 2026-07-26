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
entities, and quantitative ledger. Downstream stages cannot rewrite it.

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

## Quantitative calibration

Anthropic Opus maps document spans into typed targets and source passages into
typed measurement candidates. OpenAI independently reviews both proposal types
without changing their mapped data. Code validates structural provenance,
declared-unit compatibility, evidence-unit identity, deduplication, and
arithmetic.

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
