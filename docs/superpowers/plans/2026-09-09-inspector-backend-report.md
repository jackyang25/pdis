# Inspector multiple-rubric backend report

## Implemented

- Added a strict profile/rubric catalog. Profiles pin ordered definitions and
  declare applicability as allowed values for explicit product facts; the engine
  resolves those declarations generically to included, outside scope, or needs
  context.
- Kept every existing BMGF YAML unchanged and referenced it through authored
  first-class rubric metadata. Added scoped E4-, E6(R3)- and E14-derived PDIS
  adaptations with stable clause-level source IDs, revisions and official URLs.
- Added whole-document evidence assessment while preserving mapped-section BMGF
  behavior and one unit per schema-bound request. Guideline content filed under
  Other is assessed and cited without inventing physical guideline sections.
- Added parse-once aggregate orchestration, one consistency pass, qualified unit
  IDs, frozen requirement/rubric/stage-guidance snapshots, shared blocks, strict
  review and root-finding validation, and the profile-based application operation.
- Added strict multipart JSON fact validation and
  `GET /api/configs/inspector?org=&source_type=&intervention_class=`. The endpoint
  returns profile-owned fact controls; unrelated profiles return an empty list.
- Updated Inspector documentation, configuration guidance, response schemas and
  the generated prompt reference. The legacy single-rubric service helper remains
  available for tests and non-production callers.

## Source review

- E4: official adopted guideline, sections I–III, including benefit/adverse-effect
  dose relationships, dose-response as part of development, time course and the
  availability of multiple study designs:
  https://database.ich.org/sites/default/files/E4_Guideline.pdf
- E6(R3): the pinned Principles and Annex 1 package adopted 6 January 2025,
  especially Principles, Annex 1 section 3.1 and proportionate risk management in
  3.10.1. The adaptation stays at strategic-plan depth and does not claim review
  of executed trial conduct:
  https://www.ema.europa.eu/en/documents/scientific-guideline/ich-e6-r3-guideline-good-clinical-practice-gcp-step-5_en.pdf
- E14: official guideline sections 1.2–1.3 and 2.1–2.4, paired with the consolidated
  21 February 2022 E14/S7B Q&As 5.1 and 6.1. The adaptation does not universally
  mandate a thorough-QT study:
  https://database.ich.org/sites/default/files/E14_Guideline.pdf and
  https://database.ich.org/sites/default/files/E14-S7B_QAs_Step4_2022_0221.pdf
- EMA version history was checked to avoid silently substituting the 2026 Annex 2
  package for the pinned 2025 Principles/Annex 1 scope:
  https://www.ema.europa.eu/en/ich-e6-good-clinical-practice-scientific-guideline

These definitions are deliberately selected PDIS document-review adaptations,
not exhaustive guideline transcriptions, ICH templates, certification, regulatory
advice, approval predictions, or scientific validation. Representative-document
trials remain necessary to evaluate assessment quality.

## Verification

- Inspector suite: 106 tests passed before the final reviewer regressions were added.
- Final focused aggregate, route, contract, schema and service-interface set:
  46 tests passed; the multiple-rubric file alone passes 17 tests.
- Full backend suite: 1,111 tests passed, 1 skipped, using the Docker Python 3.11
  environment with the complete workspace mounted.
- Real fake-client HTTP-shaped fixture:
  `/private/tmp/inspector-multiple-rubrics.json`.
- Host `uv` and supported Python were unavailable; Docker was used. Ruff is not
  installed in the API image, so no separate Ruff invocation was available.

## Concerns and limits

- BMGF source templates are not tracked. Their existing definitions were preserved
  byte-for-byte, but fidelity to inaccessible originals was not re-verified and no
  source URL/revision was invented.
- E14 applicability is intentionally narrower than the guideline's full scope and
  depends only on the three explicit facts carried in the request.
- No live provider calls, regulatory validation, deployment, commit, staging or
  push were performed.
