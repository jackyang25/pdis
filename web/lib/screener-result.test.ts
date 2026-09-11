import assert from "node:assert/strict";
import test from "node:test";

import { runScreener, type ContentBlock, type ScreenerResponse } from "./api.ts";
import { buildScreenerDocumentAnnotations } from "./screener-document-trace.ts";
import { packScreenerResult, unpackScreenerResult, runScope } from "./result-file.ts";
import { documentExtractionWarnings, documentBlockLocationLabel } from "./document-extraction.ts";
import { buildDocumentTrace, documentTracePassages } from "./document-trace.ts";

function fixture(): ScreenerResponse {
  const blocks: ContentBlock[] = ["Meeting notes", "Study report"].map((doc_id, index) => ({
    id: `${doc_id}:1`, doc_id, ordinal: 1,
    block_type: index === 0 ? "paragraph" : "image",
    content: index === 0 ? "The dose-selection study is under way." : "",
    image: index === 0 ? null : {
      media_type: "image/png", source_media_type: "image/png",
      data_base64: "aW1hZ2U=", sha256: "fixture-image-hash",
    },
    heading_stack: [], section_label: null, structural_meta: {}, style_hint: {},
    source_type: null,
  }));
  return { review: {
    gate_id: "eop1", gate_label: "End of Phase 1", bank_source: "Authored question bank",
    documents: blocks.map(({ doc_id }) => ({ doc_id })), blocks,
    org: "bmgf", intervention_class: "small_molecule", indication: "tuberculosis",
    disciplines: [{ id: "clinical", label: "Clinical", questions: [{
      id: "Q1", text: "Is dose selection under way?", requirement: "required",
      state: "partly_answered", statement: "The study is under way.",
      missing: "The planned completion date.", cited_block_ids: blocks.map(({ id }) => id),
    }] }],
  } };
}

test("arbitrary documents and embedded images survive saved-result and trace round trips together", () => {
  const result = fixture();
  const file = packScreenerResult(result);
  assert.equal(file.analysis_version, 5);
  assert.deepEqual(file.source_documents.map(({ doc_id }) => doc_id), ["Meeting notes", "Study report"]);
  const restored = unpackScreenerResult(JSON.parse(JSON.stringify(file)));
  assert.deepEqual(restored, result);
  const [annotation] = buildScreenerDocumentAnnotations(restored.review);
  assert.deepEqual(annotation.blockIds, result.review.blocks.map(({ id }) => id));
  assert.equal(annotation.kind, "partly_answered");
  assert.match(runScope(restored, "screener"), /Tuberculosis/);
});

test("PDF page locations, limitations and citations survive export and trace reconstruction", () => {
  const result = fixture();
  result.review.blocks[0].structural_meta = { page: 3, extraction_warnings: ["pdf_limited_structure"] };
  const restored = unpackScreenerResult(JSON.parse(JSON.stringify(packScreenerResult(result))));
  const annotations = buildScreenerDocumentAnnotations(restored.review);
  const trace = buildDocumentTrace(restored.review.blocks, annotations);
  assert.equal(documentTracePassages(trace, annotations[0].id)[0].sectionLabel, "Page 3");
  assert.equal(documentBlockLocationLabel(restored.review.blocks[0]), "Page 3");
  assert.deepEqual(documentExtractionWarnings(restored.review.blocks), [{
    code: "pdf_limited_structure", documentIds: ["Meeting notes"],
  }]);
  assert.deepEqual(restored, result);
});

test("saved reviews from before retained-only evidence are explicitly refused", () => {
  const file = packScreenerResult(fixture());
  assert.throws(() => unpackScreenerResult({ ...file, analysis_version: 4 }), /re-run the screener analysis/);
});

test("every answered and partial question must cite passages retained in the file", () => {
  for (const state of ["answered", "partly_answered"] as const) {
    const result = fixture();
    const question = result.review.disciplines[0].questions[0];
    question.state = state;
    question.missing = state === "answered" ? "" : "The completion date.";
    question.cited_block_ids = [];
    assert.throws(() => packScreenerResult(result), /cites no passage/);
    question.cited_block_ids = ["unretained:1"];
    assert.throws(() => packScreenerResult(result), /passage the file does not carry/);
  }
});

test("a saved review cannot silently lose a document's retained content", () => {
  const file = packScreenerResult(fixture());
  file.source_documents.pop();
  assert.throws(() => unpackScreenerResult(file), /document has no retained passages/);
});

test("Screener submits one ordered file collection with no type or context channels", async (t) => {
  const result = fixture();
  let request: FormData | undefined;
  t.mock.method(globalThis, "fetch", async (url: string, init: RequestInit) => {
    assert.match(url, /\/api\/screener\/run$/);
    request = init.body as FormData;
    return new Response(JSON.stringify({ event: "complete", result }) + "\n");
  });
  const files = [new File(["notes"], "notes.docx"), new File(["slides"], "report.pptx")];
  assert.deepEqual(await runScreener(files, {
    gate: "eop1", org: "bmgf", intervention_class: "small_molecule", indication: "tuberculosis",
  }), result);
  assert.ok(request);
  assert.deepEqual([...request.keys()], ["files", "files", "gate", "org", "intervention_class", "indication"]);
  assert.deepEqual(request.getAll("files").map((file) => (file as File).name), files.map((file) => file.name));
});
