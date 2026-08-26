import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import type { ContentBlock } from "./api.ts";
import {
  buildDocumentTrace,
  displayDocumentName,
  documentTraceBlockLocation,
  documentTracePassages,
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

test("locating a block reports its document and every mark on it", () => {
  // Both kinds of mark count: revealing a passage has to know whether the current
  // layer is hiding all of them, and an exact span and a block marker are equally a
  // reason the reader was sent here.
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

  assert.deepEqual(documentTraceBlockLocation(trace, source.id), {
    documentId: "document",
    annotationIds: ["field-1", "assessment-1"],
  });
});

test("locating a block names the document that holds it", () => {
  const profile = block("profile/b-0001", 1, "Present.", "profile");
  const plan = block("plan/b-0001", 1, "Present.", "plan");
  const trace = buildDocumentTrace([profile, plan], [
    annotation({ id: "a-1", kind: "field", blockIds: [profile.id, plan.id] }),
  ]);
  assert.equal(documentTraceBlockLocation(trace, plan.id)?.documentId, "plan");
});

test("an unmarked block is still locatable, with no marks", () => {
  // The document is the whole document, so a reader can be sent to a passage no
  // result cites — from a block reference, say. That is not a failure to resolve.
  const source = block("document/b-0001", 1, "A retained passage.");
  const trace = buildDocumentTrace([source], []);
  assert.deepEqual(documentTraceBlockLocation(trace, source.id), {
    documentId: "document",
    annotationIds: [],
  });
});

test("an unknown block has no location", () => {
  const trace = buildDocumentTrace(
    [block("document/b-0001", 1, "A retained passage.")],
    [],
  );
  assert.equal(documentTraceBlockLocation(trace, "document/b-9999"), null);
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

test("lineage wins over a display anchor, so the pair cannot mislead", () => {
  // The anchor is placement, the blocks are provenance. Rather than forbidding
  // the combination by scanning source text for it - a check that reads code as
  // strings and breaks on formatting - the engine gives lineage precedence and
  // never reads the anchor when blocks exist. The illegal state is harmless
  // instead of policed.
  const blocks = [block("b-1", 1, "Minimum: 60%"), block("b-2", 2, "Safety data")];
  const trace = buildDocumentTrace(blocks, [
    annotation({
      id: "both",
      kind: "field",
      blockIds: ["b-1"],
      displayAnchorBlockId: "b-2",
    }),
  ]);

  const [first, second] = trace.documents[0].blocks;
  assert.deepEqual(
    first.markers.map((marker) => marker.annotation.id),
    ["both"],
    "an annotation with lineage is placed on the block it cites",
  );
  assert.deepEqual(second.anchored, [], "its anchor is not consulted");
  assert.deepEqual(trace.unplacedAnnotationIds, []);
});

test("an annotation's passages are listed in document order, not citation order", () => {
  // The list doubles as a map of where an answer is spread through a document, so a
  // reader stepping down it moves downward through the text.
  const first = block("document/b-0001", 1, "The target shelf life is 24 months.");
  const second = block("document/b-0002", 2, "Storage is 2-8 degrees Celsius.");
  const trace = buildDocumentTrace([first, second], [
    annotation({
      id: "a-1",
      kind: "field",
      // Cited out of order on purpose.
      blockIds: [second.id, first.id],
    }),
  ]);

  assert.deepEqual(
    documentTracePassages(trace, "a-1").map((passage) => passage.blockId),
    [first.id, second.id],
  );
});

test("each passage carries where it sits and how the result attaches to it", () => {
  const source: ContentBlock = {
    ...block("document/b-0001", 1, "Target efficacy is greater than 80% at twelve months."),
    section_label: "Efficacy",
  };
  const trace = buildDocumentTrace([source], [
    annotation({
      id: "a-1",
      kind: "field",
      blockIds: [source.id],
      spans: [{ quote: "Target efficacy is greater than 80%", blockIds: [source.id] }],
    }),
  ]);

  const [passage] = documentTracePassages(trace, "a-1");
  assert.equal(passage.sectionLabel, "Efficacy");
  assert.equal(passage.connection, "exact");
  assert.equal(passage.preview, "Target efficacy is greater than 80% at twelve months.");
  assert.equal(passage.documentId, "document");
});

test("a passage falls back to its nearest heading when it declares no section", () => {
  const source: ContentBlock = {
    ...block("document/b-0001", 1, "Two doses, four weeks apart."),
    heading_stack: ["Clinical", "Regimen"],
  };
  const trace = buildDocumentTrace([source], [
    annotation({ id: "a-1", kind: "field", blockIds: [source.id] }),
  ]);
  assert.equal(documentTracePassages(trace, "a-1")[0].sectionLabel, "Regimen");
});

test("a whole-block citation is reported as a block connection, not an exact one", () => {
  const source = block("document/b-0001", 1, "Manufacturing scale is not yet fixed.");
  const trace = buildDocumentTrace([source], [
    annotation({ id: "a-1", kind: "assessment", blockIds: [source.id] }),
  ]);
  assert.equal(documentTracePassages(trace, "a-1")[0].connection, "block");
});

test("a long passage is previewed at a word boundary", () => {
  const source = block(
    "document/b-0001",
    1,
    "Stability data are available for zones I and II across twenty-four months, with "
      + "accelerated data at forty degrees, and a vaccine vial monitor category is not "
      + "stated anywhere in the profile.",
  );
  const trace = buildDocumentTrace([source], [
    annotation({ id: "a-1", kind: "field", blockIds: [source.id] }),
  ]);
  const { preview } = documentTracePassages(trace, "a-1")[0];
  assert.ok(preview.endsWith("…"), preview);
  assert.ok(preview.length <= 111, `${preview.length}`);
  assert.ok(!preview.includes("  "));
  // The cut lands between words: no half word before the ellipsis.
  assert.ok(source.content.startsWith(preview.slice(0, -1)), preview);
});

test("passages span every document a result was read from", () => {
  // This is the case a count could never serve: two documents, and the viewer shows
  // one at a time, so the reader has no way to learn the other citation exists.
  const profile = block("profile/b-0001", 1, "Target shelf life is 24 months.", "profile");
  const plan = block("plan/b-0001", 1, "Stability studies start in Q3.", "plan");
  const trace = buildDocumentTrace([profile, plan], [
    annotation({ id: "a-1", kind: "field", blockIds: [profile.id, plan.id] }),
  ]);
  // Grouped in the trace's own document order, which is the order of the switcher
  // above the list, so stepping down the list runs the switcher forward rather than
  // jumping back and forth between documents.
  assert.deepEqual(
    documentTracePassages(trace, "a-1").map((passage) => passage.documentId),
    trace.documents.map((document) => document.docId),
  );
});

test("a display anchor is never listed as a passage", () => {
  // An anchor is where an absence is shown. Listing it would turn a placement
  // decision into a source citation.
  const source = block("document/b-0001", 1, "Clinical development plan.");
  const trace = buildDocumentTrace([source], [
    annotation({
      id: "a-1",
      kind: "assessment",
      blockIds: [],
      displayAnchorBlockId: source.id,
    }),
  ]);
  assert.deepEqual(documentTracePassages(trace, "a-1"), []);
});

test("a cited block the document does not contain is not offered as a passage", () => {
  // It cannot be opened, and the viewer reports it as unavailable instead.
  const source = block("document/b-0001", 1, "Present.");
  const trace = buildDocumentTrace([source], [
    annotation({ id: "a-1", kind: "field", blockIds: [source.id, "document/b-9999"] }),
  ]);
  assert.deepEqual(
    documentTracePassages(trace, "a-1").map((passage) => passage.blockId),
    [source.id],
  );
  assert.deepEqual(trace.unresolvedBlockIdsByAnnotation["a-1"], ["document/b-9999"]);
});

test("a document is named the same way wherever it is shown", () => {
  assert.equal(displayDocumentName("product_profile"), "product profile");
  assert.equal(displayDocumentName("dev-plan"), "dev plan");
  assert.equal(displayDocumentName(""), "Source document");
});

test("the shared trace layer imports nothing tool-specific", () => {
  // An import graph assertion, not a keyword scan: the rule is that a shared
  // module may not depend on a tool's adapter, types, or vocabulary. Naming a
  // tool in a comment to explain a shared decision is fine and expected.
  const SHARED = [
    "lib/document-trace.ts",
    "lib/document-block-presentation.ts",
    "components/document-trace-viewer.tsx",
    "components/document-trace-panel.tsx",
    "components/ui/signal-help.tsx",
  ];
  const TOOL_MODULE = /^(?:\.{1,2}\/|@\/)(?:.*\/)?(?:scout|inspector|aligner|chunker)[-/]/;

  const offenders: string[] = [];
  for (const relative of SHARED) {
    const text = readFileSync(path.join(WEB_ROOT, relative), "utf8");
    for (const [, specifier] of text.matchAll(/from\s+"([^"]+)"/g)) {
      if (TOOL_MODULE.test(specifier)) offenders.push(`${relative} -> ${specifier}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "a shared trace module depends on one tool, so the next tool inherits its assumptions",
  );
});

test("every tool adapter presents the same surface", () => {
  // Symmetry is what lets a reader learn one adapter and understand the rest.
  const ADAPTERS = [
    { module: "lib/scout-document-trace.ts", build: "buildScoutDocumentAnnotations" },
    { module: "lib/inspector-document-trace.ts", build: "buildInspectorDocumentAnnotations" },
    { module: "lib/expert-document-trace.ts", build: "buildExpertDocumentAnnotations" },
  ];
  for (const { module, build } of ADAPTERS) {
    const text = readFileSync(path.join(WEB_ROOT, module), "utf8");
    assert.ok(
      text.includes(`export function ${build}`),
      `${module} must export ${build}`,
    );
    assert.ok(
      /export type \w+DocumentTraceKind/.test(text),
      `${module} must declare its own closed layer vocabulary`,
    );
    assert.ok(
      /export type \w+DocumentAnnotation\b/.test(text),
      `${module} must name its annotation type`,
    );
  }
});

test("no inspector renders a passage count in place of the passages", () => {
  // The regression this exists for: a count reads as provenance while being
  // unnavigable, so every citation after the first was asserted and unreachable.
  // Any tool adding a trace inherits the list rather than reinventing the number.
  const INSPECTORS = [
    "components/scout-document-trace.tsx",
    "components/inspector-document-trace.tsx",
    "components/expert-document-trace.tsx",
  ];
  for (const module of INSPECTORS) {
    const text = readFileSync(path.join(WEB_ROOT, module), "utf8");
    assert.ok(
      text.includes("<TracePassageList"),
      `${module} must list its passages, not count them`,
    );
    assert.ok(
      !/\{\s*annotation\.blockIds\.length\s*\}/.test(text),
      `${module} must not render a bare citation count`,
    );
  }
});

test("one meaning takes one tone, and every tool draws from the same four", () => {
  // The point of a shared vocabulary is that a reader learns it once. Two tools using
  // different colours for "the thing asked for is there", or one tool using two shades of
  // the same colour for two meanings, both break that — and neither is visible from
  // inside a single tool's file.
  const sources = [
    "lib/expert-document-trace.ts",
    "lib/aligner-document-trace.ts",
    "lib/inspector-document-trace.ts",
  ].map((module) => readFileSync(path.join(WEB_ROOT, module), "utf8"));

  const allowed = new Set(["success", "caution", "danger", "neutral"]);
  for (const source of sources) {
    for (const [, tone] of source.matchAll(/tone: "(\w+)"/g)) {
      assert.ok(allowed.has(tone), `${tone} is not one of the shared tones`);
    }
  }

  // "The thing asked for is there" is success everywhere it appears.
  const [expert, aligner] = sources;
  assert.match(expert, /question\.state === "answered"\s*\n?\s*\? \{ tone: "success"/);
  // Aligner's verdict tones moved to `ALIGNMENT_VERDICT_TONE`, read by both the count row
  // and this trace, so the judgement is made once and the trace translates `warning` to
  // its own `caution`. Checked at the source rather than at the translation, which is
  // where a second opinion would appear if one were ever introduced.
  const verdictTone = readFileSync(path.join(WEB_ROOT, "lib", "api.ts"), "utf8");
  assert.match(verdictTone, /meets: "success"/);
  assert.match(verdictTone, /exceeds: "success"/);
  assert.match(
    aligner,
    /ALIGNMENT_VERDICT_TONE\[verdict\] === "warning" \? "caution"/,
    "the aligner trace decides its own tones again instead of translating the shared map",
  );
});

test("a block claimed twice shows the tone a reader most needs", () => {
  // A passage that answers one question and contradicts another has to show the
  // contradiction, and a claim outranks the absence of one.
  const source = block("document/b-0001", 1, "A retained passage.");
  const trace = buildDocumentTrace([source], [
    annotation({
      id: "a-1",
      kind: "assessment",
      blockIds: [source.id],
      emphasis: { tone: "success", badge: "Answered" },
    }),
    annotation({
      id: "a-2",
      kind: "assessment",
      blockIds: [source.id],
      emphasis: { tone: "danger", badge: "Not met" },
    }),
  ]);
  assert.equal(trace.documents[0].blocks[0].emphasis?.tone, "danger");

  const quieter = buildDocumentTrace([source], [
    annotation({
      id: "a-1",
      kind: "assessment",
      blockIds: [source.id],
      emphasis: { tone: "neutral", badge: "Requirement" },
    }),
    annotation({
      id: "a-2",
      kind: "assessment",
      blockIds: [source.id],
      emphasis: { tone: "success", badge: "Meets" },
    }),
  ]);
  assert.equal(quieter.documents[0].blocks[0].emphasis?.tone, "success");
});
