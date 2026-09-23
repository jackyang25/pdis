# Screener: question-specific evidence selection

## Intent and approval scope

The user wants Screener to accommodate larger collections (approximately 15–20
documents) by reducing the material in each final assessment request. Increased
model-call cost is acceptable. Preserve complementary evidence, conflicting
evidence, visual context, citations, and existing question-answer semantics.

The agreed direction is one selection request per document per applicable
question, followed by one final assessment per question. This document specifies
the approved direction and its verification requirements.

## Alternatives and choice

- Current full-set assessment preserves direct access to everything, but each
  request grows with the entire collection.
- Sequential running answers compress history into model reasoning and introduce
  document-order dependence. Do not use this approach.
- Choose independent source-block selection followed by combined assessment.
  This reduces final payload where material is irrelevant, at the cost of more
  calls and an additional evidence-recall risk. It is not an accuracy guarantee.

## Data flow

1. Resolve applicability and parse every document using existing contracts.
2. For every applicable question/document pair, send the complete parsed document
   text and retained images, the exact question, and selected review context to a
   schema-bound selector. Selection returns canonical block IDs only, not an
   answer, paraphrase, confidence score, or per-document coverage state.
3. Resolve those IDs back to original blocks. Union selections for that question
   in source order, without modifying text, tables, images, or provenance.
4. Send the question and selected original blocks to the final assessor. Only
   this stage decides answered, partly answered, or not found.
5. Retain the full original block collection in the portable result, Documents
   view, and Ask. Selection reduces model input, not the saved source record.

For one question and 15 documents, this means 15 selection calls and one final
assessment, excluding bounded retries. A single document uses the same path;
there is no undocumented threshold changing assessment behavior.

## Selection and context contract

Select evidence addressing any part of the question, including incomplete plans,
qualifications, explicit negative findings, contradictions, and uncertainty.
Retain supporting context needed to interpret it: product identity, population,
dates, units, definitions, caveats, and contextual passages elsewhere in that
document. Select potentially relevant material when uncertain, rather than
maximizing compression. Review tags are intended context, not proof of identity
and not hard filters. Background and comparator evidence remain eligible.

Use whole canonical blocks; never generate replacement evidence summaries.
Retain complete tables as represented by the parser and use explicit structural
metadata to retain related page/slide text and visuals together. Do not infer
relationships by proximity or re-parse prose. Image inputs retain exact block-ID
labels. PDF extraction warnings remain visible to the assessor.

The selector receives one question and one document per request, with documented
request-scope constants. Required/anticipatory remains absent from both model
stages. No lexical relevance filters, similarity thresholds, top-k limits, or
arbitrary truncation are introduced.

Final assessment preserves the bank's existing clause-reading rules and context
attribution guardrails. Final citations must resolve within the selected input,
not merely somewhere in the full saved collection. It is told that its input is
selected evidence, not the complete document set.

An empty selection is a valid structured outcome for a successfully read document,
not a pipeline failure. All documents must finish selection before assessment.
If all selections are empty, the final assessor receives explicit no-selected-
evidence context and cannot cite blocks or claim an answered state. This outcome
still has evidence-recall risk; tests alone cannot prove actual absence.

## Scheduling and failure handling

Reuse shared batching/fan-out and structured-call/reference transport primitives.
Keep parsing bounded at three documents. Flatten question/document selection
tasks into a run-wide queue capped at six concurrent model calls, then assess
questions with the same cap. Never nest six document workers inside six question
workers. Keep result ordering independent of completion order.

Validate every selected ID against that request's document. A malformed reply or
unknown ID gets the existing bounded contract-repair policy, then fails the run.
Provider failures also fail the run with stage context. No failure becomes an
empty selection, a partial answer, or an omitted document/question. Do not fall
back silently to full-set requests after size errors.

Represent selection as its own progress stage through the existing run-event
mechanism. Keep existing run capacity and stateless architecture. Do not alter
deployment memory settings as part of this change.

## Scope and documentation

Add a selector under Screener stages, keep block serialization shared between
Screener's two stages, and let the pipeline own task scheduling and combination.
Use existing shared utilities rather than copying provider or batching mechanics.
Do not change other tools' pipelines, question banks, final result fields, states,
counts, or import compatibility. Runtime selection records stay request-local.

Revise the Screener documentation and relevant AGENTS.md invariant: every
applicable question still examines every document through selection, but the
final assessment no longer receives every block. Remove claims of one model call
per question or identical full-set assessment prefixes. Refresh generated prompt
references and user-facing progress descriptions through existing mechanisms.

## Verification and acceptance

Write failing contract tests first. Cover exact pair scope, every document read,
selected-only final requests, canonical IDs, original image bytes and warnings,
whole table/page/slide context, empty selections, invalid/cross-document IDs,
selection failures, ordering, and a global concurrency cap. Preserve all original
blocks in exported results and verify existing citation/state contracts.

Test complementary evidence from different documents reaching one assessment,
conflicting and qualifying passages being forwarded when selected, and no mixing
of unrelated questions. Unit tests verify wiring and prompt obligations, not
whether the model reliably selects the right evidence.

Run the full repository checks. Compare representative live runs against the
current full-set baseline before claiming equivalent answer quality: complementary
documents, unrelated-product additions, comparator/background evidence, partial
answers, contradictions, and image-only relevant content. Measure request sizes,
latency, tokens, and selection recall. Offline tests and builds alone do not
establish a low error rate or support for every 20-document workload.

## Explicit limitations

A single document can still exceed gateway/model capacity. Combined selected
evidence can still be large when much of the collection is relevant. Parsing and
retaining all source images still consumes memory. This refactor addresses final
assessment payload size, not a hard request-size or memory guarantee. Further
within-document splitting or aggregate-budget policies need a separate design;
do not silently omit evidence to fit.
