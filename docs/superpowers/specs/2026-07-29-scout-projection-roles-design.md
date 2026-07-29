# Scout Projection Roles Design

## Goal

Make Scout's Landscape and Safety views explicit about how each structured
source record relates to the uploaded product without changing retrieval,
canonical document claims, evidence reasoning, or quantitative calibration.

## Problem

Searcher adapters correctly retain provider-supplied development and safety
records. Scout's projection layer currently groups every named intervention as
a `DevelopmentProgram`, however, even when the source record describes a
control, comparator, co-intervention, or merely analogous product. Safety items
likewise identify their source product but do not state whether that product is
the document product or contextual evidence from another product.

The raw facts and citations are sound. The derived views imply a relationship
that their contract does not currently store.

## Boundaries

The change belongs after normalized Findings and before the two derived views:

`Findings -> projection role mapping -> Landscape and Safety projections`

It must not mutate or feed back into:

- the canonical document claim ledger;
- quantitative target or comparator contracts;
- query planning or retrieval;
- Insights, evidence relationships, grounding, or precedent;
- quantitative admission or statistics.

Raw Findings and their provenance remain unchanged. The role decisions are
stored once in the final Scout result and rendered directly by the UI.

## Contracts

Every projected development or safety item stores:

- `source_role`: `experimental | comparator | control | co_intervention |
  unknown`. This describes the record's explicit role within its source study.
  Adapters may populate it only from structured provider metadata; otherwise it
  remains `unknown`.
- `target_relationship`: `direct | analogous | adjacent | unrelated | unknown`.
  This describes the item's relationship to the product represented by the
  canonical document context.

These are separate axes. A record can be an experimental arm in its source and
still be only analogous to the uploaded product.

The semantic relationship mapper receives bounded canonical document context,
the projected item's source-owned fields, and its cited Finding context. It
returns one schema-bound decision per item ID. OpenAI owns this semantic
classification. Missing or malformed decisions become `unknown`; they do not
stop the Scout run and never alter core analysis.

## Projection and Provenance

Projection identity remains based on the existing source-normalized record
identity. Grouping retains every supporting Finding, record ID, source type,
attribute reference, and URL. When grouped records contain different explicit
source roles or different semantic relationship decisions, the projection uses
`unknown` rather than selecting a stronger label.

The API and TypeScript contracts expose the two closed enums. Final-result
serialization persists them as part of the current result schema.

## User Interface

Landscape is presented as structured development records, not an unqualified
list of programs. Each row shows the target relationship and, when known, the
source-study role. Users can filter by target relationship while retaining
access to all records and citations.

Safety shows the target relationship beside the record type and product name.
Its explanatory copy states that analogous and adjacent records are context,
not safety findings attributed to the uploaded product. Unknown relationships
remain visible and explicitly labeled.

No record is hidden solely because of its role. This is a lossless presentation
change.

## Error Handling

- Provider metadata absent: `source_role = unknown`.
- Semantic mapper uncertainty or omitted decision: `target_relationship =
  unknown`.
- Conflicting grouped roles: the affected role becomes `unknown`.
- Invalid IDs or enum values: reject that mapper decision structurally and use
  `unknown` for the projection.
- All failures are isolated to the derived view; Scout's final core analysis
  remains available.

## Tests

Tests must prove that:

1. explicit provider arm roles survive Searcher normalization;
2. unknown roles are never inferred from intervention names;
3. projection grouping retains all provenance and resolves role conflicts to
   `unknown`;
4. semantic relationship decisions are ID-bound and schema-bound;
5. malformed or incomplete mapping degrades only the projection role;
6. API and TypeScript contracts carry both enums;
7. Landscape and Safety display direct versus contextual records clearly;
8. the existing Scout reasoning and quantitative outputs are byte-for-byte
   unchanged by projection classification, apart from the two derived arrays.

