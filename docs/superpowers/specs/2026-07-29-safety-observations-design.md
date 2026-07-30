# Safety observations

## Purpose

Make Scout's Safety view useful for product-development triage without implying
that spontaneous-report counts measure incidence, establish causality, or form a
validated statistical safety signal.

## Scope

This change covers FDA label warnings, FAERS reported events, MAUDE device
reports, and FDA device recalls already retrieved by the `fda_safety` adapter.
It does not add disproportionality analysis, EBGM, chi-square tests, incidence,
severity inference, or causal assessment.

## Architecture

The existing boundary remains:

`FDA source -> Searcher normalization -> Scout projection -> API -> Safety UI`

Each layer has one responsibility:

- The FDA Safety adapter executes source-native operations and normalizes
  explicit provider facts.
- Searcher exposes a source-attributed `SafetyObservationRecord` without
  interpreting clinical importance.
- Scout deduplicates repeated retrievals and optionally adds the existing
  display-only relationship to the uploaded product.
- The API serializes the current result contract without deriving new facts.
- The UI groups and explains observations without recalculation.

No model stage assigns causality, incidence, severity, or statistical signal
strength. No compatibility or legacy branch is retained.

## Data contract

Replace the ambiguous `SafetyRecord` / `SafetySignal` terminology with
`SafetyObservationRecord` / `SafetyObservation`.

Each normalized observation contains:

- `product_name`: the product returned or queried;
- `record_type`: `label_warning | reported_event | device_event | recall`;
- `source_system`: `fda_label | faers | maude | fda_recall`;
- `label`: the source-owned warning, event term, event type, or recall class;
- `detail`: retained source detail when available;
- `report_count`: a non-negative count only when the source supplies one;
- `qualification`: the source-specific interpretation limit;
- `source_role`: the provider-supplied study role, independent of product
  relationship.

The supporting `Finding` remains the authority for URL, retrieval query,
retrieval time, source lane, and excerpt. These fields are not duplicated into
the observation.

Structural validation enforces known enum values and non-negative counts. It
does not reinterpret prose. A FAERS reported event must carry a report count;
other record types do not manufacture one.

## Projection behavior

Scout groups observations by normalized product, record type, source system,
and label. It retains all supporting findings and field references. Repeated
retrieval paths do not add counts together; when the same source observation is
retrieved more than once, Scout retains the largest identical-scope count.

The optional relationship classifier may label an observation as direct,
analogous, adjacent, unrelated, or unknown. That label is display-only and is
not a safety conclusion.

## Interface

The Safety tab has two sections:

1. **Official safety information** contains FDA label warnings and recalls.
2. **Reported-event surveillance** contains FAERS and MAUDE observations.

Rows show the source system, product, observation label, relationship, and—only
for FAERS—the report count. Expanded content shows source detail,
qualification, retrieval context, and the cited source link.

The surveillance section states that entries are ordered by returned report
count and that counts are neither incidence nor evidence of causation. The UI
does not sum counts, calculate shares, or apply qualitative risk labels.

Empty sections are omitted. If no observations are available, the tab presents
one forward-looking empty state rather than an empty table.

## Failure behavior

FDA source failures remain isolated retrieval outcomes. A failed FDA Safety
lane does not fail other Scout evidence lanes. Malformed safety records are
rejected at the Searcher model boundary rather than repaired downstream.
Missing optional detail remains empty; missing required source identity,
product, label, or FAERS count prevents that observation from entering the
result.

Source URLs must reproduce the source-native query. Tests cover URL generation
and normalized records so link drift cannot recur silently.

## Testing

- Searcher model tests cover valid and invalid observation contracts.
- FDA adapter tests cover each record type, source system, FAERS count, and
  source-native URL.
- Scout projection tests cover deduplication and provenance retention.
- API/result tests cover the renamed end-to-end contract.
- UI tests cover grouping, count wording, qualifications, and empty sections.
- Python tests, TypeScript tests, typecheck, production build, and
  `git diff --check` are required before completion.

## Deferred work

Statistical signal detection requires a separate, explicit source contract for
the exposed and background cells of a valid contingency table, time window,
product identity, deduplication rules, and method metadata. It must not be
inferred from the current top-event count response.
