# Block Reference Design

## Goal

Make every human-facing document reference consistent and navigable without changing canonical block IDs, parsed blocks, result envelopes, or provenance.

## Scope

The design applies to Scout, Inspector, Aligner, Evidence Map, and shared source-passage UI. Data contracts continue to store complete canonical IDs such as `document/b-0040`.

## Presentation contract

- Show the compact terminal ID, such as `b-0040`, wherever a block reference is visible.
- Do not prefix the visible ID with `Block` or expose full document-qualified IDs in ordinary page content.
- Use `View source` for the action and `Source passage` for the content it opens.
- Reserve `Block ID` for the audit detail inside the source-passage popover. Show the full canonical ID there and retain the copy action.
- Use full canonical IDs in accessible names and tooltips so shortening does not reduce traceability.

## Document-trace gutter

Each reconstructed block has one compact gutter row aligned with the first baseline of its source content:

- the compact block ID is quiet, monospace, and non-interactive;
- connected result groups appear beside the ID as compact count controls;
- controls are not stacked below the ID;
- groups are progressively disclosed in the existing inspector after activation;
- exact quoted spans remain the primary inline connection affordance.

The gutter does not copy IDs or imitate a link when no destination exists. Copying remains in the source-passage audit detail.

## Shared component boundary

A shared block-reference presentation component owns compact formatting, accessible naming, source-passage wording, optional connection counts, and optional navigation. Consumers provide canonical IDs and supported actions; they do not recreate labels or truncate IDs independently.

`DocumentSourceTrace` remains the shared passage inspector. It may expose `Open in document trace` only when its provider supplies a valid navigation callback. Inspector and Aligner use the same source-passage inspector without a false document-trace link. Evidence Map uses compact references and the same source affordance instead of joining raw IDs.

## Data flow and safety

This is a presentation-only projection:

1. Consumers pass canonical block IDs already present in final results.
2. Shared formatting derives a compact display ID without rewriting the canonical value.
3. Source lookup and navigation continue to use the full canonical ID.
4. Missing retained blocks render as unavailable source passages; the UI does not invent text or a destination.

No analysis stage, API schema, saved result, import/export path, or provenance check changes.

## Testing

- Unit tests cover compact formatting, full-ID preservation, singular/plural source wording, and optional navigation.
- Component tests cover gutter alignment, one-row connection controls, and no inert links.
- Existing document-trace, Evidence Map, Inspector, and Aligner tests must continue to pass.
- Typecheck and production build verify the cross-page integration.
