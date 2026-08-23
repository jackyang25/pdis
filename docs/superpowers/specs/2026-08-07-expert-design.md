# Expert

> **Superseded on the bank (2026-08-10).** The 560-question document this was designed
> against was the wrong source. The shipped bank is now *Stage Gate Questions - All
> Gates.docx*, developed from the Drug Development Milestone Dictionary (PDID): 349
> questions, 5 disciplines, 7 gates, each question stating `required` or `anticipatory`,
> and every bank scoped to `drug`. The architecture below stands unchanged — that is the
> point of it — but the counts, the discipline list, the `[PQ]` marker and the `likely_in`
> hint no longer describe what ships.

Expert — stage-gate question triage

**Status: built and available.** Service, route, web page, result contract, Ask
legend, docs graph, published prompt, and tests are all in place. All seven gates are
transcribed — 560 questions, 8 disciplines x 10 per gate, 21 `[PQ]`-marked at DTL.
What is left is calibration and review, not construction. See §14.

This document is the design and the record of where the build departed from it. It
exists so the next person does not have to reconstruct the reasoning from a chat log.

## 0. The invariant, and where the build corrected this spec

**Only what the source question bank guarantees may decide anything.** That is the
gate, the owning discipline, the question text, the `[PQ]` markers, and the eleven
questions whose own text restricts them to an intervention class. Everything else the
bank carries is a tag: displayed, never gating.

This was learned by violating it. The first build had five states, two of which came
from a per-question judgment about which document type could answer a question —
`answerable_from`. That judgment is not in the source document, which is a list of
questions for reviewers to ask people and has no notion of an iTPP, cTPP or IPDP. Being
wrong there produced a confident wrong state: a question withheld from assessment, or a
gap attributed to a grantee for something no document was ever meant to hold. And 66 of
the 77 `applies_to` values were the same kind of inference, each silently removing a
question from the run and reporting it as "not a shortfall".

What replaced it:

| Was | Now |
|---|---|
| 5 states, 2 from a guess | **3 states**, all traceable |
| `answerable_from` gated assessment | `likely_in` — a hint, shown as "usually answered in" |
| `applies_to` on 77 questions | on the **11** whose text states the restriction |
| each question saw the documents I guessed | every question reads **everything supplied** |
| `absent` — a gap the grantee can close | `not_found` — true whatever the hint says |
| the hint went into the prompt | the model is never told where to look |

The costs, taken deliberately: ~80 calls per gate instead of 43, and "no document could
ever answer this" is no longer claimed — routing is by discipline, which the source
document guarantees. The prompt now puts the supplied material first and the question
last, so the identical half is a cacheable prefix; that ordering is what keeps doubling
the calls from doubling the bill.

### Earlier corrections, from the first build

Seven things changed during it. Each is a correction, not a compromise:

1. **`find_config(org, gate)`, two keys, not three.** The intervention class filters
   questions *inside* a bank rather than selecting which bank to read, so taking it
   at lookup would be a parameter that does not affect the lookup.
2. **An empty assess queue is a valid result.** The spec said fail loudly. Wrong: a
   gate whose applicable questions all route to disciplines is complete, and routing
   is the tool's main output. What does fail loudly is a bank with no question
   applicable to the run's intervention class.
3. **The model returns one three-value decision**, not a state plus a source.
   `answered_from_document | answered_from_context | absent` needs no cross-field
   rule, which JSON Schema cannot express — so an incoherent answer is
   unrepresentable rather than merely invalid. `answered_from_context` is omitted
   from the enum entirely when no context was supplied.
4. **`answerable_from` is carried on each assessment.** Without it the interface
   cannot say which upload would make a `not_assessable` question assessable, and the
   first attempt hardcoded `["itpp", "ctpp", "ipdp"]` in `web/lib/` — a copy of a
   vocabulary the configs own.
5. **`PriorityPanel` is used.** An earlier note said not to, reasoning that priority
   implies weighting. It does not: the panel renders an already-ordered list and
   states the rule. Refusing the shared opening panel would have been the drift.
6. **`SectionHeading` was promoted** from inside Inspector's page to
   `web/components/ui/`, per the second-consumer rule, rather than copied.
7. **`not_assessable` is also assignable after parsing.** A document type can be
   uploaded and produce no blocks. Assessability is the same authority either way;
   that case is only reachable once the parse has run.
8. **Every bank declares `mirrors`, and it is required.** Inspector's configs
   already carry this field — provenance naming the authored source, published on the
   docs page with the caveat that nothing in the repo can verify it. Expert follows
   the convention and makes it mandatory, because the whole tool is a transcription.
   It is also carried onto the result as `bank_source` and checked by the contract, so
   a downloaded review states which version of the bank produced it: a v5 triage and
   a v6 triage are different answers, and only that line distinguishes them.
9. **`load_config` is cached on file mtime.** Not added speculatively: a bank is 80
   questions of prose, and `/api/configs/document-types` asks whether Expert can read
   each of a dozen document types, each answer walking every gate. Measured at
   **9.7 seconds** before caching and 245 ms after, with `/api/expert/gates` going
   390 ms to 2 ms. Keyed on mtime so a hand-edited bank is picked up immediately,
   which matters because hand-editing is how these are maintained. It caches
   immutable files, not session state.

## 1. What it does

A gate review asks a fixed set of questions. The bank is a matrix: 7 gates × 8
disciplines × 10 questions = 560, authored by SMEs, with `[PQ]` marking WHO
prequalification questions carried inside the DTL ten.

Expert does not answer those questions. It **triages** them. For one gate, given
the investment's documents, it reports which questions the documents already
answer with a citation, which they should answer and don't, and which no document
could ever answer — those routed to the discipline that owns them.

The value is not the question list, which is a document you could email. Hand a
PPL 80 questions they cannot answer 60 of and you have produced noise. The value
is the sort: arrive at the review with the answerable questions closed and the
rest addressed to the right person. It democratises the **SME's attention**, not
the question bank.

## 2. Its authority, and the Inspector boundary

Each tool judges against a different authority. Expert's is the gate's question
bank. It reads several documents at once, which no judging tool currently does.

The boundary that must be written into `AGENTS.md`, because these two will
otherwise drift into each other:

> **Inspector** asks *is this document complete and well-formed against its own
> template.* One document, its rubric.
> **Expert** asks *does the evidence exist anywhere in this set for a reviewer to
> close this question.* Several documents, a gate's bank.

Expert shares no code and no config with Inspector. The resemblance is
structural only — a list of sections holding units, one model call per unit — and
that resemblance is what makes the scale predictable, not a dependency.

## 3. The bank is transcribed, not parsed

The SME document is prose. **Do not write a reader for it.** Hand-author the YAML
once and keep the prose as the thing the config was checked against. 560
questions is a day of transcription and it buys never owning a parser, which is
the brittle layer this design exists to avoid.

One file per `(org, gate)` — seven files, not thirty-five. The matrix is gate ×
discipline, and most questions are shared across intervention classes with
per-question exceptions. Keying files by class would mean editing one question in
five places, which is the drift.

```yaml
# services/expert/configs/bmgf_eop1.yaml
org: bmgf

gate:
  id: eop1
  label: End of Phase 1
  # Gates are ordered. The selector lists them in development order, and nothing
  # derives this from the id.
  ordinal: 4

disciplines:
  - id: cp
    label: Clinical Pharmacology
    questions:
      - id: CP.EOP1.6
        text: >-
          Has a concentration-QTc analysis been performed to the standard
          required, and does the upper bound of the two-sided 90% confidence
          interval exclude the threshold of regulatory concern at the highest
          clinically relevant exposure — including the exposure produced by the
          worst-case DDI?
        # Omit for every class.
        applies_to: [drug, monoclonal_antibody]
        # Omit when no document could answer it.
        answerable_from: [ipdp]
        # Omit for false.
        pq: false
```

Six fields. Each has exactly one consumer.

### Why this is interoperable rather than normalised

**The only two enumerated fields draw on vocabularies the input layer already
owns.** `applies_to` takes `intervention_class` values; `answerable_from` takes
`source_type` values. `load_config` validates against those and raises on anything
else. That is a contract check, not a translation.

That constraint forces the authoring discipline that keeps runtime clean. The
prose says *"For biologics:"* and there is no `biologic` in our vocabulary. The
tempting fix is a synonym table. The correct fix is to author
`applies_to: [monoclonal_antibody, vaccine]` — resolved once, by a human, visibly, at
transcription. Every place the prose names a category we do not have, it is
resolved into ones we do. **Nothing maps anything at runtime.**

### Two fields that must not be added

- **No `summary` or short-form field.** These questions run 40–60 words and the
  interface needs a two-line preview, but 560 hand-written summaries would drift
  from `text`, and truncating in code is the normaliser we are avoiding.
  `line-clamp-2` in CSS is rendering, not transformation.
- **No `duplicate_of`.** The coordination map deliberately has Translational
  Medicine and Clinical Pharmacology reach dose selection independently and
  disagree in public at EOP1 and EOP2. Since there is no reconciliation stage,
  both questions simply exist and both are assessed. **The absence of the
  mechanism is the mechanism**, and it needs recording or someone will add
  deduplication as a tidy-up and destroy the one thing the bank was built to
  produce.

`COORDINATION_MAP.md` — the SME document's topic-ownership map — belongs beside
the banks as config, since discipline ownership is what makes routing possible.

## 4. Five states, one owner each

```python
QuestionState = Literal[
    "not_applicable", "not_answerable", "not_assessable", "answered", "absent"
]
AnswerSource = Literal["document", "context"]
```

| State | Decided by | When | Action it implies |
|---|---|---|---|
| `not_applicable` | `applies_to` vs `intervention_class` | resolve, deterministic | none — **not a shortfall** |
| `not_answerable` | `answerable_from` empty | authoring | goes to the discipline |
| `not_assessable` | `answerable_from` ∩ uploaded types = ∅ | resolve, deterministic | upload the missing document |
| `answered` | one model call, closed enum | run | none |
| `absent` | one model call, closed enum | run | gap the grantee closes |

Nothing is decided twice. This is the same discipline as Inspector's `level`
deriving from `reason`: one authority per value, so two consumers cannot disagree.

`not_answerable` and `not_assessable` stay separate because one routes to a person
and the other asks for a file. Collapsing them would make a missing upload look
like an SME question.

**The denominator never shrinks.** Every question in the gate appears in the
result with a state, every time. That is what makes two runs comparable line by
line and lets a governance committee trust a count. Same reason Inspector keeps a
unit the model said nothing about.

**Counts are derived, never stored.** A stored count is a second authority that
can disagree with the list it summarises.

## 5. Canonical and transient input

PDIS already draws this line, in the Ask legend's description of
`conversation_attachments[]` — *"user-supplied context, not PDIS findings or
independently verified evidence."* Reuse those words. Do not invent a parallel
vocabulary.

| | Canonical | Transient |
|---|---|---|
| What | iTPP, cTPP, IPDP as DOCX/PPTX | labelled text pasted for this run |
| Path | Chunker → `ContentBlock`s with stable IDs | straight into the prompt |
| Provenance | source **and** exact block | source only |
| Stored in the result | blocks embedded, as every tool does | **the label only, never the text** |
| Format gate | `DOCUMENT_SUFFIXES` | none — it is not a file |
| Config needed | chunker config per type | none |

**Transient input has no custom wiring.** In and out of the prompt. It is never
chunked, never stored as content, never versioned, and there is nothing for Ask to
interpret beyond a name.

**Provenance has two levels, and transient input keeps the first.** Each context
item is a labelled section in the prompt, and the model returns which label it
used, constrained to a closed list of the labels supplied. That is exactly the
guarantee block IDs already give: you cannot prove the model read that source, but
you can prove the label it returned exists. Membership check, not a truth check.

So a transient answer reads *"answered from the CMC Development Report"* — real
attribution — rather than *"answered from context,"* which throws away something
the user knows.

Two lines to hold:

- **The label is free text the user typed, not a `source_type`.** The moment it
  becomes a config vocabulary value, transient input has entered the contract and
  needs configs, validation, and stamping on blocks.
- **Transient input is repeatable labelled rows, not one textarea** — a name field
  and a text area per item, add and remove, the same shape as Aligner's document
  rows. A single unnamed blob has nothing to attribute to.

**One consequence, accepted deliberately.** Because the text is never stored,
reopening a saved result later shows the label with nothing behind it. The label is
the entire record. That is the price of keeping transient input out of the
contract, and it is why the provenance line must be explicit rather than subtle: a
reader six months later needs to see at a glance which answers they can verify and
which they would have to ask a person about.

## 6. Input configuration

Nothing new in the shared header.

| Bucket | Field | Component | Notes |
|---|---|---|---|
| 1 — context | org, intervention_class, indication | `ContextFields` | unchanged |
| 2 — document type | one per uploaded document | `SourceTypeField` per row | as Aligner does |
| 3 — bespoke | **gate** | `ConfigSelect`, page-owned | the only new input |
| 3 — bespoke | **context items** | labelled rows, page-owned | never leaves the tool |

`indication` filters nothing. Rifampicin and ART co-medication questions are not
inapplicable for a non-TB product — they are *shaped* by the indication. So it goes
into prompt framing as `{indication}`, exactly as Inspector and Scout already use
it.

### Deterministic filters, all before any model call

1. **gate** (run parameter) → 560 → 80
2. **intervention_class** (header) → `not_applicable`
3. **`answerable_from` empty** (config) → `not_answerable`, routed
4. **uploaded `source_type`s** → `not_assessable`

A realistic run: 80 in the gate, ~65 applicable to a vaccine, ~20 of those
document-answerable, minus any whose document was not uploaded → **15–20 model
calls.** Comparable to an Inspector run.

### Config lookup

`find_config(org, intervention_class, gate)` — same name and same contract as every
other service's (resolve or raise `LookupError`); only the key differs. Aligner is
already in this position. `has_config` beside it for the predicate case.

## 7. The run

```
resolve   deterministic, no I/O. Bank + intervention_class + uploaded source_types.
          Every question gets a terminal state or joins the assess queue.
          Fail loudly when no bank matches, and when the queue is empty.

parse     Chunker, canonical documents only. Already supported — DOCX and PPTX,
          zero new work. Bounded parallelism as Aligner does.

assess    One call per queued question. Closed enum out.

result    Every question in the gate, each with one state.
```

Two code stages, one model stage. **Deliberately absent:** no normaliser for the
bank, no chunker for transient input, no routing stage (routing is resolve's
output — unanswerable questions never enter the queue and their owner is already a
field in the bank), no reconciliation stage.

Resolve runs before parsing for the same reason Aligner resolves edges first: fail
before the expensive part, and never let a run that assessed nothing look like a
run that found nothing wrong.

### The assessor's contract

One question per request. Per `AGENTS.md`, a stage returning one decision per item
sends one item per request; `QUESTIONS_PER_REQUEST = 1` carries that
justification.

Input: the question text, the blocks belonging to its `answerable_from` documents,
and each transient item as a labelled section.

Output, schema-bound:

```
state:          answered | absent          (closed; excludes failure members)
source:         document | context          (required when answered)
context_label:  one of the supplied labels  (required when source == context)
block_ids:      from the supplied blocks    (required when source == document)
statement:      one short sentence
```

Deterministic post-checks only: block IDs exist in the supplied set, the context
label is one that was supplied, `source` and its evidence agree. No re-parsing of
prose.

## 8. Result shape

```python
@dataclass
class QuestionAssessment:
    id: str                      # CP.EOP1.6 — the bank's own id
    text: str                    # carried so a saved result renders without the config
    state: QuestionState
    pq: bool = False
    statement: str = ""          # model prose; empty for config-decided states
    source: AnswerSource | None = None
    cited_block_ids: list[str] = field(default_factory=list)
    context_label: str = ""      # only when source == "context"

@dataclass
class DisciplineReview:
    id: str
    label: str
    questions: list[QuestionAssessment]

@dataclass
class ReviewDocument:
    doc_id: str
    source_type: str

@dataclass
class GateReview:
    gate_id: str
    gate_label: str
    documents: list[ReviewDocument]
    disciplines: list[DisciplineReview]
    context_labels: list[str]    # names only; never the text
    org: str
    intervention_class: str
    indication: str
    blocks: list["ContentBlock"] = field(default_factory=list)
```

`text` is carried on the result rather than looked up from config at render time,
so a downloaded file stays readable after the bank is edited — the same reason
every other tool embeds its blocks.

### Structural contract

`validate_result_contract(result, config)` returns the result it validated, and
checks:

- every question in the resolved bank appears exactly once; no question outside it
- `state == answered` ⇒ `source` set; otherwise `source is None`
- `source == "document"` ⇒ at least one `cited_block_ids`, all belonging to a
  carried document, and no `context_label`
- `source == "context"` ⇒ `context_label` in `context_labels`, and no block IDs
- `not_answerable` questions carry no statement, no source, no blocks
- documents have distinct `doc_id`s and known `source_type`s
- block IDs are unique across carried blocks

Structural only. It authorises model output; it does not replace semantic review.

## 9. Contracts downstream

| Concern | File | Change |
|---|---|---|
| Envelope | `web/lib/result-file.ts` | `ResultType` gains `expert`; `ANALYSIS_VERSIONS.expert: 1`; `packExpertResult` / `unpackExpertResult`; `expertResultFilename` — gate plus joined source types |
| Readability | `web/lib/result-contracts.ts` | `assertExpertReadable`. The `satisfies Record<ResultType, ResultContract>` map refuses to compile without it |
| API types | `web/lib/api.ts` | `ToolName` gains `"expert"`; `ExpertResponse`, `GateReview`, `QuestionAssessment`, `DisciplineReview`; `fetchGates()`; `runExpert(documents, gate, contextItems, header, onStage)` |
| Document support | `api/routes/configs.py` | `supports["expert"]`, true when a chunker config exists for the type **and** that `source_type` appears in some bank's `answerable_from` for that org and class. Computed without a gate, so the picker works before one is chosen |
| Gate list | `api/routes/expert.py` | `GET /gates` returns the declared gates in `ordinal` order, so the selector reads the service's own config rather than a copy in TypeScript. Same reason Aligner publishes `GET /edges` |
| Tool routing | `web/components/configuration-fields.tsx` | `PATH_TO_TOOL` gains `/expert` |
| Ask | `services/assistant/legends.py` | `EXPERT_LEGEND` + registration in `_LEGENDS`; the workspace legend's `result_type` sentence gains Expert. The legend must state that a `context`-sourced answer has no block lineage and must never be presented as cited, and that `not_applicable` is not a shortfall |
| Docs | `shared/product_knowledge.json` | a workflow graph: documents and gate → resolve → parse → assess → result. `tests/test_product_knowledge_contract.py` gains `expert` to its published-workflow tuple |
| Prompts | `services/expert/prompt_catalog.py`, `shared/prompt_reference.json` | one `CatalogEntry` for the assessment prompt; regenerate with `PYTHONPATH=. python scripts/generate_prompt_reference.py`. `tests/test_prompt_reference.py` gains `("expert", "assessment")` and `expert` to the published-tools set |
| Card | `web/lib/tools.ts` | `availability` → `available`, add `href: "/expert"` and an `activity` estimate |
| Invariants | `AGENTS.md` | an `### Expert` section under Tool contracts: the Inspector boundary, the five states and their owners, the no-reconciliation rule, and that transient input never enters the contract |
| Service docs | `services/expert/README.md` | background, usage, contract table, request scope |

New service files: `services/expert/{__init__,models,contract,pipeline,prompt_catalog}.py`,
`stages/assessor.py`, `configs/bmgf_*.yaml`, `README.md`.

Nothing in Inspector, Aligner, Scout, Chunker, or Searcher changes. `ToolName`,
`ResultType`, and the `supports` map are the three union types that gain a member,
and each is `satisfies`-checked or exhaustively switched, so a missed site fails to
compile rather than at runtime.

## 10. Interface

### What is shared, and must not be re-implemented

`ConfigurationShell`, `ContextFields`, `SourceTypeField`, `ConfigSelect`,
`RunPanel`, `CollapsibleCard`, `PriorityPanel`, `FinalResultActions`,
`BlockReferenceId`, the `document-trace-panel.tsx` primitives, and `SignalHelp`. A
reader who learned the question-mark affordance in Inspector already knows it here.

One thing to promote rather than copy: `SectionHeading` is currently a local
function inside `web/app/inspector/page.tsx`. Expert is its second consumer, and
`AGENTS.md` says to move a mechanic to shared on the second consumer, not the
third. Lift it to `web/components/ui/` rather than writing a near-identical one.

**Use `PriorityPanel`.** It is the panel every tool opens with, and it does not
decide priority — a tool passes items already selected and already ordered, with
`orderNote` stating the rule. Expert's items are the `absent` questions in bank
order, and the note is *"In the order the question bank asks them."* Refusing the
shared panel because "priority implies weights" would be the drift; the panel
exists precisely so no tool invents its own opening.

The selector lives in `web/lib/expert-priorities.ts`, as Inspector's and Scout's
do, so changing what qualifies touches one file in `lib` and no component.

### Bespoke to Expert

The gate selector, the labelled context rows, the five-state vocabulary in
`web/components/expert-signal-help.tsx`, and the state panels below.

### What is shown where

**Top, always visible** — one line of counts that sums to the total:

```
End of Phase 1 · vaccine · iTPP, cTPP, IPDP

23 answered   14 gaps   31 for reviewers   8 need the IPDP   4 not applicable
──────────────────────────────────────────────────────────────────────── 80
```

Five numbers is more than one, but they add to 80, which makes the row
self-verifying, and it is the line that gets screenshotted into a deck.

**No composite coverage score.** "62 of 80 addressed" blends states that mean
different things — "the document says it" and "an SME will answer it" — and would
tell a governance committee something untrue. Same reason Scout refuses to blend
its axes.

**Opened by default:** `PriorityPanel` with the gaps, then the **Gaps in the
documents** panel. That is the only list anyone acts on immediately.

**Collapsed, with the useful number visible in the header:**

- **For the reviewers** — per-discipline counts in the collapsed state, because
  reading "Drug Safety 5" is how a PPL knows who to invite.
- **Answered** — split as *"19 cited to a passage · 4 from supplied context."*
  That split is the number worth seeing: a review answered mostly from pasted
  context is a different situation from one answered from the documents, and the
  interface should make it visible without editorialising.

**Conditional, appears only when a document is missing:** *"8 questions need the
IPDP, which wasn't uploaded."* No empty panel when nothing is missing.

**A number in the header and nothing else:** `not_applicable`. It is in the
denominator so the arithmetic works; it is never a panel, because it is not a
shortfall.

**Granular, on expanding one row:** the full question text, the statement, and the
provenance line.

```
Source:  IPDP · block ipdp:214
Source:  CMC Development Report · no block reference
```

Same field, same position, same weight. Symmetric rendering is what stops a
transient answer reading as a warning: it *was* addressed, it just cannot be
checked from the file.

### Ordering

The bank's own order — discipline sequence, then question number. Nothing
re-ranks. Same rule Inspector holds: the author's sequence is the order, so there
is no weighting anyone can argue with and two runs on one gate compare line by
line.

## 11. Decisions not to relitigate

- **Triage, not answering.** Roughly a quarter of the bank is document-answerable.
  The rest is operational (*"has the procedure been tested?"*) or judgment
  (*"would we fund this today?"*) and no document contains it.
- **Bank transcribed to YAML, not parsed from prose.**
- **Applicability and answerability decided at authoring, not per run.** Otherwise
  the same question lands in different buckets on different runs.
- **Transient input is prompt-only, label stored, text never.**
- **No reconciliation or deduplication stage.**
- **Five states, denominator never shrinks, counts derived.**
- **Gate is a run parameter, not a header field.** No header amendment.
- **Canonical input stays DOCX and PPTX.** `AGENTS.md` refuses PDF as a document
  source because a table reconstructed from geometry can merge unrelated columns
  into a block whose text still passes exact-quote validation. Study reports and
  regulatory minutes are overwhelmingly PDFs — that is what transient input is
  for, and widening the format set is reopening a decision made for a good reason.

## 12. Open questions

**Before writing any config:**

1. **Are LCS / PCD / FIH / EOP1 / EOP2 / DTF / DTL the Foundation's gates?** These
   are industry development gates. If BMGF's stage-gate process uses different
   names or boundaries, the gate axis needs a mapping decided before seven config
   files exist. There is also an existing `ghide-stage-gate-evaluator` whose gate
   vocabulary should be checked against this one.
2. **Measure the buckets first.** Take one real investment's iTPP, cTPP, and IPDP,
   take one gate's 80 questions, and hand-sort them. If 20 are answerable you have
   a tool. If 4 are, you have a routing list — still useful, but a different
   product, and worth knowing before building.
3. **The bank is drug and biologic shaped** — BCS classification, DART,
   carcinogenicity, ICH M7. A diagnostic or device needs its own bank. That maps
   onto `intervention_class` cleanly, but 560 is one family's bank, not the matrix.

**Product:**

4. Do Stage Gate Notes and Meeting Notes belong in Expert's input set? They were
   scoped as context-only earlier, but for this tool prior-gate commitments are
   arguably the most relevant auxiliary source. Worth asking Janet rather than
   deciding.
5. Should a discipline filter exist as a second run parameter, so a CMC reviewer
   can run their own ten? Cheap once the bank exists; do not build speculatively.
6. Who owns keeping the bank current as guidance moves? A question authored
   against a superseded ICH version is exactly the failure the bank itself warns
   about at `NC.EOP2.9`.

## 13. What exists

| Concern | File |
|---|---|
| Bank, states, resolution, config loading | `services/expert/models.py` |
| Structural contract | `services/expert/contract.py` |
| Run | `services/expert/pipeline.py` |
| One model call | `services/expert/stages/assessor.py` |
| Published prompt | `services/expert/prompt_catalog.py` |
| LCS bank | `services/expert/configs/bmgf_lcs.yaml` |
| Service docs | `services/expert/README.md` |
| Route and gate list | `api/routes/expert.py`, registered in `api/main.py` |
| Wire shapes | `api/schemas.py` (`GateReviewOut` and below) |
| Document support | `api/routes/configs.py` — `supports["expert"]` |
| Types, fetchers | `web/lib/api.ts` |
| Envelope | `web/lib/result-file.ts` — `ANALYSIS_VERSIONS.expert: 1` |
| Readability | `web/lib/result-contracts.ts` — `assertExpertReadable` |
| Selectors and counts | `web/lib/expert-priorities.ts` |
| Page | `web/app/expert/page.tsx` |
| Vocabulary popovers | `web/components/expert-signal-help.tsx` |
| Shared heading | `web/components/ui/section-heading.tsx` |
| Ask | `services/assistant/legends.py` — `EXPERT_LEGEND` |
| Docs graph | `shared/product_knowledge.json` |
| Invariants | `AGENTS.md` — `### Expert` |
| Intervention vocabulary | `shared/vocabulary.py` — `intervention_classes()` |

Tests: `tests/test_expert.py` (bank, validation, resolution, contract, assessor,
catalog), `tests/test_expert_route.py` (every guard fails the request rather than the
stream), `tests/test_expert_pipeline.py` (a real DOCX end to end through chunker, the
assessor, and the contract), and `web/lib/expert-priorities.test.ts` (the counts sum
to the total, and missing documents are read from the questions rather than a
hardcoded list).

## 14. What is left

### 1. Calibrate `answerable_from` against a real investment

This is the one thing that needs a domain reviewer rather than an engineer.

Every question carries two authoring judgments, and a wrong `answerable_from` is a
silent wrong answer: mark a question answerable that no TPP or IPDP could ever answer
and the run reports `absent`, which reads as "the grantee should have written this"
for something no document carries. The rule applied throughout, stated at the top of
`bmgf_lcs.yaml`:

- `itpp` / `ctpp` — target product attributes: population, efficacy, dosing,
  presentation, stability, price, delivery
- `ipdp` — plan, timeline, study intent, regulatory pathway, access strategy,
  governance, stopping criteria
- none — experimental results, process chemistry, operational verification, judgment

What that produces today, for a vaccine with all three documents uploaded:

| Gate | Assessed | Routed | Not applicable |
|---|---|---|---|
| LCS | 43 | 24 | 13 |
| PCD | 48 | 23 | 9 |
| FIH | 43 | 32 | 5 |
| EOP1 | 48 | 22 | 10 |
| EOP2 | 60 | 12 | 8 |
| DTF | 33 | 42 | 5 |
| DTL | 52 | 25 | 3 |

Two of those shapes are worth understanding rather than "fixing". **CMC at LCS is
entirely routed**, because a TPP carries presentation, stability and price *targets*
while an IPDP carries plans, and neither carries process chemistry or a bottom-up
cost model. **DTF is the most routed gate**, because almost every question there asks
whether a dossier module, validation or inspection readiness exists — and the dossier
is not among Expert's inputs.

Take one gate and one real iTPP/cTPP/IPDP, hand-sort the questions, and compare
against what `resolve_questions` predicts. The config is where these judgments live
precisely so a reviewer can change them without touching code.

### 2. Two questions to verify against the SME original

`CMC.LCS.2` and `CMC.LCS.3` carry a `VERIFY AGAINST SOURCE` comment in the bank. The
document supplied ran them together mid-sentence, so the tail of one and the head of
the other were lost; both are transcribed from the surviving fragments and are the
only two questions of the 560 not taken verbatim.

### 3. `COORDINATION_MAP.md` is not transcribed

The SME document references it for topic ownership. Discipline ownership is already
carried — every question sits under the discipline that owns it, and routing reads
that — so nothing is broken. What is missing is the map's account of *why* two
disciplines touch the same subject from different angles. If that reasoning should be
visible to a reviewer, it belongs beside the banks as config.

### 4. Deferred deliberately

- **A discipline filter** as a second run parameter, so a CMC reviewer can run their
  own ten. Cheap now that the banks exist; not built speculatively.
- **Banks for diagnostics and devices.** These seven are drug and biologic shaped —
  BCS classification, DART, ICH M7 — and `applies_to` marks those questions
  accordingly, so a diagnostic run returns more `not_applicable` than a vaccine one.
  A diagnostic bank is its own transcription, keyed the same way, and no code changes
  to accept it.
- **Who keeps the banks current** as guidance moves. A question authored against a
  superseded ICH version is exactly the failure the bank warns about at `NC.EOP2.9`.
