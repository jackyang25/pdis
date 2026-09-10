# Inspector: multiple authored rubrics over one document

Date: 2026-09-09

Status: researched design for approval; no runtime implementation or regulatory validation claimed.

## Outcome

Keep iTPP, cTPP and IPDP as the document inputs. Resolve an ordered set of rubric
definitions from the input configuration. Parse and label the source once, assess
each selected rubric independently, and display every result with one shared
section-and-unit viewer and one Documents view. Preserve the existing BMGF
assessment behavior and its source blocks.

ICH-derived requirements are PDIS-authored document-review expectations informed
by named ICH clauses. They are not official ICH templates for iTPP/cTPP/IPDP,
certification, approval predictions, or a review of actual trial conduct.

## Research and source versions

Official sources examined for scope and candidate requirements:

1. [E6(R3), Principles and Annex 1, adopted 6 January 2025](https://www.ema.europa.eu/en/documents/scientific-guideline/ich-e6-r3-guideline-good-clinical-practice-gcp-step-5_en.pdf).
   Use the scope, proportionality principles, and Annex 1 sections 3.1 and 3.10.1
   for an initial clinical-planning review. The scope includes investigational
   medicines, vaccines and biological products. Do not demand site records,
   executed consent forms or complete protocols in a high-level development plan.
2. [E4, adopted 10 March 1994](https://database.ich.org/sites/default/files/E4_Guideline.pdf).
   Relevant anchors are section I (dose choice, concentration-response, time),
   section II (development strategy), and section III (study designs). The
   document addresses benefit and adverse effects across doses and recognizes
   multiple designs. Do not mandate one design, numeric dose or therapeutic
   monitoring for every product.
3. [E14, adopted 12 May 2005](https://database.ich.org/sites/default/files/E14_Guideline.pdf).
   Sections 1.2-1.3 establish product-specific QT evaluation and scope, including
   systemic availability and the focus on non-antiarrhythmic drugs. Sections
   2.1-2.4 concern the evaluation strategy and its implications for later trials.
4. [E14/S7B consolidated Q&As, 21 February 2022](https://database.ich.org/sites/default/files/E14-S7B_QAs_Step4_2022_0221.pdf).
   E14 Q&As 5.1 and 6.1 describe concentration-response and integrated approaches;
   6.3 discusses large targeted proteins and monoclonal antibodies. A dedicated
   thorough-QT study is not a universal requirement. Do not label older Q&A 5.1
   or 6.1 text current when the 2022 revision replaces it.

[EMA's E6 version history](https://www.ema.europa.eu/en/ich-e6-good-clinical-practice-scientific-guideline)
distinguishes the effective Principles/Annex 1 from Annex 2, adopted in 2026 with
an EU effective date of 15 January 2027. Pin the initial review to the named 2025
package, not an ambiguous "latest E6". Organization is not jurisdiction, and
PDIS does not make a jurisdictional compliance claim.

The source BMGF templates are not present in the tracked repository. The
existing YAML definitions and their `mirrors` pointers are available. Preserve
their content; do not claim their fidelity to inaccessible originals was verified.

## Proposed requirement-to-document mapping

These are PDIS adaptations, not instructions issued by ICH for these documents.
The first release is deliberately a selected scope, not exhaustive guideline
coverage. The published rubric must say so.

| Family | iTPP | cTPP | IPDP |
| --- | --- | --- | --- |
| BMGF | Existing rubric unchanged | Existing rubric unchanged | Existing rubric unchanged |
| E4-derived | Regimen intent and relationship between desired effects and tolerability; qualitative goals allowed | Candidate dose/regimen rationale and stated evidence gaps; a proposed dose is not proof of completed studies | How planned dose/exposure-response work will support regimen selection, including effects over time |
| E6-derived | No separate GCP review: a target profile is not a trial plan | No separate GCP review for the same reason | Documented clinical-planning basis and critical-to-quality risk management at strategic-plan depth |
| E14-derived | No candidate-specific QT assessment for a candidate-agnostic profile | Candidate QT-risk evidence summary and unresolved evaluation needs, when applicability is established | Proposed QT-evaluation approach and connection to later clinical safety planning, when applicability is established |

Author atomic units with stable IDs. Where an adaptation contains independent
requirements, split them before publication rather than returning several
verdicts for a compound unit. Each unit carries an explicit source locator,
its PDIS expectation, and an explanation of the document-level adaptation.
Related content in different rubrics is not silently deduplicated: their
authorities remain separate. Do not repeat the same obligation in multiple units
within one rubric merely because several clauses support it.

## Applicability: do not infer missing product facts

The existing selectors identify organization, intervention class, document type
and indication. They do not establish systemic availability, small-molecule
status, antiarrhythmic purpose, or trial stage.

Recommended initial configuration policy:

Candidate selection is intersected with document configurations already
supported by both Chunker and Inspector. Do not introduce an otherwise unsupported
document/intervention combination merely to activate a guideline review.

- E4-derived profiles initially cover `drug` and `monoclonal_antibody`, with
  document-specific wording. Other modalities remain outside the implemented
  review scope, not declared exempt from ICH.
- E6-derived profiles cover IPDP for drug, vaccine and monoclonal antibody
  development. They inspect plans, accepting future actions; they do not require
  studies to have started or finished.
- E14-derived profiles initially cover drug cTPP/IPDP only after explicit
  confirmation of small-molecule, systemic-exposure, non-antiarrhythmic scope.
  This is a deliberately narrow PDIS implementation scope, not a restatement of
  E14's entire scope.
- For the E14 candidate profile, collect those three product facts through
  Inspector-owned controls using the shared configuration-field primitives.
  Each accepts yes/no/unknown. Unknown never becomes no by default. Do not parse
  the indication label or use keyword heuristics to set these facts.
- Resolve every candidate review to `included`, `outside_review_scope` or
  `needs_context`, with a reason code and explanation. This is run-scope
  metadata, not a model verdict. Retain excluded and unresolved candidates in
  saved results and visibly disclose them. Other resolved reviews may run, but
  unresolved applicability must not be described as complete guideline coverage.
- Do not reuse the assessment's existing `optional` or `not_applicable` meaning
  for an unresolved product-applicability decision.

This introduces product-fact controls, not a manual rubric selector. The user
still gets all reviews resolved as applicable by configuration.

## Code findings that determine the design

`services/inspector/models.py` currently combines rubric content and the
`(org, source_type, intervention_class)` lookup. `pipeline.run_pipeline` also
uses that same configuration to choose Chunker's labeling taxonomy.

`stages/assessor.py:assess_document` groups blocks by their exact
`section_label`, then treats a rubric section without matching blocks as absent
without a model assessment. `contract.py` requires mapped blocks to bear the
rubric section's label. Therefore adding an ICH YAML alone would fabricate
missing sections: guideline topics do not share BMGF's section names.

The section viewer itself iterates generic sections and units, but source
mapping and presence labels are not generic yet. A guideline-topic container
must never say the document lacks a section merely because the topic is not a
physical heading.

The route, schema, portable result builder, session, priorities, trace projector
and Assistant currently consume one `inspection`. They must migrate together;
updating only the page or only the pipeline leaves incomplete consumers.

## Architecture

### Configuration ownership

```text
services/inspector/configs/
  profiles/       # input triple -> document config + ordered rubric references
  rubrics/
    pdid/         # existing authored template content, preserved
    ich/          # E4-, E6- and E14-derived document-review rubrics
```

Folders organize authoring only. No runtime branch examines `bmgf`, `ich`, `e4`,
`e6` or `e14` to choose an engine. Each rubric has identity, revision,
display name, scope description, source metadata, ordered sections/units,
document framing and an explicit evidence-scope mode. Profiles reference pinned
rubric revisions; they do not duplicate rubric content. The source revision and
PDIS rubric revision are distinct facts.

Move configuration loading/selection to a focused Inspector module. `models.py`
owns the shared shapes. Validate references, unique IDs, enums, and applicability
facts at catalog load; malformed definitions fail loudly. Preserve the public
package boundary. Do not modify Chunker taxonomy to accommodate rubric topics.

### Evidence and assessment

Use one assessment function with an explicit evidence selection boundary:

- `mapped_section`: existing BMGF sections receive the same labeled blocks as
  today, preserving the established behavior.
- `whole_document`: guideline requirements can read all retained blocks,
  including blocks labeled Other or Metadata. Their citations identify the
  actual evidence; a rubric-topic heading is not a source-document heading.

Both modes call the same schema-bound per-unit assessor, with one unit per
request. They differ only in which evidence is supplied and the authored
framing. No RAG, graph, new external search or provider branch is required.
If full evidence exceeds a supported request budget, fail explicitly rather
than silently truncate it and claim absence. Preserve image IDs and bytes.

Keep existing BMGF parse mapping distinct from assessed citations. Guideline
section containers have no inferred physical-section presence. Trace placement
uses cited blocks only, never an invented mapping. A missing unit has no mark.

Run the current document consistency pass once using the existing document
taxonomy, not once per rubric. Store it at document-run scope so it is not
counted repeatedly or presented as ICH's verdict. Cross-rubric requirements
disagreeing is not a document contradiction.

### Result contract

One document-run result owns context tags, applicability facts and resolutions,
source blocks, the document consistency result, and an ordered `reviews` list.
Each review owns rubric identity/revision/source snapshot and its sections and
unit assessments. Each applicable unit appears exactly once within its review.
Use review-qualified unit IDs wherever identities share a namespace (trace,
priorities, selection and Assistant references).

Freeze the effective requirement text and source locators in the result so a
saved assessment can be interpreted without fetching today's YAML. Reuse source
blocks once, not one copy per rubric. Do not persist multiple representations
of verdicts or a blended score. Preserve current assessment failure behavior:
a failed required assessment prevents final emission, not a missing review
disguised as success. Applicability-unresolved is separate from execution failure.

Version Inspector's portable analysis contract independently. At import only,
wrap old Inspector results as a single legacy review, preserving IDs and
provenance and explicitly marking unavailable rubric revision metadata unknown.
Never assign today's rubric revision to a historical result. No legacy runtime
assessment branch. Other tools' saved-result versions remain unchanged.

### Shared presentation

Keep one reusable Inspector section/assessment renderer. An accessible review
selector switches completed rubric results; it is not an input selector. Use
the existing controls, spacing, verdict vocabulary and trace components.
Section expansion behavior is shared. Show rubric sources and adapted scope
without repeating a large disclaimer beneath every unit.

Keep one Documents view. Selecting another rubric changes the annotation layer,
not the underlying document or block IDs. Keep a visible account of unresolved
and excluded reviews. Priority selection and its derived digest are scoped to
the selected rubric; cache identity includes the review ID. Document consistency
stays a separate document-level view. Assistant receives every review with its
authority and scope, not only the one currently visible.

### Transport and boundaries

Create the Inspector application operation under `api/operations/` and make the
HTTP adapter delegate request/result composition to it. Do not add an Inspector
MCP tool as part of this change; the operation makes later transport reuse
possible. Provider composition remains in API; services remain stateless.
The new product facts are Inspector-local and do not alter Screener or other
tools' context semantics. Preserve DOCX/PPTX-only Inspector uploads.

## Verification required before shipping

- Golden configuration checks: all BMGF units, order, text, optional flags and
  stage framing survive the migration without changes.
- Deterministic fake-client fixtures: BMGF evidence scopes, per-unit requests,
  verdicts and citations match the old path; parsing occurs once for many reviews.
- Guideline evidence in an unrelated physical section is still assessed and
  cited; missing guideline-named headings never cause automatic missing results.
- Applicability yes/no/unknown truth tables, absent facts, invalid enums, and
  incomplete contexts cannot silently include or exclude E14.
- Section mode and citation checks, duplicate IDs/revisions/references,
  unknown citations and missing unit responses fail as intended.
- Colliding unit names in two rubrics remain distinct in trace, priorities and
  Assistant; consistency is run and counted once.
- Round-trip new portable results with all source metadata and retained images;
  import legacy results without inventing a revision or rewriting provenance.
- Shared viewer renders one and multiple reviews, unresolved scope notices,
  keyboard selection and passage reveals at desktop and mobile widths.
- Backend tests, frontend tests, typecheck, lint and production build.

No live external model calls or deployment/push are implied by design approval.
Representative source-document trials are needed to evaluate assessment quality;
schema and UI tests alone cannot establish scientific validity.

## Decision before implementation

Approve this concrete scope, particularly the three explicit E14 product facts,
the exclusion of a separate E6 review for target profiles, and the distinction
between ICH source requirements and PDIS document-level adaptations. These
details were not established by the earlier high-level discussion. The next
artifact is a task-by-task implementation plan; the architecture skill requires
review of this written design before runtime changes.
