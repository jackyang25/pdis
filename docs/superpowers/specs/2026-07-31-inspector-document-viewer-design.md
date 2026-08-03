# Inspector Document Viewer Design

## Purpose

Give Inspector a document-centered view of its own results, reusing the shared
document trace viewer that Scout already uses. The view answers one question the
existing Overview, Sections, and Consistency tabs cannot: *where in my document
are the problems?* It creates no new analysis and changes no result contract.

## Scope

- One Inspector trace adapter projecting existing `InspectionResult` lineage into
  shared annotations.
- Four layers matching Inspector's contract: completeness, adherence, rigor, and
  cross-section consistency.
- Whole-block emphasis carrying a grade, because `block_ids` is Inspector's true
  granularity.
- Section-anchored display for findings that have no document lineage.
- An Inspector-specific inspector panel.
- Two additive, tool-neutral fields on the shared annotation contract, plus a fix
  for annotations that currently orphan.

Aligner is out of scope. Its two-document trace raises layout questions that
deserve their own design.

## Non-goals

- New grades, issues, recommendations, or lineage. The adapter is a projection.
- Changing `InspectionResult`, the API, or the result envelope.
- Exact-span text highlighting. Inspector carries no quotes; synthesizing spans
  by matching variable names against block text would invent provenance the model
  never asserted.
- Replacing the Sections tab. That tab owns the complete rubric ledger; this view
  owns location.

## Why Inspector cannot reuse Scout's presentation directly

Scout carries `document_spans` with exact quotes, which is what produces text
highlighting. Inspector carries only `block_ids`. A naive adapter would therefore
produce a document in which nothing is highlighted and every annotation is a
margin marker — correct, and useless.

Two consequences drive this design:

1. **Emphasis is the block, not a span.** A grade addresses everything the block
   contains, so the block is tinted as a whole. This is honest about precision
   rather than implying a span the result does not claim.
2. **Inspector's most valuable finding has no location.** A missing variable is an
   absence, and `AGENTS.md` requires that absent content never carry an invented
   citation. Absences are therefore *anchored* for display without becoming
   provenance claims.

## Shared contract additions

Both fields are optional, so Scout's adapter and output are untouched. Neither is
Inspector-specific.

```ts
/**
 * Whole-block emphasis for an annotation whose granularity *is* the block.
 * Spans address text; a block-level judgement addresses everything in the block.
 */
emphasis?: {
  tone: "neutral" | "caution" | "danger";
  /** Short text carrying the precise claim, e.g. a grade letter. */
  badge?: string;
};

/**
 * Where to *display* an annotation that has no document lineage. Never a
 * provenance claim: `blockIds` stays empty and the viewer renders the annotation
 * beside the anchor without attaching it to the block's text.
 */
displayAnchorBlockId?: string;
```

`tone` is semantic rather than a numeric severity, because a numeric range would
encode Inspector's A–F scale into a contract Scout also uses. Three tones map to
the existing `--tone-neutral`, `--tone-warning`, and `--tone-danger` variables,
so a failing grade inherits the rule that a negative *result* uses
`--tone-danger` while `--destructive` remains reserved for system errors.

Colour is never the only signal: `badge` carries the exact grade as text.

### Invariant

An annotation carrying `displayAnchorBlockId` declares no block lineage. A test
enforces this, because prose will not.

### Orphan fix

`buildDocumentTrace` currently drops an annotation whose `blockIds` and `spans`
are both empty: it appears in `annotations[]` but is reachable from no segment,
marker, or unresolved group. Verified by probe. Such annotations are now placed
in one of two groups:

- **anchored** — a valid `displayAnchorBlockId` resolves to a retained block;
- **unplaced** — no anchor, or an anchor naming an unknown block.

`unplaced` is distinct from the existing `unresolved` group. Unresolved means the
annotation cites a block that is missing from the retained document, which is a
data problem. Unplaced means the annotation never had lineage, which for
Inspector is the finding itself.

### Block emphasis resolution

One block may carry several annotations. The shared layer resolves a single tone
per block by precedence `danger > caution > neutral`, taking the badge from the
strongest-tone annotation and breaking ties by annotation order. This is
ordering, not domain knowledge, so it belongs in the shared layer.

Emphasis renders below hover and navigation-focus in precedence, so jumping to a
block still reads.

### Emphasis is suppressed while several layers are visible

A tone is a claim on one axis. Tinting a block while every layer is visible would
blend independent judgments into one colour — a composite verdict no individual
result made, and the same mistake the Overview tab avoids by showing three
separate dimension tiles instead of one overall letter.

While the layer filter is set to "all", markers and gap counts still render, so
document structure reads; choosing a layer reveals that layer's emphasis. The
viewer therefore accepts an optional `defaultLayer`, and a tool whose annotations
carry `emphasis` should name one rather than opening on an untinted view.
Inspector opens on completeness: whether required content exists is the question
that gates the other two.

## Inspector adapter

`InspectionResult` in, annotations out, pure and order-preserving.

### Annotation sources

`variable_grades` is the complete ledger. A missing variable *also* appears there
with completeness `F`, adherence `F`, and rigor `N/A`, so `missing_variables` is
read only as a label source. Emitting from both would double-count every gap.

| Source | Kind | Lineage | Notes |
|---|---|---|---|
| `section_grades[].variable_grades[]` × 3 dimensions | `completeness` / `adherence` / `rigor` | `variable_grade.block_ids` | Placed when lineage exists, anchored when empty |
| `section_grades[]` with no variables (prose sections) | same three | none — `SectionGrade` has no `block_ids` | Always anchored to the section |
| `cross_section_findings[]` | `consistency` | `finding.block_ids` | Tone always `danger`; a conflict is a negative result |

A dimension graded `N/A` is skipped. `N/A` means the rubric does not apply, so
there is no finding to locate, and emitting one adds gutter noise without
information.

### Placement rule

One rule, no special cases:

- `block_ids` non-empty → placed annotation with emphasis;
- `block_ids` empty → anchored absence.

This covers missing variables, not-applicable-but-cited content, and prose
sections without separate branches.

### Section anchoring

An absence anchors to the **last** retained block whose `section_label` equals the
rubric section name, so the gap reads after the content it is missing from. When
no block matches — the section is absent entirely — the annotation has no anchor
and joins the unplaced group. The adapter never falls back to `heading_stack`
matching: two matching rules mean two ways to be wrong about location.

### An absence renders at the section boundary, not in the gutter

Incompleteness is a property of a section, not of a block. A control placed in the
gutter beside one block reads as attached to that block's text however it is
styled, which claims an association the annotation explicitly disclaims.

Anchored annotations therefore render as a full-width row in the paper flow, on
their own grid row after the anchor block, introduced by a dashed rule and naming
their section — `Not present in Efficacy · 1`. Because the anchor is the section's
last block, that position *is* the section boundary.

The row sits outside the block body element. Inside it, the row would paint over
the block's emphasis tint and borrow that block's grade colour, re-attaching the
gap to a passage it does not describe. It carries no block ID and no highlight,
because it cites nothing. The gutter keeps one meaning: this block's identity and
what cites it.

### Grade mapping

| Grade | Tone |
|---|---|
| `A`, `B` | neutral |
| `C` | caution |
| `D`, `F` | danger |
| `N/A` | skipped |

This mapping lives only in the adapter.

## Layers

| Layer | Reader's question |
|---|---|
| Completeness | Is it there? |
| Adherence | Does it follow the template? |
| Rigor | Is what is there any good? |
| Cross-section consistency | Do two sections disagree? |

These are Inspector's own orthogonal axes, guaranteed independent by `AGENTS.md`,
so filtering is meaningful by construction. Severity is not a layer: layer
answers *which question*, tone answers *how bad*, so triage is visible in every
layer at once.

## Inspector panel

For a variable annotation: variable name, section, the dimension and its grade,
issues as a list, and the recommendation. For a consistency finding: the sections
in conflict, the description, and the recommendation. Both show the connection
kind already reported by the shared viewer, and absences state plainly that the
content is not present rather than showing an empty citation.

## Integration

Inspector already renders `Tabs` inside `DocumentSourceProvider`. This adds a
fourth `Document trace` tab beside Overview, Sections, and Consistency, matching
where Scout placed its own. The existing `focusBlockId` / `onFocusBlockConsumed`
navigation contract is reused unchanged.

## Stability and failure handling

- Projection is deterministic and order-preserving; annotation IDs derive from
  existing result identity.
- Rendering never writes to result or session state.
- A grading run with `grading_status: "unknown"` still renders: the document and
  whatever grades exist remain visible.
- `consistency_status` other than `complete` leaves the consistency layer empty
  rather than implying no conflicts exist.
- An anchor naming an unknown block degrades to unplaced, never to a wrong block.

## Testing

Adapter tests:

- every layer projects from its documented source field;
- missing variables are not double-counted;
- `N/A` dimensions are skipped;
- empty lineage produces an anchored annotation, not a placed one;
- anchoring selects the last block of the matching section;
- an unmatched section yields no anchor;
- grade-to-tone mapping for all six grades;
- input results are not mutated.

Shared contract tests:

- an anchored annotation declares no block lineage;
- an empty-lineage annotation is reachable rather than orphaned;
- block emphasis precedence and badge selection.

Verification includes the full Python suite, every web `test:*` script,
TypeScript checking, the production web build, and `git diff --check`.

## Acceptance criteria

- An Inspector user can read their reconstructed document and see which passages
  carry weak grades, filtered by dimension.
- Missing content is visible where it is missing, without an invented citation.
- The shared viewer contains no Inspector-specific logic, and Scout's behaviour
  and output are unchanged.
- No new analysis, grade, or result-contract field is created.

---

## Addendum: canonical refactor (implemented)

The viewer above was built against a canonical layer that computed several facts
and then discarded them, forcing the adapter to re-derive them. An audit of the
Inspector stack found the specific gaps; this addendum records what changed.

### Removed duplication

- **The A-F scale existed twice** - `GRADE_TO_SCORE` and the `_score_to_grade`
  thresholds were declared identically in `pipeline.py` and `stages/grader.py`,
  so changing the scale moved only half the report card. One scale and one
  converter now live in `models.py`.
- **The presence vocabulary existed twice** - as a schema enum and again as a
  parse-time set. One `CONTENT_STATUSES` constant now feeds both.
- **The section-to-block mapping was computed three times** - for the prompt, for
  the contract check, and again in the viewer from `section_label`. It is
  computed once and published as `mapped_block_ids`.
- **Absence was recorded twice** - as a `content_status` and again as a parallel
  `missing_variables` list. The status is the authority; the list is derived.

### Published instead of discarded

- `DimensionGrade.cited_block_ids` - each dimension judges and cites
  independently, so lineage belongs to the dimension. The three were previously
  merged into one list per variable, which let a completeness verdict be
  attributed to a block only rigor had read.
- `VariableGrade.content_status` - the five-value presence vocabulary the model
  already returns. `placeholder` and `missing` are different problems with
  different fixes, and nothing downstream could tell them apart before.
- `SectionGrade.mapped_block_ids` - a deterministic assignment, named apart from
  `cited_block_ids` so a consumer cannot mistake one for the other.
- `TopIssue` - `top_issues` was a formatted sentence fusing variable, dimension,
  grade, and issue. Consumers that wanted to link, filter, or re-sort had to take
  the sentence apart, contrary to the invariant that a layer states the
  structured parts its consumers need.

### Non-brittle checks

Two checks were replaced rather than kept:

- The rule that an absence cannot also cite blocks was enforced by a regex over
  TypeScript source. The engine now gives lineage precedence and never reads the
  anchor when blocks exist, so the combination is harmless rather than policed,
  and the test exercises behaviour instead of reading code as text.
- Deciding which files are document types used a filename-shape heuristic. All
  three services now expose `available_configs()` and identify a config by
  whether its declared `type_key` matches its filename - the same rule
  `find_config` enforces, so enumeration and lookup cannot disagree.

### Contract

`RESULT_VERSION` moved 38 to 39 with no migration, so earlier Inspector downloads
must be re-run. Grades, issues, and recommendations are unchanged; a snapshot
test in `tests/test_inspector_canonical_fidelity.py` pins the judgments against
fixed model replies so a future change to the merge cannot alter a report card
while the shape still validates.

### Still open

The per-dimension rule blocks on `SectionSpec` and `VariableSpec` are read by all
three prompt builders and populated by **zero** of 76 sections and 309 variables
across all 11 rubrics, so every variable is graded by identical generic rules.
Populating them, revisiting the 20-word caps on issues and recommendations, and
fencing completeness against adherence for template tokens are domain decisions,
not refactors.
