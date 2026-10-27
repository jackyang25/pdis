# Drafter

Suggested iTPP targets for a product type and disease, each drawn from what comparable
products achieved and what published guidance asks.

## Background

Scout checks a target a document already states against external evidence. Drafter
answers the earlier question - what should this iTPP say? - for a team writing one. The two
share evidence machinery and never a run: a Scout result is a finding about a document's
claim; a Drafter result is a set of suggestions for a team to check and edit.

Drafter judges nothing. It has no priority card, no verdicts and no scores, and every
target it produces is labelled a suggestion, on the page and in the Word export.

## Usage

Import `run_pipeline`, `find_config`, `available_configs` and `validate_result_contract`
from `services.drafter`. A run takes the product context, an injected model client and a
Searcher runtime. It reads no document: a team with a draft uses Inspector to find what
the draft leaves out and Scout to check what it states.

## Contract

```text
variables (shared attribute list) → search planning → retrieval
→ evidence reading → figures → suggestion
```

- **Variables** are the shared attribute list for the product type
  (`shared/attributes.yaml`), so a Drafter row and a Scout field are the same variable.
- **Search planning** writes a few queries per variable, each with a purpose -
  `comparable` (what similar products achieved) or `guidance` (what a published profile
  asks) - and Searcher facets.
- **Evidence reading** reads one source for one variable and reports observations, each
  with its basis (`comparable_product` or `published_guidance`) and a quote the code checks
  is in the excerpt (`shared.quotes`). A number comes with `value.text`, the words of its
  quote that state it, and code checks those words are in the quote; the number is the
  reader's reading of them and is never re-parsed. A number whose words are not in its
  quote is kept as words, outside the figures, and counted with the unverified quotes. A reading quoting words the excerpt lacks is asked
  for once more with those quotes named; what still fails is never kept and is counted on
  the row as `unverified_quotes`, beside `unread_findings` for sources that could not be read.
- **Figures** describe comparable values per stated unit (`shared.statistics`), only from
  verbatim literature, registry and regulatory text - Scout's rule for text that may supply
  a number. Units are never converted or pooled, and each group lists the
  `observation_ids` it was computed from.
- **Suggestion** proposes a `range` (minimum, preferred), a `statement`, or `insufficient`,
  citing only the variable's own observations. Each kind is its own variant in the schema,
  so a kind paired with the wrong fields cannot be produced. `leans_on` is read off the
  bases of the observations it cites, never asked for. The pairing of kind, fields and basis
  is one rule, `contract.check_suggestion`, applied to the model's reply and to every saved
  result.
- A variable whose searches returned nothing is `insufficient` without a model call. A
  variable that was never searched (every source unconfigured or inapplicable), or whose
  sources failed, could not be read or quoted words they do not contain, is `status: failed`
  with `evidence_unavailable`: "not enough evidence" would describe a reading that never
  happened. A variable whose planning or suggestion call fails is `status: failed` with
  `search_planning_failed` or `suggestion_failed` and the call's `cause` from
  `shared.ai.FAILURE_CODES` (`response_truncated`, `response_refused`,
  `invalid_model_response`, `provider_error`). Every failed variable stays in the result. An error that means the code
  is wrong (`TypeError`, `AttributeError`, ...) stops the run instead.
- Model calls go through `shared.ai.request_validated`: an invalid answer is repaired once,
  a reply cut off at its budget is retried once at the next lower effort with the same
  budget (`shared.ai.after_truncation`), and a refusal is never retried. Each stage states
  its `TASK`, `EFFORT` and `MAX_TOKENS` beside its `*_PER_REQUEST` constant: planning and
  reading are fast/low, the suggestion reasoning/medium.
- The contract recomputes each row's figures from its observations, so a saved result's
  statistics are always the arithmetic of what it shows.

Every per-item decision is one request (`VARIABLES_PER_REQUEST`, `FINDINGS_PER_REQUEST`);
fan-outs are flat bounded queues.

## Result

A run's result is final when it finishes: it can be saved and exported straight away. There
is no review step, because a review only earns its place before something it controls -
Scout's checkpoints decide what is searched and which measurements enter the statistics -
and nothing in a Drafter run follows its suggestions. The team edits the exported table.

## Configuration

`configs/*.yaml` each name the Searcher sources, the search guidance and the programme
context for one product type; a config is found by the `(org, source_type, intervention_class)` it declares, never
by its filename, and every file must load - a malformed one raises rather than removing a
product type. `load_config` refuses a source whose excerpts are not verbatim, such as
`web`: snippets can support neither a number nor a quotation.

`programme_context` says who every draft is for - for BMGF, products for low- and
middle-income countries and the public-sector programmes that serve them. It is the
organisation's statement of purpose, read by all three stages: searches look for guidance
that serves that setting, readings keep where each source applies, and suggestions aim at
it. A comparable product's markets, price and presentation are evidence about that product,
never a target for this one, so a variable about where or for whom a product is used rests
on guidance for that setting or is insufficient. Without it, a draft proposed the US, EU and
Canada as target countries because that is where its comparator was licensed.

A team may also state the product's intended use - who receives it and what it prevents or
treats, such as maternal immunization to protect infants - in an optional field. It is run
input, not configuration: searches are planned for that use and a target rests on evidence
for it, with evidence from another population used only when nothing for the stated use
speaks to the variable. It is never evidence and never a target value, and the result keeps
it (`intended_use`) so the page and the Word file say what steered the draft. Without it, an
"RSV vaccine" draft mixed older-adult and maternal products.

Published guidance - a WHO preferred product profile, a treatment guideline - is found by
searching, like any other evidence, so it is always the current version. Nothing is copied
into configuration by hand, because a stored copy of a document that is revised goes stale
without anyone noticing.

## Development

`models.py` declares shapes, `configuration.py` loads configs, `stages/` owns each
prompt and reply, `retrieval.py` runs Searcher, `assembly.py` is the deterministic part,
`contract.py` owns checks and `pipeline.py` orchestrates. Drafter uses Chunker and
Searcher only through their packages.
