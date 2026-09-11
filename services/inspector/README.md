# Inspector

One product-development document against every rubric resolved by its configured profile.

## Background

Inspector measures document quality, not investment merit. It does not assign
program risk, validate real-world feasibility, recommend funding, or search
external evidence.

Inspector judges one document independently against authored rubrics. Comparing two documents
against each other is Aligner's responsibility; the two tools have different
comparison targets and neither substitutes for the other.

## Usage

Import pipeline entry points, result and config models, config lookup, and
serializers from `services.inspector`.

## Contract

| Direction | Value |
|---|---|
| Input | One document, a profile, explicit applicability facts, indication, and an injected model client |
| Output | Shared blocks and consistency findings, rubric resolutions, and one peer review per included rubric |

There is one published atom. An **`Assessment`** is one rubric unit and how it
stands: one `verdict`, one `statement` saying what is wrong, and the exact blocks it
was read from. A unit *is* its assessment — there is nothing nested inside it — so a
unit cannot carry two answers to one question.

Every section holds at least one unit: a section with variables contributes one
unit per variable, and a section without them is itself one unit whose
`variable_name` is `None`. There is no prose-versus-table branch for a consumer to
get wrong.

## One vocabulary

`VERDICTS` is the whole vocabulary, declared worst-first after `specified`, in
`models.py`:

| Verdict | Meaning |
|---|---|
| `specified` | the rubric asks for this and the document supplies it usably |
| `not_present` | nothing is there |
| `placeholder` | a token such as `<<TBD>>` sits where the value belongs |
| `insufficient` | present, but part of what the requirement asks for is absent |
| `vague` | covers the requirement, but is unusable as stated |
| `section_conflict` | two sections state claims that cannot both hold |
| `not_applicable` | the rubric accepts absence here and the document omits it |

`insufficient` and `vague` are not degrees of each other, and the prompt states the
test rather than leaving it to two adjectives: **coverage first, then usability.** Is
any part of what the requirement asks for absent? Then `insufficient`. Only if the
content covers the whole requirement and is still unusable is it `vague`. A unit that
is both is `insufficient`.

**One axis, and there is no second one.** There used to be three over the same fact:
a `reason` the model chose, a `level` that was a lookup on the reason, and a `status`
that bucketed the levels into three. The second carried nothing the first did not,
and the third re-expressed the second in different words — so a reader saw
"Insufficient" on a finding and "Not met" on the unit above it and had no way to know
those were one judgement said twice. The keys collided too: the reason `unmet`
rendered as "Insufficient" while the status `not_met` rendered as "Not met".

There is no `recommendation` either. It restated the statement as an imperative —
"Vial size is not specified" beside "Specify vial size" — and the web layer had grown
a guard to hide one of the two. Where the imperative carried something the statement
did not, which was one case, the fact moved into the statement.

There is no `off_template` either, and it was the last value that did not belong. It
named a deviation in structure or naming, which is a different question from every
other verdict: the rest ask what the content says, that one asked what shape it was
in. A unit that was both misnamed and unmeasurable had to be filed as one of them, and
the other fact was lost. A layout that costs a reader something now shows up as
`insufficient` or `vague` on its own merits; a layout that costs them nothing is not
Inspector's business.

`not_applicable` comes only from the rubric's `optional` flag: whether absence is
acceptable is the author's decision, never the model's, and `Assessment` refuses it on
a required unit rather than trusting the reply. Left ungated, a model could drop a real
shortfall out of the worklist by calling it not applicable.

Conformance language throughout, deliberately not severity language. Inspector
knows what the rubric asked and what the document supplies; it does not know what
a shortfall costs a given programme, so it does not claim one. There is no letter
grade and no overall score.

## How a unit is assessed

**One model call per unit, and one verdict back.** That replaced three calls per
unit — completeness, adherence, and rigor — which cost three times the requests and
could each report the same defect under its own axis. Merging them also removed the
naming split that came with it, where one axis was `adherence` in the data and
"Template adherence" in two interfaces.

All included rubrics share one bounded unit-work queue per document run (24
concurrent unit calls maximum), using `shared.batching.map_ordered`. Work is
interleaved across rubrics so a large template does not hold up every guideline.
There are no nested rubric or section worker pools. Single-rubric entry points
use the same queue. Progress counts completed units once across the whole run;
result order remains the authored rubric/section/unit order. Retries stay inside
their unit's worker slot. Parsing happens once before assessment and consistency
once afterward. A failed unit aborts publication rather than returning partial
reviews; already-started independent work may finish before the error returns.

The reply is one object, not a list of them. A list let a unit come back with several
answers to one question, so every layer above had to reconcile them into the one
thing a row can show.

`not_present` and `not_applicable` are the only verdicts that cite nothing, and the
only ones exempt from citing. Every other verdict names the block it was read from —
including `specified`, which is a claim about content someone saw. The parser
enforces this so a bad reply gets the retry; `contract.py` enforces it again for an
imported result.

A unit nobody assessed is refused rather than filled in. The assessor makes one call
per unit, so a missing answer is a failed call, and "not checked" reading as "nothing
wrong" is the one mistake this tool cannot make.

Ordering is the verdict's place in the vocabulary above, then the sequence the rubric
author wrote. That is the only
authored priority signal in the system, and it costs nothing: it replaced a
per-section `weight` that nobody calibrated, had one consumer, and sat in eleven
configs.

`assessment_status` and `consistency_status` report whether the run completed. They
are process facts kept outside the assessment, because "not checked" must never
read as "nothing found". A failed unit stops the run, so a partial assessment
cannot become a downloadable result; the cross-section pass is additive and reports
its own failure instead.

## Layout

| Module | Owns |
|---|---|
| `models.py` | shapes and the published vocabulary |
| `configuration.py` | input profiles, rubric references and configuration lookup |
| `assembly.py` | the join of rubric and verdicts, and the ranking |
| `stages/assessor.py` | what the model is asked, and what is accepted back |
| `contract.py` | the deterministic checks, on a fresh or imported result |
| `pipeline.py` | the order those run in |

## Profiles, rubrics and sources

`configs/profiles/catalog.yaml` maps an `(org, source_type,
intervention_class)` input to an ordered set of pinned rubric definitions. It also
declares applicability as allowed values for explicit product facts. Missing or
`unknown` facts produce `needs_context`; confirmed non-matches produce
`outside_review_scope`. Neither indication nor document prose supplies these facts.

`configs/rubrics/` owns rubric identity, PDIS revision, authority, selected scope,
evidence mode, sources and source-referenced requirements. ICH-derived definitions
are PDIS-authored document-review adaptations, not official templates,
certification, trial-conduct audits, or exhaustive guideline coverage. Source
revision and PDIS rubric revision remain separate in every saved snapshot.

Shared rubric definitions declare no `org`, `source_type`, or `intervention_class`.
`load_rubric` requires a profile and supplies its context before parsing the runtime
assessment config; context fields in a shared definition are rejected, not overridden.
Class-specific PDID template files retain their real document identities, which must
match the referencing profile. The catalog owns applicability; a shared ICH rubric
does not pretend to be a drug template merely to satisfy the config parser.

Each rubric definition also declares a quoted ISO `updated_on` date (YYYY-MM-DD).
This dates the PDIS-authored rubric, not publication or review of its external sources.
The initial baseline is 2026-09-11; earlier update dates were not recorded. When
assessment rules change, bump `revision`, update `updated_on`, and update the
profile catalog's revision pins together. Presentation-only changes do not bump
either. The shared PDID definition versions its profile-specific requirement files
as one family. Source guideline revisions remain in `sources`.

Results snapshot the rubric revision and date. The selector shows the saved revision
and the date beneath it; opening an older result never substitutes current metadata.

### Selected ICH coverage

The catalog adds planning adaptations, not ICH-authored iTPP/cTPP/IPDP templates.
Each requirement links to the source sections used to author it. Source guideline
copyright belongs to ICH; these adaptations are not endorsed by ICH. Revisions are
pinned rather than following a changing web page automatically.

| Guideline family | Document profiles | Selected subject matter |
| --- | --- | --- |
| E4 | Drug/mAb iTPP and cTPP; drug IPDP | Dose-response intent and planning |
| E6(R3) | Drug/vaccine IPDP | Clinical planning and critical-to-quality risks |
| E14 | Drug cTPP/IPDP, explicit product facts | QT/QTc planning |
| E8(R1) | Drug/vaccine IPDP | Development sequence, intended populations, patient input |
| E9/E9(R1) | Drug/mAb/vaccine cTPP; drug/vaccine IPDP | Treatment-effect targets; statistical and estimand planning |
| E10 | Drug/mAb/vaccine cTPP; drug/vaccine IPDP | Comparison basis and control-strategy rationale |
| Q8(R2) | Drug iTPP/cTPP/IPDP | Quality target intent through pharmaceutical-development planning |
| Q9(R1) | Drug/vaccine IPDP | Pharmaceutical-quality risk assessment, controls and review |
| M3(R2) | Drug IPDP, confirmed small molecule | Nonclinical support for clinical progression |

E14 requires confirmed small-molecule status, systemic exposure, and a non-antiarrhythmic
purpose. The M3 adaptation requires only confirmed small-molecule status; unknown
facts leave the review visibly unassessed. This is narrower than M3's complete scope,
which also discusses timing for biotechnology-derived products while referring their
study selection to S6. No indication-name or document-text inference supplies facts.

Q8 starts conservatively with drug profiles; its principles may be useful elsewhere,
but this catalog does not claim a reviewed biologic/vaccine adaptation yet. Q9 explicitly
covers biological products and is about pharmaceutical quality, not investment risk.
Devices and diagnostics receive no pharmaceutical ICH reviews. There is currently no
mAb IPDP profile to extend. Clinical-protocol detail is not required of a cTPP; an iTPP
does not owe a finished formulation or quality dossier. Q8's quality target product
profile is only a pharmaceutical-quality subset, not another name for an iTPP/cTPP.

Additional independent rubric units add model calls, using the same bounded queue.
They do not trigger extra parsing or document-consistency passes. Reviews remain
separate even where source principles overlap; no combined compliance score is produced.
S6, E11/E11A, E17/E5 and M12 are not included in this expansion: they need their own
reviewed adaptations and, where necessary, explicit applicability facts.

```text
configs/
  profiles/catalog.yaml
  rubrics/
    pdid/pdid.yaml                # shared template-rubric metadata
    pdid/pdid-ctpp-drug.yaml       # template requirements by document and class
    ich/ich-e4-ctpp.yaml           # guideline-derived requirements
```

`org: bmgf` identifies the input organization; PDID and ICH identify assessment
authorities. Profiles reference both explicitly. Filenames use hyphens, while
input keys retain underscores (for example `monoclonal_antibody`). Lookups follow
profile references, never infer rubric filenames from organization keys.

PDID requirement files retain their assessment content. `pdid/pdid.yaml` supplies
shared metadata and references the profile's template file. Existing `type_key`
values and the published rubric ID `bmgf` remain stable for result provenance;
they are identifiers, not filename rules. The optional `reference_url` points to
the employee reference-library landing page, not a direct template or a verified
requirement-level citation. Template basis (`mirrors`) and specific guideline
citations remain distinct and travel with the saved rubric snapshot.

The result's **Rubric** selector uses authority-first labels. Its shared label help control
holds scope, revision, sources and a link to the current assessment documentation; **How to read**
explains result vocabulary. Requirement disclosures reuse the same source presentation
in the section view and document sidebar. Historical results retain their saved labels
and source metadata; opening them does not attach newer provenance.

## Where a PDID template rubric comes from

A rubric mirrors an authored source template for its **structure**: the section
list, the unit names, and the column conventions. Each config records which source
in its `mirrors:` field, and that field is published to the in-app docs page beside
the prompts, so "is this the official template" is answerable from the file rather
than from memory.

Everything that makes a rubric *assessable* is authored here and is not in the
source template: each unit's `description`, the `stage_guidance`, the `optional`
flags, and the `expectations`. When the source template changes, the mirrored half
needs re-syncing; the added half is maintained in this repository.

`mirrors:` is a pointer, not a drift check. The source template lives outside the
repository, so nothing here can verify it — which is precisely why the field exists:
it names what to go and check.

## Development

PDID rubrics live in `configs/rubrics/pdid/pdid-<document>-<intervention>.yaml`. A section and a
variable declare the same four things — `name`, `description`, `optional`,
`expectations` — so there is one schema to learn; a section adds only `variables`.
Set `optional: true` where the rubric genuinely does not require a unit.
`expectations` is read into the prompt verbatim. Independent authorities belong in
separate rubric definitions and reviews; expectations remain the assessment bar for
one requirement.

`mapped_section` evidence preserves BMGF's physical section mapping.
`whole_document` evidence lets guideline requirements read every retained block,
including Other and Metadata, without claiming the document physically contains a
guideline-named section. Whole-document section presence is therefore `null` and
its citations are checked against the shared block collection.

`VERDICTS` is declared once in `models.py` and mirrored in `web/lib/api.ts`, bound by
`inspector-vocabulary.test.ts` — which also fails if a second axis grows back.

Inspector consumes Chunker only through `services.chunker` and never searches
external evidence.
