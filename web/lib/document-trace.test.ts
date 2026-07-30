import assert from "node:assert/strict";
import test from "node:test";

import type { ContentBlock } from "./api.ts";
import {
  buildDocumentTrace,
  documentTraceFocusTarget,
  documentTraceSegmentsInRange,
  filterDocumentAnnotations,
  groupDocumentTraceMarkers,
  type DocumentAnnotation,
} from "./document-trace.ts";

type Kind = "field" | "assessment";

function block(
  id: string,
  ordinal: number,
  content: string,
  docId = "document",
): ContentBlock {
  return {
    id,
    doc_id: docId,
    ordinal,
    block_type: "paragraph",
    content,
    heading_stack: [],
    section_label: null,
    structural_meta: {},
    style_hint: {},
    image: null,
  };
}

function annotation(
  overrides: Partial<DocumentAnnotation<Kind, { ref: string }>> &
    Pick<DocumentAnnotation<Kind, { ref: string }>, "id" | "kind" | "blockIds">,
): DocumentAnnotation<Kind, { ref: string }> {
  const { id, kind, blockIds, ...rest } = overrides;
  return {
    id,
    kind,
    layerLabel: kind === "field" ? "Field" : "Assessment",
    title: "Title",
    summary: "Summary",
    blockIds,
    spans: [],
    sourceRef: { ref: id },
    ...rest,
  };
}

test("highlights an exact quote while preserving original source text", () => {
  const source = block(
    "document/b-0001",
    1,
    "Target efficacy is greater than 80%\n  at twelve months.",
  );
  const result = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{
        quote: "target EFFICACY is greater than 80% at twelve months.",
        blockIds: [source.id],
      }],
    }),
  ]);

  assert.equal(result.documents.length, 1);
  assert.equal(result.documents[0].blocks.length, 1);
  assert.equal(
    result.documents[0].blocks[0].segments.map((segment) => segment.text).join(""),
    source.content,
  );
  assert.deepEqual(
    result.documents[0].blocks[0].segments
      .filter((segment) => segment.annotationIds.length > 0)
      .flatMap((segment) => segment.annotationIds),
    ["field-1"],
  );
  assert.deepEqual(result.documents[0].blocks[0].markers, []);
});

test("preserves exact offsets when Unicode normalization expands source text", () => {
  const sources = [
    block("document/b-0001", 1, "İ exact target"),
    block("document/b-0002", 2, "A&#x1F600; exact target"),
  ];
  const result = buildDocumentTrace(sources, [
    annotation({
      id: "unicode-letter",
      kind: "field",
      blockIds: [sources[0].id],
      spans: [{ quote: "i̇ exact target", blockIds: [sources[0].id] }],
    }),
    annotation({
      id: "unicode-entity",
      kind: "field",
      blockIds: [sources[1].id],
      spans: [{ quote: "A😀 exact target", blockIds: [sources[1].id] }],
    }),
  ]);

  for (const [index, source] of sources.entries()) {
    const traceBlock = result.documents[0].blocks[index];
    assert.equal(traceBlock.segments.map((segment) => segment.text).join(""), source.content);
    assert.equal(traceBlock.segments.some((segment) => segment.annotationIds.length > 0), true);
    assert.deepEqual(traceBlock.markers, []);
  }
});

test("treats invalid numeric entities as literal source text without throwing", () => {
  const source = block("document/b-0001", 1, "Invalid &#x110000; target");
  const result = buildDocumentTrace([source], [
    annotation({
      id: "invalid-entity",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: source.content, blockIds: [source.id] }],
    }),
  ]);

  assert.equal(
    result.documents[0].blocks[0].segments.map((segment) => segment.text).join(""),
    source.content,
  );
});

test("does not use fuzzy matching and falls back to a block marker", () => {
  const source = block("document/b-0001", 1, "Target efficacy is 80%.");
  const result = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "Target efficacy is 85%.", blockIds: [source.id] }],
    }),
  ]);

  assert.deepEqual(result.documents[0].blocks[0].segments, [
    { text: source.content, annotationIds: [], start: 0, end: source.content.length },
  ]);
  assert.deepEqual(
    result.documents[0].blocks[0].markers.map((item) => ({
      id: item.annotation.id,
      reason: item.reason,
      unmatchedQuotes: item.unmatchedQuotes,
    })),
    [{
      id: "field-1",
      reason: "quote_unmatched",
      unmatchedQuotes: ["Target efficacy is 85%."],
    }],
  );
});

test("clips exact trace segments to parser-owned table-cell offsets", () => {
  const source = block(
    "document/b-0001",
    1,
    "Measure: Efficacy, Target: >= 75%",
  );
  const result = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "Efficacy", blockIds: [source.id] }],
    }),
  ]);

  assert.deepEqual(
    documentTraceSegmentsInRange(result.documents[0].blocks[0].segments, 9, 17),
    [{ text: "Efficacy", annotationIds: ["field-1"], start: 9, end: 17 }],
  );
});

test("unions overlapping annotations without merging their records", () => {
  const source = block("document/b-0001", 1, "Protective efficacy exceeds 80% at 12 months.");
  const result = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "Protective efficacy exceeds 80%", blockIds: [source.id] }],
    }),
    annotation({
      id: "assessment-1",
      kind: "assessment",
      blockIds: [source.id],
      spans: [{ quote: "efficacy exceeds 80% at 12 months", blockIds: [source.id] }],
    }),
  ]);

  assert.ok(
    result.documents[0].blocks[0].segments.some(
      (segment) =>
        segment.annotationIds.includes("field-1") &&
        segment.annotationIds.includes("assessment-1"),
    ),
  );
  assert.equal(result.annotations.length, 2);
});

test("matches exact spans only inside their declared source blocks", () => {
  const first = block("document/b-0001", 1, "The repeated target is 80%.");
  const second = block("document/b-0002", 2, "The repeated target is 80%.");
  const result = buildDocumentTrace([first, second], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [first.id, second.id],
      spans: [{ quote: "The repeated target is 80%.", blockIds: [second.id] }],
    }),
  ]);

  assert.equal(
    result.documents[0].blocks[0].segments.some((segment) => segment.annotationIds.length > 0),
    false,
  );
  assert.equal(
    result.documents[0].blocks[1].segments.some((segment) => segment.annotationIds.includes("field-1")),
    true,
  );
});

test("uses a marker for block-only lineage and ignores unknown blocks", () => {
  const source = block("document/b-0001", 1, "A retained passage.");
  const result = buildDocumentTrace([source], [
    annotation({ id: "known", kind: "assessment", blockIds: [source.id] }),
    annotation({ id: "unknown", kind: "assessment", blockIds: ["document/b-9999"] }),
  ]);

  assert.deepEqual(
    result.documents[0].blocks[0].markers.map((item) => ({
      id: item.annotation.id,
      reason: item.reason,
    })),
    [{ id: "known", reason: "block_only" }],
  );
  assert.deepEqual(result.unresolvedAnnotationIds, ["unknown"]);
  assert.deepEqual(result.unresolvedBlockIdsByAnnotation, {
    unknown: ["document/b-9999"],
  });
});

test("retains missing block citations when another cited block is available", () => {
  const source = block("document/b-0001", 1, "A retained passage.");
  const result = buildDocumentTrace([source], [
    annotation({
      id: "mixed",
      kind: "assessment",
      blockIds: [source.id, "document/b-9999"],
    }),
  ]);

  assert.deepEqual(
    result.documents[0].blocks[0].markers.map((item) => item.annotation.id),
    ["mixed"],
  );
  assert.deepEqual(result.unresolvedAnnotationIds, ["mixed"]);
  assert.deepEqual(result.unresolvedBlockIdsByAnnotation, {
    mixed: ["document/b-9999"],
  });
});

test("sorts documents and blocks without mutating inputs", () => {
  const blocks = [
    block("z/b-0002", 2, "Second", "z"),
    block("a/b-0001", 1, "First", "a"),
    block("z/b-0001", 1, "First in z", "z"),
  ];
  const annotations = [
    annotation({ id: "z", kind: "field", blockIds: ["z/b-0001"] }),
  ];
  const blocksBefore = structuredClone(blocks);
  const annotationsBefore = structuredClone(annotations);

  const result = buildDocumentTrace(blocks, annotations);

  assert.deepEqual(result.documents.map((document) => document.docId), ["a", "z"]);
  assert.deepEqual(
    result.documents[1].blocks.map((item) => item.block.id),
    ["z/b-0001", "z/b-0002"],
  );
  assert.deepEqual(blocks, blocksBefore);
  assert.deepEqual(annotations, annotationsBefore);
});

test("filters annotations by layer without changing source order", () => {
  const annotations = [
    annotation({ id: "one", kind: "field", blockIds: ["document/b-0001"] }),
    annotation({ id: "two", kind: "assessment", blockIds: ["document/b-0001"] }),
    annotation({ id: "three", kind: "field", blockIds: ["document/b-0002"] }),
  ];

  assert.deepEqual(
    filterDocumentAnnotations(annotations, "field").map((item) => item.id),
    ["one", "three"],
  );
  assert.deepEqual(
    filterDocumentAnnotations(annotations, "all").map((item) => item.id),
    ["one", "two", "three"],
  );
});

test("resolves a uniquely connected exact result when focusing a block", () => {
  const source = block("document/b-0001", 1, "Target efficacy exceeds 80%.");
  const trace = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "efficacy exceeds 80%", blockIds: [source.id] }],
    }),
  ]);

  assert.deepEqual(documentTraceFocusTarget(trace, source.id), {
    documentId: "document",
    blockId: source.id,
    annotationIds: ["field-1"],
    selectedAnnotationId: "field-1",
    connection: { type: "exact", blockId: source.id },
  });
});

test("resolves a uniquely connected block-level result without inventing an exact quote", () => {
  const source = block("document/b-0001", 1, "A retained passage.");
  const trace = buildDocumentTrace([source], [
    annotation({ id: "assessment-1", kind: "assessment", blockIds: [source.id] }),
  ]);

  assert.deepEqual(documentTraceFocusTarget(trace, source.id), {
    documentId: "document",
    blockId: source.id,
    annotationIds: ["assessment-1"],
    selectedAnnotationId: "assessment-1",
    connection: {
      type: "block",
      blockId: source.id,
      markerReason: "block_only",
      unmatchedQuotes: [],
    },
  });
});

test("focuses an ambiguously connected block without choosing a result", () => {
  const source = block("document/b-0001", 1, "Target efficacy exceeds 80%.");
  const trace = buildDocumentTrace([source], [
    annotation({
      id: "field-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "efficacy exceeds 80%", blockIds: [source.id] }],
    }),
    annotation({ id: "assessment-1", kind: "assessment", blockIds: [source.id] }),
  ]);

  assert.deepEqual(documentTraceFocusTarget(trace, source.id), {
    documentId: "document",
    blockId: source.id,
    annotationIds: ["field-1", "assessment-1"],
    selectedAnnotationId: null,
    connection: null,
  });
});

test("does not resolve a focus target for an unknown block", () => {
  const trace = buildDocumentTrace(
    [block("document/b-0001", 1, "A retained passage.")],
    [],
  );

  assert.equal(documentTraceFocusTarget(trace, "document/b-9999"), null);
});

test("groups block-level connections by reason without losing result IDs", () => {
  const source = block("document/b-0001", 1, "A retained passage.");
  const result = buildDocumentTrace([source], [
    annotation({ id: "one", kind: "field", blockIds: [source.id] }),
    annotation({ id: "two", kind: "assessment", blockIds: [source.id] }),
    annotation({
      id: "three",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "A different passage.", blockIds: [source.id] }],
    }),
  ]);
  const markers = result.documents[0].blocks[0].markers;
  const before = structuredClone(markers);

  assert.deepEqual(groupDocumentTraceMarkers(markers), [
    {
      reason: "block_only",
      annotationIds: ["one", "two"],
      unmatchedQuotes: [],
    },
    {
      reason: "quote_unmatched",
      annotationIds: ["three"],
      unmatchedQuotes: ["A different passage."],
    },
  ]);
  assert.deepEqual(
    groupDocumentTraceMarkers(markers).map((group) => ({
      reason: group.reason,
      count: group.annotationIds.length,
    })),
    [
      { reason: "block_only", count: 2 },
      { reason: "quote_unmatched", count: 1 },
    ],
  );
  assert.deepEqual(markers, before);
});

test("decodes the scientific entities the server's html.unescape decodes", () => {
  // A source block carrying entities the server folds before matching. Each of
  // these is outside the original six-entity map, so the span would not have
  // highlighted even though conformity._normalize_quote accepts it.
  const source = block(
    "document/b-0100",
    1,
    "Storage at 2&ndash;8&deg;C with &le;5&percnt; loss and &micro;g dosing.",
  );

  const result = buildDocumentTrace([source], [
    annotation({
      id: "entity-span",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "Storage at 2–8°C with ≤5&percnt; loss", blockIds: [source.id] }],
    }),
  ]);

  const highlighted = result.documents[0].blocks[0].segments
    .filter((segment) => segment.annotationIds.length > 0);
  assert.ok(highlighted.length > 0, "entity-bearing span did not highlight");
  assert.equal(
    result.documents[0].blocks[0].segments.map((segment) => segment.text).join(""),
    source.content,
  );
});
