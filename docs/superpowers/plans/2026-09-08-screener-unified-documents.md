# Screener unified documents implementation plan

**Goal:** Every Screener upload passes through the same shared parser and survives
in the result as citable content. The user approved this cleanup in conversation.

**Architecture:** Screener accepts any DOCX/PPTX document, identified by filename
stem, without a document-role selector. Chunker parses each file without rubric
section mapping. All questions read the same combined blocks, and all result
consumers use the same citations and retained documents.

**Tech stack:** Python/FastAPI, shared Chunker, TypeScript/React, portable JSON.

## Dependency map and boundaries

| Owner | Consumes | Produces | Dependent consumers |
|---|---|---|---|
| Shared context discovery | tool configurations and Screener gate banks | `/api/configs/contexts` | shared `ContextFields` |
| Shared document-type discovery | document configurations | `/api/configs/document-types` | `SourceTypeField`, not Screener |
| Screener input panel | DOCX/PPTX files and shared run context | `File[]`, gate/org/intervention/indication | `runScreener` |
| API route | one `files` multipart field | `DocumentInput(file_path, doc_id)` | Screener pipeline |
| Chunker | supported file, stable identity, context tags | canonical `ContentBlock[]` | assessor and result |
| Screener pipeline | documents and gate bank | `GateReview` | API serialization |
| Assessor | one question and all blocks | state, statement, missing, cited block IDs | result contract |
| Result contract | complete bank and retained documents | validated review | UI, export/import, Ask |
| Shared result envelope | review and blocks | versioned analysis plus source documents | import and workspace |
| Screener trace adapter | cited questions | shared annotations | unchanged shared trace viewer |

## Fixed contract

- `DocumentInput` owns `file_path` and `doc_id`; `ReviewDocument` owns `doc_id`.
- `GateReview` owns documents, blocks, disciplines, gate identity, bank source and
  org/intervention/indication. No `context_labels`.
- `QuestionAssessment` retains id/text/requirement/state/statement/missing and
  `cited_block_ids`. No source enum or context label.
- The model chooses `answered`, `partly_answered`, or `not_found`.
  Configuration alone assigns `not_applicable`.
- Answered and partial questions cite retained blocks; other states cite nothing.
- Canonical blocks retain the shared shape. Screener's unclassified document role
  is null, not a fabricated business type; org/intervention/indication are stamped.
- All supported documents use the same parse-only call. No document configuration
  lookup, transient reader, new parser adapter, or separate citation engine.
- Reject unsupported files and obsolete upload fields explicitly. Never silently
  omit uploaded evidence. Duplicate document identities fail before parsing.
- Bump only Screener's analysis version from 4 to 5. Old results fail at the
  existing version boundary; their lost context cannot be reconstructed.
- Keep embedded images and PPTX rasterization. Ask's independent attachment
  feature is outside this Screener cleanup.

## Execution

- [x] Backend: remove context reader/models/exports, reduce assessor schema,
  parse every document without configuration, simplify API and result contract.
  Update tests for arbitrary same-kind DOCX/PPTX documents, format rejection,
  all-document prompts, retained images, and absent/unknown citations.
- [x] Frontend: one file collection using shared format controls; simplify
  request and result types, counts, trace adapter, and citation rendering.
  Bump portable schema and update tests for round-trip and old-version rejection.
- [x] Consumers: update Ask legend, public knowledge, generated prompt reference,
  Screener docs and AGENTS invariants to describe this one path.
- [x] Integration: run backend and web suites, TypeScript checking, production
  build, and diff checks. Search live code for removed fields and format lists.

## Verification cases

1. Two ordinary reports of the same format are parsed and retained separately.
2. A question can cite blocks from both reports, preserved through export/import.
3. A DOCX and PPTX with embedded visuals use one block collection and retain IDs.
4. PDF/TXT/MD/standalone images are rejected at both UI and API boundaries.
5. Legacy context fields cannot enter the live request or result contract.
6. Missing/unknown citations fail; unanswered questions remain in the review.
7. Questions, Documents and Ask share source identity and block membership.
8. Other tools retain their existing document-role configuration and behaviour.

## Verification results

- Python 3.11 in a disposable API container: 1,034 tests, successful with one skip.
- Web: 611 tests passed; TypeScript and production Next.js build passed.
- Ruff and `git diff --check` passed.
- Independent review found no important integration defects.
- No live provider assessment or browser interaction test was performed.
- The running application containers were not replaced; rebuild API and web to
  serve this implementation and its regenerated shared prompt artifact.
