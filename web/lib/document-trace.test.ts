import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import type { ContentBlock } from "./api.ts";
import {
  buildDocumentTrace,
  documentTraceFocusTarget,
  documentTraceSegmentsInRange,
  filterDocumentAnnotations,
  groupDocumentTraceMarkers,
  strongestEmphasis,
  type DocumentAnnotation,
} from "./document-trace.ts";

const WEB_ROOT = path.resolve(import.meta.dirname, "..");

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

// ---------------------------------------------------------------------------
// Absence, anchoring, and whole-block emphasis
//
// Added for the Inspector adapter, but these belong to the shared contract: any
// tool may claim a whole block or describe content that is not present.
// ---------------------------------------------------------------------------

/** Every place the viewer can surface an annotation. */
function reachableIds(
  trace: ReturnType<typeof buildDocumentTrace<Kind, { ref: string }>>,
): Set<string> {
  const ids = new Set<string>();
  for (const document of trace.documents) {
    for (const traceBlock of document.blocks) {
      for (const segment of traceBlock.segments) {
        segment.annotationIds.forEach((id) => ids.add(id));
      }
      traceBlock.markers.forEach((marker) => ids.add(marker.annotation.id));
      traceBlock.anchored.forEach((item) => ids.add(item.id));
    }
  }
  trace.unresolvedAnnotationIds.forEach((id) => ids.add(id));
  trace.unplacedAnnotationIds.forEach((id) => ids.add(id));
  return ids;
}

test("no annotation is silently dropped", () => {
  const blocks = [block("b-1", 1, "Minimum: 60%"), block("b-2", 2, "Safety data")];
  const annotations = [
    annotation({
      id: "exact",
      kind: "field",
      blockIds: ["b-1"],
      spans: [{ quote: "60%", blockIds: ["b-1"] }],
    }),
    annotation({ id: "block-only", kind: "field", blockIds: ["b-1"] }),
    annotation({ id: "unresolved", kind: "field", blockIds: ["b-404"] }),
    annotation({ id: "anchored", kind: "assessment", blockIds: [], displayAnchorBlockId: "b-2" }),
    annotation({ id: "unplaced", kind: "assessment", blockIds: [] }),
    annotation({ id: "bad-anchor", kind: "assessment", blockIds: [], displayAnchorBlockId: "b-404" }),
  ];

  const trace = buildDocumentTrace(blocks, annotations);
  const reachable = reachableIds(trace);
  assert.deepEqual(
    annotations.map((item) => item.id).filter((id) => !reachable.has(id)),
    [],
    "an annotation reachable from nowhere is present in data and invisible in the UI",
  );
});

test("an anchored annotation sits beside its block, never inside its text", () => {
  const blocks = [block("b-1", 1, "Minimum: 60%"), block("b-2", 2, "Safety data")];
  const trace = buildDocumentTrace(blocks, [
    annotation({ id: "gap", kind: "assessment", blockIds: [], displayAnchorBlockId: "b-2" }),
  ]);

  const [first, second] = trace.documents[0].blocks;
  assert.deepEqual(second.anchored.map((item) => item.id), ["gap"]);
  assert.deepEqual(first.anchored, []);
  assert.deepEqual(
    second.segments.flatMap((segment) => segment.annotationIds),
    [],
    "a display anchor never highlights the block's text",
  );
  assert.deepEqual(second.markers, [], "a display anchor is not a provenance marker");
});

test("an unusable display anchor degrades to unplaced, never to a wrong block", () => {
  const blocks = [block("b-1", 1, "Minimum: 60%")];
  const trace = buildDocumentTrace(blocks, [
    annotation({ id: "gap", kind: "assessment", blockIds: [], displayAnchorBlockId: "b-404" }),
  ]);

  assert.deepEqual(trace.unplacedAnnotationIds, ["gap"]);
  assert.deepEqual(trace.documents[0].blocks[0].anchored, []);
});

test("unplaced and unresolved are different claims", () => {
  const blocks = [block("b-1", 1, "Minimum: 60%")];
  const trace = buildDocumentTrace(blocks, [
    annotation({ id: "cites-missing-block", kind: "field", blockIds: ["b-404"] }),
    annotation({ id: "has-no-lineage", kind: "assessment", blockIds: [] }),
  ]);

  assert.deepEqual(
    trace.unresolvedAnnotationIds,
    ["cites-missing-block"],
    "citing a block the document lacks is a data problem",
  );
  assert.deepEqual(
    trace.unplacedAnnotationIds,
    ["has-no-lineage"],
    "having no lineage at all can be the substance of a finding",
  );
});

test("block emphasis takes the strongest tone and that claim's badge", () => {
  assert.equal(strongestEmphasis([]), null);
  assert.deepEqual(
    strongestEmphasis([
      annotation({ id: "a", kind: "field", blockIds: [], emphasis: { tone: "neutral", badge: "A" } }),
      annotation({ id: "f", kind: "field", blockIds: [], emphasis: { tone: "danger", badge: "F" } }),
      annotation({ id: "c", kind: "field", blockIds: [], emphasis: { tone: "caution", badge: "C" } }),
    ]),
    { tone: "danger", badge: "F" },
  );
  assert.deepEqual(
    strongestEmphasis([
      annotation({ id: "a", kind: "field", blockIds: [], emphasis: { tone: "caution", badge: "first" } }),
      annotation({ id: "b", kind: "field", blockIds: [], emphasis: { tone: "caution", badge: "second" } }),
    ]),
    { tone: "caution", badge: "first" },
    "ties break by declaration order so the rendered badge is deterministic",
  );
});

test("emphasis resolves per block from the annotations claiming it", () => {
  const blocks = [block("b-1", 1, "Minimum: 60%"), block("b-2", 2, "Safety data")];
  const trace = buildDocumentTrace(blocks, [
    annotation({ id: "a", kind: "field", blockIds: ["b-1"], emphasis: { tone: "neutral", badge: "A" } }),
    annotation({ id: "f", kind: "field", blockIds: ["b-1"], emphasis: { tone: "danger", badge: "F" } }),
  ]);

  const [first, second] = trace.documents[0].blocks;
  assert.deepEqual(first.emphasis, { tone: "danger", badge: "F" });
  assert.equal(second.emphasis, null, "an unclaimed block carries no emphasis");
});

test("no adapter sets a display anchor beside real block lineage", () => {
  // An absence cannot cite a block. The type system cannot express "these two
  // fields are mutually exclusive" without making the common case awkward, so
  // the rule is enforced here rather than left to a comment nobody re-reads.
  const offenders: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (!/\.tsx?$/.test(entry) || /\.test\.tsx?$/.test(entry)) continue;
      const text = readFileSync(full, "utf8");
      if (!text.includes("displayAnchorBlockId")) continue;
      for (const [literal] of text.matchAll(/\{[^{}]*displayAnchorBlockId[^{}]*\}/g)) {
        if (/blockIds:\s*(?!\[\])/.test(literal)) {
          offenders.push(`${path.relative(WEB_ROOT, full)}: ${literal.slice(0, 80)}`);
        }
      }
    }
  };
  for (const dir of ["app", "components", "lib"]) walk(path.join(WEB_ROOT, dir));
  assert.deepEqual(
    offenders,
    [],
    "an annotation with a display anchor must declare blockIds: []",
  );
});
