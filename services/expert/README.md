# Expert

A set of product-development documents against one stage gate's question bank: what
is still unresolved, and which reviewer it goes to.

## Background

Expert renders no verdict. It triages: for one gate, it reports which of the bank's
questions the supplied material answers, cited to the passage, and which it does not —
each of those alongside the discipline that owns it.

**Only what the source question bank guarantees decides anything.** That is the gate,
the owning discipline, the question text, the `[PQ]` markers, and the eleven questions
whose own text restricts them to an intervention class. Everything else the bank
carries is a tag: displayed, never gating. Two states used to be derived from a
per-question judgment about which document type could answer a question — a judgment
the source document does not contain, since it is a list of questions for reviewers to
ask people and has no notion of an iTPP, cTPP or IPDP. That judgment now lives in
`likely_in`, where being wrong costs a misleading hint rather than a wrong answer.

The value is not the question list, which is a document you could email. Hand a PPL
eighty questions they cannot answer sixty of and you have produced noise. The value
is the sort, so a gate review begins with the answerable questions closed and the
rest addressed to the right person.

Judging one document against its own template is Inspector's responsibility, and
judging a document's targets against external evidence is Scout's; the tools have
different authorities and none substitutes for another. Expert shares no code or
configuration with Inspector. The resemblance — a list of sections holding units,
one model call per unit — is structural only.

## Usage

Import `run_pipeline`, `find_config`, `available_gates`, `resolve_questions`, public
models, and the contract from `services.expert`.

## Contract

| Direction | Value |
|---|---|
| Input | One or more `DocumentInput`s, a `GateConfig`, the run's org/intervention/indication, optional `ContextItem`s, and an injected model client |
| Output | Every question the gate asks, grouped by discipline in authored order, each in exactly one state |

Banks are keyed `(org, gate)`. The intervention class filters questions inside a
bank rather than selecting which bank to read, so `find_config` takes two keys.
Keying files by intervention class would mean editing one shared question in five
files, which is how a bank drifts.

### The three states

| State | Decided by | Means |
|---|---|---|
| `not_applicable` | the question's own text | it restricts itself to another intervention class — **not a shortfall**, and no model read it |
| `answered` | one model call | the supplied material answers it |
| `not_found` | one model call | it was read against everything supplied and no answer was there |

`not_found` is named for what stays true whatever a hint says. `absent` invites the
reader to hear a fault, and this tool cannot tell an omission from a question no
profile or plan was ever going to carry. What it can say is which discipline owns it,
and that is the routing.

Every applicable question is read against **everything supplied**. Nothing is withheld
because of an assumption about where an answer ought to live — that assumption is
`likely_in`, and it is a hint.

The denominator never shrinks: every question appears with a state, every run. No count
is stored, because a carried count is a second authority that can disagree with the
list it summarizes. A bank with no question applicable to the run's intervention class
fails loudly.

### Canonical and transient input

Canonical documents are DOCX and PPTX, parsed by chunker into blocks with stable
IDs, and an answer read from one cites the exact passages.

A `ContextItem` is transient: pasted for one run, put into the prompt, and never
stored. Only its `label` reaches the result, so an answer sourced from it carries
attribution — *which* source — without lineage, and can never be presented as
cited. The label is free text the user typed, never a `source_type`; the moment it
becomes one, transient input has entered the contract and needs configs,
validation, and stamping on blocks.

Both citation forms are membership-checked against what was supplied. Neither proves
a model read the source; both prove what it named exists.

## The bank

### Where it comes from

Every bank declares `mirrors`: the authored document it transcribes, named with its
version and linked. Required rather than optional, unlike Inspector's — the whole
tool is a transcription, so a bank that does not say what it transcribes cannot be
audited or told stale.

Nothing in the repository can verify that claim; the source is a SharePoint document
outside it. What `mirrors` does is name which document to re-check when that document
moves, and the **version is the load-bearing part**: a bank taken from v5 is stale
the moment v6 publishes.

It is carried onto every result as `bank_source`, for the same reason each question
carries its own `text` and Scout carries its retrieval window — a saved review has to
state its own authority. A reader six months later cannot otherwise tell a v5 triage
from a v6 one, and `validate_result_contract` refuses a review whose `bank_source`
disagrees with the config that produced it.

### How it is written

Transcribed into `configs/*.yaml` by hand from the SME question document, never
parsed from it. That document is what the config was checked against; the config is
the source everything downstream reads. A reader for someone else's prose format is
a normalization layer that breaks whenever the prose is edited.

```yaml
- id: CMC.LCS.5
  text: >-
    For biologics: what are the developability metrics — expression titer…?
  applies_to: [mab, vaccine]  # ONLY where the text states it. Eleven questions do.
  likely_in: [ipdp]           # a hint. Never gates. Omit when unclear.
  pq: false                   # omit for false
```

`applies_to` is the one field that removes a question from a run, so it is set only
where the question text states the restriction — never by reading subject matter and
inferring a class. 66 such inferences were removed: a wrongly inapplicable question
vanishes silently and reports as "not a shortfall", which is the least detectable
error a bank can hold.

`likely_in` is not in the source document at all. It says where an answer of that kind
usually lives, so a reader knows which document to open or upload. It never reaches
resolution, never reaches the model, and appears in the interface as "usually answered
in".

Both enumerated fields draw only on vocabularies the input layer already owns, and
`load_config` raises on anything else. Where the prose names a category the system
does not have — "for biologics" — it is resolved into ones it does, `[mab, vaccine]`,
once, by a human, at transcription. That is the whole extent of the interpretation.

Two fields deliberately absent: no short-form summary, because 560 hand-written
summaries would drift from the text they summarize and truncating in code would
transform authored content; and no `duplicate_of`, because the coordination map wants
Translational Medicine and Clinical Pharmacology to reach dose selection
independently and disagree.

## Request scope

`QUESTIONS_PER_REQUEST = 1`. An unrelated question in the prompt would influence the
decision, and batch composition would shift between runs. Throughput comes from
fan-out, bounded by `MAX_PARALLEL_QUESTIONS`.

The decision is a single three-value enum — `answered_from_document`,
`answered_from_context`, `not_found` — rather than a state plus a separate source field,
because those two would need a cross-field rule the schema cannot express. One enum
makes an incoherent answer unrepresentable rather than merely invalid.
`answered_from_context` is offered only when context items were supplied.

## Run

```text
resolve   deterministic, no I/O; the state the question text owns, fail before parsing
parse     chunker, canonical documents only
assess    one call per applicable question, each reading everything supplied
result    every question, each in one state
```

The supplied material precedes the question in every prompt. Order is for cost, not
reading: identical material on every call makes it a prefix a provider can cache, so
the expensive half is paid for once rather than once per question. With the question
first it shared nothing.

Deliberately absent: no normalizer for the bank, no chunker for transient input, no
routing stage (routing is resolve's output), and no reconciliation stage.
