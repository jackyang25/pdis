# Screener

A set of product-development documents against one stage gate's question bank: what
is still unresolved, and which reviewer it goes to.

## Background

Screener renders no verdict. It triages: for one gate, it reports which of the bank's
questions the supplied material answers, cited to the passage, and which it does not —
each of those alongside the discipline that owns it.

**Only what the source question bank guarantees decides anything.** That is the gate,
the owning discipline, the question text, whether the gate states it as required or anticipatory, and any question
whose own text restricts them to an intervention class. Everything else the bank
carries is a tag: displayed, never gating. Two states used to be derived from a
per-question judgment about which document type could answer a question — a judgment
the source document does not contain, since it is a list of questions for reviewers to
ask people and has no notion of an iTPP, cTPP or IPDP. That document-type judgment
was removed. The bank's required/anticipatory column states whether the gate
expects an answer now or expects the question to be under consideration; it does
not identify a document that should hold the answer.

The value is not the question list, which is a document you could email. Hand a PPL
eighty questions they cannot answer sixty of and you have produced noise. The value
is the sort, so a gate review begins with the answerable questions closed and the
rest addressed to the right person.

Judging one document against its own template is Inspector's responsibility, and
judging a document's targets against external evidence is Scout's; the tools have
different authorities and none substitutes for another. Screener shares no code or
configuration with Inspector. The resemblance — a list of sections holding units,
one model call per unit — is structural only.

## Usage

Import `run_pipeline`, `find_config`, `available_configs`, `available_gates`, `resolve_questions`, public
models, and the contract from `services.screener`.

## Contract

| Direction | Value |
|---|---|
| Input | One or more `DocumentInput(file_path, doc_id)` records, a `GateConfig`, the run's org/intervention/indication, and an injected model client |
| Output | Every question the gate asks, grouped by discipline in authored order, plus the supplied document identities and their retained blocks |

Banks are keyed `(org, gate)`. The intervention class filters questions inside a
bank rather than selecting which bank to read, so `find_config` takes two keys.
Keying files by intervention class would mean editing one shared question in five
files, which is how a bank drifts.

### The four states

| State | Decided by | Means |
|---|---|---|
| `not_applicable` | the question's own text | it restricts itself to another intervention class — **not a shortfall**, and no model read it |
| `answered` | one model call | every part of the question is answered |
| `partly_answered` | one model call | some parts are; `missing` names the rest |
| `not_found` | one model call | nothing supplied addresses it |

The bank's questions are compound — most ask three to five things in one sentence — so
they are judged clause by clause. Without `partly_answered` the model had to file "four
of five clauses answered" as if nothing were there, and a whole gate read the same
whether the plan was thorough or blank.

A partial carries `missing`: one sentence naming what the question still leaves open,
required on that state and refused on every other. That is the sentence a PPL takes back
to the grantee. It is never added to `answered` to imply progress, and there is no score.

`statement` and `missing` divide a partial between them and must not overlap — the first
is the part the documents cover, the second is the part they do not — so a reader sees
both halves without opening the document. A partial whose gap cannot be named specifically
is reported as answered instead: `missing` restating the question is the black box the
field was added to prevent.

### How a question is read

The bank's own wording raises questions the prompt has to answer, or the model answers
them itself and answers them strictly. A five-item parenthetical read as five independent
judgements comes back fully answered about 17% of the time at a 70% chance each — an amber
grid caused by punctuation rather than by anything missing. So the prompt states the
readings:

| the bank writes | it is read as |
|---|---|
| `properties (crystallinity, solubility/pKa, LogP/LogD…)` | the parenthetical says what counts as addressing *the properties* — not five demands |
| `documentation final - stability reports, batch record…` | a dash or colon enumerates what the author wants, so each item is its own clause |
| `Is a plan being initiated…` | answered when the material says it is under way; a finished plan is a later gate's question |
| `Have CMC screeners assessed…` | answered when the substance is there; a document states findings and rarely narrates who produced them |

`test_screener.py` pins each reading, and pins that the bank still contains the wording that
made them necessary — so if the source is ever rewritten, the rules stop carrying weight
visibly rather than silently.

`not_found` is named for what stays true whatever a hint says. `absent` invites the
reader to hear a fault, and this tool cannot tell an omission from a question no
profile or plan was ever going to carry. What it can say is which discipline owns it,
and that is the routing.

Every applicable question is read against **everything supplied**. Nothing is withheld
because of an assumption about where an answer ought to live. The bank's
required/anticipatory column does not affect which questions are assessed or what
material they are assessed against.

The denominator never shrinks: every question appears with a state, every run. No count
is stored, because a carried count is a second authority that can disagree with the
list it summarizes. A bank with no question applicable to the run's intervention class
fails loudly.

### One document collection

Uploads accept DOCX, PPTX, and text-based PDF through Chunker's
`TEXT_EXTRACTION_SUFFIXES` capability, exported here as `SUPPORTED_DOCUMENT_SUFFIXES`
for the API. Documents can contain any evidence relevant to the gate; they need
no iTPP, cTPP, or IPDP type, section taxonomy, or matching Chunker configuration.
TXT, Markdown, and standalone image uploads are not supported. Images embedded
in DOCX/PPTX remain retained, labeled by block ID, and citable. PDF supplies text
only: one block per page, without OCR, image extraction, or inferred tables.
Encrypted, malformed, over-limit PDFs and any page without extractable text fail
the run before assessment. Limits and extraction policy live in the
[Chunker contract](../chunker/README.md#contract).

Chunker's parse-only pipeline reads each document into stable blocks and stamps
`org`, `intervention_class`, and `indication`; `source_type` remains null. The API
preserves the original filename stem as `doc_id`. Duplicate document IDs and
unsupported formats fail before parsing. A document that yields no readable blocks
fails the run instead of silently disappearing beside the other documents.

All blocks travel together through assessment and into the result. Answered and
partly answered questions cite retained block IDs; those citations feed the shared
Documents viewer, saved results, and Ask. Citation checks establish membership in
the retained collection, not that a model interpreted a passage correctly.
PDF page locations and extraction-warning metadata travel in those same blocks.
The result displays the limitation on both tabs, including after import: images
are not read and column/table order may be inaccurate. Selectable text alone does
not establish that every part of a page was extracted.

Portable results use Screener analysis version 5. Earlier versions are refused at
the import boundary because their transient context was not retained and cannot
be converted into cited passages. The shared result envelope remains version 1.

The `/api/screener/run` endpoint accepts one `files` collection plus `gate`, `org`,
`intervention_class`, and `indication`. It rejects the obsolete `source_types`,
`context_files`, and `context_labels` fields. There is no separate context reader,
prompt-only evidence, answer-source field, or context-label output.

Context availability is published by `/api/configs/contexts`: Screener's supported
organizations and intervention classes come directly from its gate banks, independently
of the document-type configurations used by other tools.

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

Transcribed into `configs/*.yaml` by hand from the authored question document, never
parsed from it. That document is what the config was checked against; the config is
the source everything downstream reads. A reader for someone else's prose format is
a normalization layer that breaks whenever the prose is edited.

```yaml
- id: CMC.LCS.5
  text: >-
    For biologics: what are the developability metrics — expression titer…?
  applies_to: [monoclonal_antibody, vaccine]  # ONLY where the question text states it.
  requirement: required       # or `anticipatory`. Stated for every question.
```

`applies_to` is the one field that removes a question from a run, so it is set only
where the question text states the restriction — never by reading subject matter and
inferring a class. 66 such inferences were removed: a wrongly inapplicable question
vanishes silently and reports as "not a shortfall", which is the least detectable
error a bank can hold.

`requirement` is stated by the source for every question: `required` means the gate
expects an answer now, and `anticipatory` means the question should be under
consideration. It does not affect applicability and never reaches the model. It is
carried onto the result, where the interface badges required questions and counts
those that are still partly answered or not found.

Both enumerated fields draw only on vocabularies the input layer already owns, and
`load_config` raises on anything else. Where the prose names a category the system
does not have — "for biologics" — it is resolved into ones it does, `[monoclonal_antibody, vaccine]`,
once, by a human, at transcription. That is the whole extent of the interpretation.

Two fields deliberately absent: no short-form summary, because hand-written
summaries would drift from the text they summarize and truncating in code would
transform authored content; and no `duplicate_of`, because the coordination map wants
Translational Medicine and Clinical Pharmacology to reach dose selection
independently and disagree.

## Request scope

`QUESTIONS_PER_REQUEST = 1`. An unrelated question in the prompt would influence the
decision, and batch composition would shift between runs. Throughput comes from
fan-out, bounded by `MAX_PARALLEL_QUESTIONS`.

The model receives three decisions: `answered`, `partly_answered`, and `not_found`.
They map directly to result states. The fourth result state, `not_applicable`, is
decided by configuration before assessment and is never offered to the model.

Every model decision carries a non-empty `statement`. Both answer states require
citations to supplied blocks; `not_found` and `not_applicable` cannot cite evidence.
Only `partly_answered` carries a non-empty `missing` statement. Invalid model decisions
are retried once and then fail the run. Final contract validation checks completeness,
document/block identities, citation membership, and the state/evidence pairing.

## Run

```text
resolve   deterministic, no I/O; the state the question text owns, fail before parsing
parse     chunker parse-only, every supplied document; preserve input order
assess    one call per applicable question, each reading everything supplied
result    every question, each in one state, with all documents and retained blocks
```

The supplied material precedes the question in every prompt. Order is for cost, not
reading: identical material on every call makes it a prefix a provider can cache, so
the expensive half is paid for once rather than once per question. With the question
first it shared nothing.

Discipline grouping follows the bank's authored order. There is no reconciliation
or deduplication stage: each discipline's question remains independently visible.
