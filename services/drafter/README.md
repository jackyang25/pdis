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
  is in the excerpt (`shared.quotes`).
- **Figures** describe comparable values per stated unit (`shared.statistics`), only from
  verbatim literature, registry and regulatory text - Scout's rule for text that may supply
  a number. Units are never converted or pooled.
- **Suggestion** proposes a `range` (minimum, preferred), a `statement`, or `insufficient`,
  citing only the variable's own observations and naming the basis it leans on. The pairing
  of kind, fields and basis is one rule, `contract.check_suggestion`, applied to the model's
  reply and to every saved result.
- A variable with no evidence at all is `insufficient` without a model call. A variable
  whose planning or suggestion fails is `status: failed` with a code
  (`search_planning_failed`, `suggestion_failed`) and stays in the result.

Every per-item decision is one request (`VARIABLES_PER_REQUEST`, `FINDINGS_PER_REQUEST`);
fan-outs are flat bounded queues.

## Result

A run's result is final when it finishes: it can be saved and exported straight away. There
is no review step, because a review only earns its place before something it controls -
Scout's checkpoints decide what is searched and which measurements enter the statistics -
and nothing in a Drafter run follows its suggestions. The team edits the exported table.

## Configuration

`configs/bmgf_itpp_<class>.yaml` names the Searcher sources and the search guidance for
a product type. `web` is not among them: its excerpts are snippets, which can support
neither a number nor a quotation.

Published guidance - a WHO preferred product profile, a treatment guideline - is found by
searching, like any other evidence, so it is always the current version. Nothing is copied
into configuration by hand, because a stored copy of a document that is revised goes stale
without anyone noticing.

## Development

`models.py` declares shapes, `configuration.py` loads configs, `stages/` owns each
prompt and reply, `retrieval.py` runs Searcher, `assembly.py` is the deterministic part,
`contract.py` owns checks and `pipeline.py` orchestrates. Drafter uses Chunker and
Searcher only through their packages.
