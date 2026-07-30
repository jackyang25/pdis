# Prompt transparency for semantically derived labels

## Goal

Let a curious reader see the actual instructions a model stage was given for a
derived label, without duplicating prompt prose across layers and without
changing what any model receives.

## Current state

Prompt *content* is already conventionalized: `ROLE`, `INPUT AUTHORITY`,
`SHARED PRIMITIVES`, `DECISION PROCEDURE`, and `OUTPUT CONTRACT` recur across
stages, over six shared primitives in `prompt_primitives.py`.

Prompt *exposure* is not. Seventeen prompts across twelve model stages use five
conventions:

- `_system_prompt(...)` in seven stages.
- `_document_ledger_system_prompt` and `_measurement_system_prompt` in
  `conformity.py`.
- `_system_prompt_for_variable` plus geographic, counterfactual, and precedent
  variants in `query_extractor.py`.
- `_ledger_system_prompt` in `target_resolver.py`.
- Assembled inline inside a public stage function, with no seam at all:
  `conformity.reconcile_quantitative_document_ledger`,
  `evidence_reviewer.prefill_evidence_review`,
  `target_reviewer.prefill_target_review`.

Signatures disagree on shape and order: `(*, indication, intervention_class,
framing="")`, `(indication)`, `(intervention_class, source_type, indication)`,
and `(*, indication, intervention_class)`.

Nothing outside `services/scout/` can read any of it. Imports flow
`web/ → api/ → services/ → shared/`, so a documentation surface needs an
artifact in `shared/`, the way `shared/product_knowledge.json` already serves
both `services/assistant/knowledge.py` and `web/lib/product-knowledge.ts`.

## Scope

- Give every model stage one prompt seam. A stage with one prompt exposes
  module-level `system_prompt`; a stage with several exposes one named builder
  per prompt, without the leading underscore, because the catalog and the
  generator are legitimate consumers.
- Standardize names only, never signatures. Six prompts take domain objects —
  `Attribute`, `QuantitativeTarget`, `ScoutTypeConfig` — because their text
  interpolates the field under evaluation (`f"Variable: {attribute.name}"`).
  Forcing those into a scalar vocabulary would restructure how stages hand data
  to their prompts, which is exactly the invasive change this work avoids.
- Render every prompt through one convention: the catalog supplies placeholder
  domain objects whose fields are visible slots (`{field_name}`,
  `{document_target}`, `{value} {unit}`). A reader sees the real assembled
  prompt with self-evident slots where their document's content goes. Per
  configuration domain content — the four framing kinds and
  `query_extraction_guidance` — is listed once under `framings`, never inlined
  per prompt.
- Move the three inline prompts into that seam verbatim. A move, not an edit.
- Declare `services/scout/prompt_catalog.py`: for each prompt, a stable id, its
  stage, its builder, the context it requires, the framing slot it fills, and
  the result fields and UI labels it produces.
- Generate `shared/prompt_reference.json` from the catalog.
- Render it on the documentation page, one collapsed entry per prompt, and link
  each `ScoutSignalTopic` popover to the entries behind its label.

## Artifact shape

```json
{
  "version": 1,
  "prompts": [
    {
      "id": "drift.classify",
      "stage": "drift_classifier",
      "title": "Evidence relationship classification",
      "context": ["indication", "intervention_class"],
      "framing_slot": "drift_framing",
      "produces": {
        "result_fields": ["matches[].relation"],
        "ui_labels": ["relationships"]
      },
      "text": "ROLE\n..."
    }
  ],
  "framings": [
    {
      "key": "drift_framing",
      "org": "bmgf",
      "source_type": "itpp",
      "intervention_class": "vaccine",
      "text": "..."
    }
  ]
}
```

`text` is the prompt as production assembles it, with `{indication}` and
`{intervention_class}` left as literal placeholders and the configuration
framing left as a named slot. The thirteen configurations supply four framing
kinds (`evidence_framing`, `quantitative_target_framing`, `drift_framing`,
`precedent_framing`); listing them once under `framings` keeps a prompt's text
from repeating per configuration.

## Documentation surface

- The generated file lives in `shared/`, read directly by Python. The web build
  copies it into `web/public/`, and the page fetches it when a reader first
  expands a prompt. Seventeen prompts at roughly 2.3 KB each plus 13.3 KB of
  framing text is a 50–60 KB artifact; statically importing that into a route
  whose own payload is 73 KB would make every docs visitor pay for text almost
  nobody opens. Fetch-on-expand keeps the route payload flat and matches the
  collapsed-by-default design.
- It stays separate from `product_knowledge.json`, which holds authored prose;
  one file is written by a person, the other by a generator.
- One `<details>` per prompt, collapsed, grouped by stage — the pattern the
  page already uses for the FAQ and the narrow-width architecture list.
- Each popover in `scout-signal-help.tsx` gains a link resolved through the
  catalog's `ui_labels`, so the label-to-prompt mapping is never hand-written
  in the UI.
- The section states what it excludes: run-specific document content and the
  response schema.

## Boundaries

- No prompt wording changes. `SHARED PRIMITIVE` (two stages) is not normalized
  to `SHARED PRIMITIVES` (six stages), grounding and precedent gain no shared
  primitive, and no section is reordered or reworded. Each of those alters what
  a model receives and belongs to its own evaluated change.
- No per-run prompt capture. Result envelopes, API schemas, and review
  contracts are untouched.
- No runtime endpoint. The artifact is committed and read like
  `product_knowledge.json`.
- Authored prompt text stays in Python. The catalog references builders; it
  does not hold copies.
- Assistant may read the artifact as process documentation. It is never
  evidence, provenance, or grounding for a run.
- `intent_builder.py` is deterministic and has no prompt.

## Verification

- Snapshot every prompt at the provider-client boundary, not at the builder:
  a stub client records the system prompt each stage sends, captured before the
  seam work and asserted byte-equal after it. Recording what leaves the process
  covers the three inline prompts, which have no builder to call yet, and proves
  the property that matters — that no model input changed. A failure names the
  prompt whose move was not faithful.
- A test regenerates `shared/prompt_reference.json` and asserts equality with
  the committed file, so a prompt edit without regeneration fails the build.
- A completeness test asserts every stage exposing a prompt builder appears in
  the catalog, so a new stage cannot ship undocumented.
- `python -m compileall`, `python -m unittest discover -s tests`,
  `npm --prefix web run typecheck`, the production web build, and
  `git diff --check`.

## Sequencing

1. Snapshot test over today's prompts, using the current mixed accessors.
2. Seam standardization and the three extractions, keeping the snapshot green.
3. Catalog module, then the generator and its equality test.
4. Documentation section and popover links.

Steps 1 to 3 change no rendered output. Step 4 is the only user-visible change.
