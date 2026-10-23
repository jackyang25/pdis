# Drafter: evidence-based iTPP target suggestions

> Later decisions: the optional draft upload, hand-transcribed guidance and the in-browser
> review step were removed. Drafter reads no document, finds published guidance by searching
> only, and a run is final when it finishes.

## Purpose

Pilot feedback asked for help *drafting* TPPs from evidence. Scout checks a written
target against external evidence; Drafter proposes a target where none is written yet.
They share evidence machinery and never share a run: Scout's output is a finding about a
document's claim, Drafter's is a suggestion for a person to accept, edit or clear.

Success: a PST member picks a product type and disease, optionally uploads a partial iTPP,
and gets one row per iTPP variable — the draft's own wording where it states the variable,
otherwise a suggested minimum and preferred target (or a short statement for a non-numeric
variable) with the comparable-product results and published guidance it rests on, each
cited. After review they keep a saved result and a Word table of the accepted targets.

## Decisions (agreed)

| Question | Decision |
| --- | --- |
| Document | iTPP first. cTPP later is a config file; IPDP is out of scope (no fixed variables). |
| Per variable | Numeric: minimum + preferred. Non-numeric: one statement. Each with its basis. |
| Input | Product context; optional partial iTPP. Stated variables are kept as written. |
| Basis | Comparable-product results and published guidance, shown separately, never blended. |
| Output | Saved PDIS result plus a Word table export. |
| Architecture | New `services/drafter`; reuse Searcher and Chunker through their packages; only the pure statistics move to `shared/`. Scout is otherwise untouched. |

## Authority and boundaries

- Drafter judges nothing. Its catalog sentence states what it reports and where that
  came from (the rule `web/lib/tools.ts` already gives a tool that judges nothing).
- A suggestion is never a finding. No priority card (that card belongs to tools that
  judge a document), no verdict vocabulary, no scores.
- A suggestion cites only evidence the run retrieved or the configuration transcribed.
  A suggestion with no basis is refused by the contract; "not enough evidence" is a
  model outcome with no values and no basis.
- A model outcome and a pipeline failure never share a value: a variable whose
  suggestion could not be produced carries `status: failed` and a machine-readable code,
  and stays in the result.
- Only OpenAI is used (Anthropic stays limited to Scout).

## Pipeline (`services/drafter`)

```text
variables (shared attribute list for the product type)
→ draft reading          (optional; one call per variable)    → stated | not stated + exact spans
→ search planning        (one call per unstated variable)     → retrieval intents
→ retrieval              (Searcher plan_requests/run_requests) → findings per variable
→ evidence reading       (one call per finding × variable)     → observations, exact quotes
→ statistics             (deterministic, shared/statistics.py) → per-unit descriptive summary
→ suggestion             (one call per variable)               → range | statement | insufficient
```

- **Variables** come from `shared.vocabulary.attribute_definitions(intervention_class)`.
- **Draft reading** parses the upload with Chunker (DOCX/PPTX, parse-only) and asks, per
  variable, whether the draft states its target, citing exact source lines via
  `shared/spans`. One call per variable: each decision is independent
  (`VARIABLES_PER_REQUEST = 1`). Stated variables skip the rest of the pipeline.
- **Search planning** returns a few queries per variable with Searcher facets, split
  across two purposes: what comparable products achieved, and what published guidance
  asks for. Intents are built exactly as Scout builds them (scope ref = variable name).
- **Retrieval** uses the config's source keys. Failures are isolated per source, as in
  Searcher; failed sources are listed on the result.
- **Evidence reading** reads one finding for one variable (`FINDINGS_PER_REQUEST = 1`),
  capped per variable (`MAX_FINDINGS_PER_VARIABLE`). It returns zero or more
  observations: basis (`comparable_product` | `published_guidance`), product or
  publisher, what was measured, an exact quote from the excerpt, and for numbers a value
  or range with its stated unit. Code checks only that the quote is in the excerpt
  (whitespace- and typography-normalised, as Scout does).
- **Statistics** use only comparable-product observations whose excerpt is verbatim and
  whose lane is literature, registry or regulatory — Scout's existing rule for which text
  may supply a number. Values are grouped by their stated unit (never converted);
  a summary needs at least two values in a group.
- **Suggestion** reads the variable, its observations and guidance (by ID), and the
  statistics, and returns: kind, minimum, preferred, statement, rationale, which basis it
  leans on (`comparable_products` | `guidance` | `both`), and the basis IDs. The schema
  carries every field; code checks the pairing (as Screener does for `missing`): a range
  has at least one of minimum/preferred and a basis, a statement has text and a basis,
  insufficient has neither. One corrective retry; then `status: failed`.

### Curated guidance

Published target profiles (for example WHO Preferred Product Characteristics) are rarely
in WHO's guidelines collection, and web snippets cannot support a number. So each config
may list **transcribed guidance statements**, by hand, the way Screener banks are
transcribed: document title, publisher, revision, URL, which indications it covers, and
per variable the exact quoted text and its location. They enter the run as guidance
basis with no retrieval. The shipped configs start with none — values are only added by
transcription from the source document, never generated. `CONTRIBUTING.md` gets the task.

## Result

```text
DraftResult
  org, source_type ("itpp"), intervention_class, indication, display_name
  phase: review | final
  sources[], failed_sources[]
  draft: { doc_id, blocks[] } | null
  variables[]:
    name, label, description, evidence_domain
    origin: draft | suggested
    status: complete | failed      failure: { code, message } | null
    draft_text: { quote, block_ids[] } | null
    observations[]: { id, basis, url, title, source_label, product, measure,
                      quote, value: { value, lower, upper, unit } | null, numeric_eligible }
    statistics[]: { unit, count, minimum, maximum, median, lower_quartile, upper_quartile }
    suggestion: { kind, minimum, preferred, statement, rationale, leans_on, basis_ids[] } | null
    review: { decision: pending | accepted | edited | cleared, minimum, preferred, statement }
```

- Review happens in the browser on the `review` phase, like Scout's checkpoints: Accept,
  Edit or Clear per suggestion, plus "Accept all remaining". Finalize requires a decision
  on every range or statement suggestion; `final` results are immutable and downloadable.
- Draft-origin rows need no decision. Failed and insufficient rows can be filled by hand
  (Edit), which records `edited`.
- `ANALYSIS_VERSIONS.drafter = 1`; one contract in `web/lib/result-contracts.ts`, run on
  pack and unpack; `validate_result_contract` in the service.

## API

- `POST /api/drafter/run` — multipart: org, intervention_class, indication, optional
  `files` (0 or 1 DOCX/PPTX). Clients built before the stream opens; NDJSON stage events
  with completed/total for fan-out stages; shares run capacity.
- `POST /api/drafter/export` — JSON body: a final result; returns a `.docx` table:
  Variable · Target (minimum / preferred, or statement) · Origin · Sources.
- `/api/configs/contexts` publishes `supports.drafter`.

## Web

- `/drafter` page in the PST section, first in catalog order (drafting precedes checking);
  card copy follows the no-authority rule. Icon from the existing freehand set.
- Same shell as other tools: `RunPanel` (configuration + one optional document slot),
  `ResultLayout`, run picker, `FinalResultActions` (JSON), plus a Word export action.
- Rows: variable, origin badge, target; expanded: suggestion and rationale (model-authored),
  then two separate source lists — *Comparable products* and *Published guidance* — using
  `SourceEntry`, the statistics line, and review controls. Documents tab only when a draft
  was uploaded.
- `RunPanel` gains optional slots (Run enabled when required slots are filled).
- Assistant: a Drafter legend; the browser adds Drafter runs to the workspace.

## Shared change

`shared/statistics.py`: `quantile`, `empirical_percentile`, `describe(values)`. Scout's
private `_quantile`/`_empirical_percentile` are replaced by these imports; Scout's tests
prove identical behaviour.

## Documentation

AGENTS.md Drafter section; service README; README tools table; CONTRIBUTING task for
transcribing guidance; product knowledge workflow graph; prompt catalog and regenerated
prompt reference; release note.

## Testing

- Python: statistics; config loading (unknown variables or indications rejected);
  contract (basis pairing, failure vs outcome, review decisions); pipeline with a fake
  model and patched retrieval (stated variables skip search; numeric eligibility; quote
  check; failure isolation); route (optional file, 404 config, credentials before
  stream); export (valid DOCX, accepted values only); prompt reference.
- Web: contract and envelope; tool catalog and sections; presentation (origin, separate
  bases, review flow, finalize gate); run history coverage; Assistant workspace.
- One live run through Kong on a real product before calling it done.

## Out of scope

cTPP/IPDP drafting, publication-date windows, a priority card, editing draft-origin rows,
exporting into the PDID Word template, MCP exposure.
