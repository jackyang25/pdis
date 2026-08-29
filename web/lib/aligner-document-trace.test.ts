import assert from "node:assert/strict";
import { test } from "node:test";

import type { AlignmentResult } from "./api.ts";
import { buildAlignerDocumentAnnotations } from "./aligner-document-trace.ts";

function result(): AlignmentResult {
  return {
    documents: [
      { doc_id: "itpp", source_type: "itpp", display_name: "iTPP" },
      { doc_id: "ctpp", source_type: "ctpp", display_name: "cTPP" },
    ],
    edges: [
      {
        edge_id: "itpp-to-ctpp",
        reference_doc_id: "itpp",
        comparison_doc_id: "ctpp",
        question: "Does the candidate meet the bar?",
      },
    ],
    org: "bmgf",
    intervention_class: "vaccine",
    indication: "hiv",
    blocks: [],
    findings: [
      {
        requirement_id: "itpp-to-ctpp/r-001",
        edge_id: "itpp-to-ctpp",
        requirement: "Shelf life of 36 months.",
        reference_spans: [
          { quote: "Shelf life | 36 months", block_ids: ["itpp/b-0001"] },
        ],
        verdict: "falls_short",
        statement: "Shelf life is 24 months.",
        comparison_spans: [
          { quote: "Shelf life | 24 months", block_ids: ["ctpp/b-0004"] },
        ],
      },
    ],
  };
}

test("both sides of a finding underline the line they were read from", () => {
  // Aligner passed `spans: []` and cited blocks only, so the trace shaded whole passages:
  // on a target table that is several hundred words highlighted to show where one row was
  // read. Scout had underlined exact lines all along, and the difference between the two
  // tools was not a decision anyone made - the machinery was private to Scout.
  const annotations = buildAlignerDocumentAnnotations(result());
  const byKind = new Map(annotations.map((one) => [one.kind, one]));

  const requirement = byKind.get("requirement");
  assert.ok(requirement, "the bar is not placed in the document that states it");
  assert.deepEqual(requirement.spans, [
    { quote: "Shelf life | 36 months", blockIds: ["itpp/b-0001"] },
  ]);
  // Derived from the spans, never sent beside them: two fields for one fact can disagree,
  // and a reader trusting the citation is trusting that they do not.
  assert.deepEqual(requirement.blockIds, ["itpp/b-0001"]);

  const verdict = byKind.get("falls_short");
  assert.ok(verdict, "the verdict is not placed in the document it judged");
  assert.deepEqual(verdict.spans, [
    { quote: "Shelf life | 24 months", blockIds: ["ctpp/b-0004"] },
  ]);
  assert.deepEqual(verdict.blockIds, ["ctpp/b-0004"]);
});

test("silence is placed nowhere, because it cites nothing", () => {
  // `not_addressed` is the one verdict about the absence of text, so there is no passage
  // to underline and no block to open. An annotation here would put a marker on whichever
  // block happened to be nearby.
  const silent = result();
  silent.findings[0] = {
    ...silent.findings[0],
    verdict: "not_addressed",
    statement: "",
    comparison_spans: [],
  };
  const kinds = buildAlignerDocumentAnnotations(silent).map((one) => one.kind);
  assert.deepEqual(kinds, ["requirement"]);
});

test("a span with no quote is not carried into the trace", () => {
  // `markCitedText` matches a quote against block text, and an empty quote matches
  // everywhere - so a blank span does not underline nothing, it underlines everything.
  const blank = result();
  blank.findings[0] = {
    ...blank.findings[0],
    comparison_spans: [{ quote: "   ", block_ids: ["ctpp/b-0004"] }],
  };
  const verdict = buildAlignerDocumentAnnotations(blank).find(
    (one) => one.kind === "falls_short",
  );
  assert.deepEqual(verdict?.spans, []);
  // The block still opens. Losing an unusable quote is not losing the citation.
  assert.deepEqual(verdict?.blockIds, ["ctpp/b-0004"]);
});
