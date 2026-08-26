import type { Tone } from "./tone.ts";
import type { ContentBlock } from "./api.ts";

/**
 * Whole-block emphasis for an annotation whose granularity *is* the block.
 *
 * A span addresses text; a block-level judgement addresses everything the block
 * contains. `tone` is semantic rather than a numeric severity because a numeric
 * range would encode one tool's grading scale into a contract every tool shares.
 * Colour is never the only signal — `badge` carries the precise claim as text.
 *
 * Four tones, and the set is deliberately small: a reader learns them once and carries
 * them between tools, so the same meaning must take the same colour everywhere and two
 * shades of one colour must never mean two things.
 *
 *   success   the thing asked for is there — answered, met, exceeded, confirmed
 *   caution   partly there, or there in terms that cannot be compared
 *   danger    contradicted, or a shortfall the tool grades as blocking
 *   neutral   nothing was found, or nothing is claimed about it
 *
 * `neutral` is the one to be careful with. It reads as "ignored", so it belongs only
 * where nothing is being said — an unmarked citation, an absence. An answered passage
 * shown in grey looked like a passage nobody had looked at.
 */
export type DocumentAnnotationEmphasis = {
  /**
   * The shared tone, not a second list.
   *
   * This declared its own four values and called the middle one `caution` while
   * `lib/tone.ts` called it `warning`. One thing, two names - and `aligner-document-trace`
   * carried a line whose whole job was translating between them.
   */
  tone: Tone;
  /** Short text, e.g. a grade letter. */
  badge?: string;
};

export type DocumentAnnotation<
  TKind extends string = string,
  TRef = unknown,
> = {
  id: string;
  kind: TKind;
  layerLabel: string;
  title: string;
  summary: string;
  statusLabel?: string;
  blockIds: string[];
  spans: Array<{
    quote: string;
    blockIds: string[];
  }>;
  emphasis?: DocumentAnnotationEmphasis;
  /**
   * Who wrote `summary`. Stated where the text is chosen, not guessed at render time.
   *
   * Scout's trace is the reason this is not assumed: its six annotation kinds draw their
   * summary from six places, and two of them - a field's `document_target` and a target's
   * `quote` - are the document's own words. Rendered as a model's, they carried the
   * authorship mark, which is the tool claiming it wrote the reader's document.
   *
   * Defaults to `reading` because the other three tools' summaries are all a model's
   * sentence about the document.
   */
  summaryMode?: "quoted" | "reading";
  /**
   * Where to *display* an annotation that has no document lineage.
   *
   * Never a provenance claim. An absence — a missing rubric variable, a section
   * that was never written — cannot cite a block, so `blockIds` stays empty and
   * the annotation renders beside the anchor without attaching to its text.
   * Setting both is a contract violation that `document-trace.test.ts` rejects.
   */
  displayAnchorBlockId?: string;
  sourceRef: TRef;
};

export type DocumentTraceSegment = {
  text: string;
  annotationIds: string[];
  start: number;
  end: number;
};

export type DocumentTraceBlock<
  TKind extends string = string,
  TRef = unknown,
> = {
  block: ContentBlock;
  segments: DocumentTraceSegment[];
  markers: Array<{
    annotation: DocumentAnnotation<TKind, TRef>;
    reason: "block_only" | "quote_unmatched";
    unmatchedQuotes: string[];
  }>;
  /**
   * Annotations with no lineage that name this block as their display anchor.
   * They are shown beside the block, never as part of its content.
   */
  anchored: Array<DocumentAnnotation<TKind, TRef>>;
  /** Strongest emphasis claimed over this block, or null when none is. */
  emphasis: DocumentAnnotationEmphasis | null;
};

export type DocumentTraceDocument<
  TKind extends string = string,
  TRef = unknown,
> = {
  docId: string;
  blocks: Array<DocumentTraceBlock<TKind, TRef>>;
};

export type DocumentTrace<
  TKind extends string = string,
  TRef = unknown,
> = {
  documents: Array<DocumentTraceDocument<TKind, TRef>>;
  annotations: Array<DocumentAnnotation<TKind, TRef>>;
  /** Annotations citing blocks the retained document does not contain. */
  unresolvedAnnotationIds: string[];
  unresolvedBlockIdsByAnnotation: Record<string, string[]>;
  /**
   * Annotations with no lineage that could not be anchored — either no anchor
   * was supplied or it named an unknown block.
   *
   * Distinct from `unresolved`: an unresolved annotation cites a block that is
   * missing, which is a data problem. An unplaced annotation never had lineage,
   * which for a completeness finding is the substance of the finding itself.
   */
  unplacedAnnotationIds: string[];
};

export type DocumentTraceConnection = {
  type: "exact" | "block" | "unavailable";
  blockId?: string;
  markerReason?: "block_only" | "quote_unmatched";
  unmatchedQuotes?: string[];
  unavailableBlockIds?: string[];
};

/**
 * Where a block is, and what marks it.
 *
 * The two things revealing a passage has to know: which document to switch to, and
 * whether the current layer filter is hiding the mark a reader is being sent to see.
 *
 * It used to also nominate a result to select, on the rule "select it only when the
 * block has exactly one". Revealing no longer selects anything — landing on the
 * passage and opening a panel about it are separate acts, and the second is the
 * reader's — so nominating one was a decision with no consumer.
 */
export type DocumentTraceBlockLocation = {
  documentId: string;
  annotationIds: string[];
};

/**
 * One passage an annotation was read from, described well enough to choose between.
 *
 * A result routinely cites several passages, and until this existed the panel could
 * only say how many: the count was the whole of it, so every passage after the one
 * you arrived at was unreachable. Nothing here is new evidence — it is the lineage
 * the annotation already carries, resolved against the retained document so each
 * citation can be named and navigated to.
 */
export type DocumentTracePassage = {
  blockId: string;
  documentId: string;
  /** Where the passage sits: the nearest heading the block declares, if any. */
  sectionLabel: string;
  /** The passage's opening words, so the list reads without navigating away. */
  preview: string;
  /** How the annotation attaches here — an exact quotation, or the whole block. */
  connection: "exact" | "block";
};

/** Longest preview kept. Two lines in the panel, which is as much as it can show. */
const PASSAGE_PREVIEW_LIMIT = 110;

function passagePreview(content: string): string {
  const flat = content.replace(/\s+/g, " ").trim();
  if (flat.length <= PASSAGE_PREVIEW_LIMIT) return flat;
  // Cut back to a word boundary: a preview ending mid-word reads as corruption.
  return `${flat.slice(0, PASSAGE_PREVIEW_LIMIT).replace(/\s+\S*$/, "")}…`;
}

/**
 * Every passage one annotation was read from, in document order.
 *
 * Document order, not citation order, because the list doubles as a map of where
 * the answer is spread through the document, and a reader stepping through it
 * moves downward rather than jumping about.
 *
 * `anchored` annotations are deliberately excluded. A display anchor is where an
 * absence is *shown*, never where anything was read from, so listing it here would
 * turn a placement decision into a source citation — the one claim the trace must
 * not manufacture. Blocks the retained document does not contain are excluded for
 * the same reason: the viewer reports those separately as unavailable rather than
 * offering a passage that cannot be opened.
 */
export function documentTracePassages<TKind extends string, TRef>(
  trace: DocumentTrace<TKind, TRef>,
  annotationId: string,
): DocumentTracePassage[] {
  const passages: DocumentTracePassage[] = [];
  for (const document of trace.documents) {
    for (const traceBlock of document.blocks) {
      const exact = traceBlock.segments.some((segment) =>
        segment.annotationIds.includes(annotationId)
      );
      const marked = traceBlock.markers.some(
        (marker) => marker.annotation.id === annotationId,
      );
      if (!exact && !marked) continue;
      passages.push({
        blockId: traceBlock.block.id,
        documentId: document.docId,
        sectionLabel:
          traceBlock.block.section_label
          ?? traceBlock.block.heading_stack.at(-1)
          ?? "",
        preview: passagePreview(traceBlock.block.content),
        connection: exact ? "exact" : "block",
      });
    }
  }
  return passages;
}

/**
 * A document id as a reader should see it.
 *
 * Here rather than in the viewer because the passage list names documents too, and
 * one document reading `product_profile` in a list and `product profile` in the
 * switcher above it is the same drift twice on one screen.
 */
export function displayDocumentName(docId: string): string {
  return docId.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim() || "Source document";
}

/**
 * Locate one block: its document, and every annotation marking it in this trace.
 */
export function documentTraceBlockLocation<
  TKind extends string,
  TRef,
>(
  trace: DocumentTrace<TKind, TRef>,
  blockId: string,
): DocumentTraceBlockLocation | null {
  for (const document of trace.documents) {
    const traceBlock = document.blocks.find((item) => item.block.id === blockId);
    if (!traceBlock) continue;
    return {
      documentId: document.docId,
      // Both kinds of mark, deduplicated: an exact span and a whole-block marker are
      // equally a reason the reader was sent here.
      annotationIds: [
        ...new Set([
          ...traceBlock.segments.flatMap((segment) => segment.annotationIds),
          ...traceBlock.markers.map((marker) => marker.annotation.id),
        ]),
      ],
    };
  }
  return null;
}

export type DocumentTraceMarkerGroup = {
  reason: "block_only" | "quote_unmatched";
  annotationIds: string[];
  unmatchedQuotes: string[];
};

export function groupDocumentTraceMarkers<
  TKind extends string,
  TRef,
>(
  markers: DocumentTraceBlock<TKind, TRef>["markers"],
): DocumentTraceMarkerGroup[] {
  const groups = new Map<DocumentTraceMarkerGroup["reason"], DocumentTraceMarkerGroup>();
  for (const marker of markers) {
    const group = groups.get(marker.reason) ?? {
      reason: marker.reason,
      annotationIds: [],
      unmatchedQuotes: [],
    };
    if (!group.annotationIds.includes(marker.annotation.id)) {
      group.annotationIds.push(marker.annotation.id);
    }
    for (const quote of marker.unmatchedQuotes) {
      if (!group.unmatchedQuotes.includes(quote)) group.unmatchedQuotes.push(quote);
    }
    groups.set(marker.reason, group);
  }
  return [...groups.values()];
}

type NormalizedText = {
  value: string;
  starts: number[];
  ends: number[];
};

type AnnotationRange = {
  start: number;
  end: number;
  annotationId: string;
};

/**
 * Named entities this matcher decodes, so a span the server accepted still
 * highlights here.
 *
 * The server normalizes with Python's `html.unescape`, which covers the whole
 * HTML5 table (~2,000 names). Shipping that table to the browser is not worth
 * its weight, so this is the deliberate subset: the structural entities plus the
 * typographic, mathematical, and Greek characters that appear in clinical source
 * text. A name outside this set stays literal and can still fail to match — add
 * it here rather than reimplementing the table.
 */
const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  apos: "'",
  gt: ">",
  lt: "<",
  nbsp: " ",
  quot: '"',
  // Typographic
  ndash: "–",
  mdash: "—",
  lsquo: "‘",
  rsquo: "’",
  ldquo: "“",
  rdquo: "”",
  hellip: "…",
  bull: "•",
  middot: "·",
  prime: "′",
  Prime: "″",
  ensp: " ",
  emsp: " ",
  thinsp: " ",
  shy: "­",
  reg: "®",
  trade: "™",
  copy: "©",
  // Mathematical and unit-bearing
  deg: "°",
  plusmn: "±",
  times: "×",
  divide: "÷",
  minus: "−",
  micro: "µ",
  le: "≤",
  ge: "≥",
  ne: "≠",
  asymp: "≈",
  permil: "‰",
  frac12: "½",
  frac14: "¼",
  frac34: "¾",
  sup2: "²",
  sup3: "³",
  // Greek used in clinical measures
  alpha: "α",
  beta: "β",
  gamma: "γ",
  mu: "μ",
};

function decodeEntity(raw: string): string | null {
  const body = raw.slice(1, -1);
  let point: number | null = null;
  if (body.startsWith("#x") || body.startsWith("#X")) {
    point = Number.parseInt(body.slice(2), 16);
  } else if (body.startsWith("#")) {
    point = Number.parseInt(body.slice(1), 10);
  }
  if (point !== null) {
    const isScalar = Number.isInteger(point)
      && point >= 0
      && point <= 0x10ffff
      && !(point >= 0xd800 && point <= 0xdfff);
    return isScalar ? String.fromCodePoint(point) : null;
  }
  return NAMED_ENTITIES[body] ?? null;
}

function normalizeWithOffsets(text: string): NormalizedText {
  const characters: string[] = [];
  const starts: number[] = [];
  const ends: number[] = [];
  let index = 0;

  while (index < text.length) {
    const sourceStart = index;
    let source: string;
    let sourceEnd: number;
    if (text[index] === "&") {
      const entity = text.slice(index).match(/^&(?:#\d+|#x[\da-f]+|[a-z]+);/i)?.[0];
      const decoded = entity ? decodeEntity(entity) : null;
      if (entity && decoded !== null) {
        source = decoded;
        sourceEnd = index + entity.length;
      } else {
        source = "&";
        sourceEnd = index + 1;
      }
    } else {
      const point = text.codePointAt(index);
      source = point === undefined ? text[index] : String.fromCodePoint(point);
      sourceEnd = index + source.length;
    }

    const normalized = /\s/u.test(source) ? " " : source.toLowerCase();
    for (let unitIndex = 0; unitIndex < normalized.length; unitIndex += 1) {
      const unit = normalized[unitIndex];
      if (unit === " " && characters.at(-1) === " ") {
        ends[ends.length - 1] = sourceEnd;
        continue;
      }
      characters.push(unit);
      starts.push(sourceStart);
      ends.push(sourceEnd);
    }
    index = sourceEnd;
  }

  while (characters[0] === " ") {
    characters.shift();
    starts.shift();
    ends.shift();
  }
  while (characters.at(-1) === " ") {
    characters.pop();
    starts.pop();
    ends.pop();
  }

  return { value: characters.join(""), starts, ends };
}

function findQuoteRanges(text: string, quote: string): Array<{ start: number; end: number }> {
  const source = normalizeWithOffsets(text);
  const needle = normalizeWithOffsets(quote).value;
  if (!source.value || !needle) return [];

  const ranges: Array<{ start: number; end: number }> = [];
  let fromIndex = 0;
  while (fromIndex <= source.value.length - needle.length) {
    const matchIndex = source.value.indexOf(needle, fromIndex);
    if (matchIndex < 0) break;
    ranges.push({
      start: source.starts[matchIndex],
      end: source.ends[matchIndex + needle.length - 1],
    });
    fromIndex = matchIndex + needle.length;
  }
  return ranges;
}

function traceSegments(text: string, ranges: AnnotationRange[]): DocumentTraceSegment[] {
  if (!ranges.length) return [{ text, annotationIds: [], start: 0, end: text.length }];
  const boundaries = new Set<number>([0, text.length]);
  for (const range of ranges) {
    boundaries.add(range.start);
    boundaries.add(range.end);
  }
  const points = [...boundaries].sort((left, right) => left - right);
  const segments: DocumentTraceSegment[] = [];
  for (let index = 0; index < points.length - 1; index += 1) {
    const start = points[index];
    const end = points[index + 1];
    if (start === end) continue;
    const annotationIds = ranges
      .filter((range) => range.start < end && range.end > start)
      .map((range) => range.annotationId)
      .filter((id, idIndex, ids) => ids.indexOf(id) === idIndex);
    segments.push({ text: text.slice(start, end), annotationIds, start, end });
  }
  return segments;
}

export function documentTraceSegmentsInRange(
  segments: DocumentTraceSegment[],
  start: number,
  end: number,
): DocumentTraceSegment[] {
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end < start) {
    return [];
  }
  return segments.flatMap((segment) => {
    const clippedStart = Math.max(start, segment.start);
    const clippedEnd = Math.min(end, segment.end);
    if (clippedStart >= clippedEnd) return [];
    return [{
      text: segment.text.slice(clippedStart - segment.start, clippedEnd - segment.start),
      annotationIds: [...segment.annotationIds],
      start: clippedStart,
      end: clippedEnd,
    }];
  });
}

export function filterDocumentAnnotations<
  TKind extends string,
  TRef,
>(
  annotations: Array<DocumentAnnotation<TKind, TRef>>,
  kind: TKind | "all",
): Array<DocumentAnnotation<TKind, TRef>> {
  return kind === "all"
    ? [...annotations]
    : annotations.filter((annotation) => annotation.kind === kind);
}

export function buildDocumentTrace<
  TKind extends string,
  TRef,
>(
  blocks: ContentBlock[],
  annotations: Array<DocumentAnnotation<TKind, TRef>>,
): DocumentTrace<TKind, TRef> {
  const sortedBlocks = [...blocks].sort(
    (left, right) =>
      left.doc_id.localeCompare(right.doc_id) ||
      left.ordinal - right.ordinal ||
      left.id.localeCompare(right.id),
  );
  const blocksById = new Map(sortedBlocks.map((block) => [block.id, block]));
  const rangesByBlock = new Map<string, AnnotationRange[]>();
  const matchedSpanBlocks = new Set<string>();

  for (const annotation of annotations) {
    for (const [spanIndex, span] of annotation.spans.entries()) {
      const quote = span.quote.trim();
      if (!quote) continue;
      for (const blockId of span.blockIds) {
        const block = blocksById.get(blockId);
        if (!block) continue;
        const ranges = findQuoteRanges(block.content, quote);
        if (ranges.length) {
          matchedSpanBlocks.add(`${annotation.id}\u241f${spanIndex}\u241f${blockId}`);
        }
        for (const range of ranges) {
          const blockRanges = rangesByBlock.get(blockId) ?? [];
          blockRanges.push({ ...range, annotationId: annotation.id });
          rangesByBlock.set(blockId, blockRanges);
        }
      }
    }
  }

  const markersByBlock = new Map<string, DocumentTraceBlock<TKind, TRef>["markers"]>();
  const anchoredByBlock = new Map<string, Array<DocumentAnnotation<TKind, TRef>>>();
  const unresolvedAnnotationIds: string[] = [];
  const unresolvedBlockIdsByAnnotation: Record<string, string[]> = {};
  const unplacedAnnotationIds: string[] = [];
  for (const annotation of annotations) {
    const referencedBlockIds = [...new Set([
      ...annotation.blockIds,
      ...annotation.spans.flatMap((span) => span.blockIds),
    ])];

    // An annotation with no lineage is a claim about absent content. Without
    // this branch it would survive in `annotations` while being reachable from
    // no segment, marker, or group — present in the data and invisible in the UI.
    if (referencedBlockIds.length === 0) {
      const anchorId = annotation.displayAnchorBlockId;
      if (anchorId && blocksById.has(anchorId)) {
        const anchored = anchoredByBlock.get(anchorId) ?? [];
        anchored.push(annotation);
        anchoredByBlock.set(anchorId, anchored);
      } else {
        unplacedAnnotationIds.push(annotation.id);
      }
      continue;
    }

    const unknownBlockIds = referencedBlockIds.filter((blockId) => !blocksById.has(blockId));
    if (unknownBlockIds.length) {
      unresolvedAnnotationIds.push(annotation.id);
      unresolvedBlockIdsByAnnotation[annotation.id] = unknownBlockIds;
    }
    for (const blockId of referencedBlockIds.filter((id) => blocksById.has(id))) {
      const declaredSpans = annotation.spans
        .map((span, spanIndex) => ({ span, spanIndex }))
        .filter(({ span }) => span.blockIds.includes(blockId));
      const unmatchedQuotes = declaredSpans
        .filter(({ spanIndex }) => !matchedSpanBlocks.has(`${annotation.id}\u241f${spanIndex}\u241f${blockId}`))
        .map(({ span }) => span.quote.trim())
        .filter(Boolean);
      if (declaredSpans.length > 0 && unmatchedQuotes.length === 0) continue;
      const markers = markersByBlock.get(blockId) ?? [];
      markers.push({
        annotation,
        reason: declaredSpans.length > 0 ? "quote_unmatched" : "block_only",
        unmatchedQuotes,
      });
      markersByBlock.set(blockId, markers);
    }
  }

  // Which annotations claim each block, in declaration order, so emphasis
  // precedence and badge selection are deterministic.
  const claimsByBlock = new Map<string, Array<DocumentAnnotation<TKind, TRef>>>();
  for (const annotation of annotations) {
    const claimed = new Set([
      ...annotation.blockIds,
      ...annotation.spans.flatMap((span) => span.blockIds),
    ]);
    for (const blockId of claimed) {
      if (!blocksById.has(blockId)) continue;
      const claims = claimsByBlock.get(blockId) ?? [];
      claims.push(annotation);
      claimsByBlock.set(blockId, claims);
    }
  }

  const documentsById = new Map<string, Array<DocumentTraceBlock<TKind, TRef>>>();
  for (const block of sortedBlocks) {
    const documentBlocks = documentsById.get(block.doc_id) ?? [];
    documentBlocks.push({
      block,
      segments: traceSegments(block.content, rangesByBlock.get(block.id) ?? []),
      markers: markersByBlock.get(block.id) ?? [],
      anchored: anchoredByBlock.get(block.id) ?? [],
      emphasis: strongestEmphasis(claimsByBlock.get(block.id) ?? []),
    });
    documentsById.set(block.doc_id, documentBlocks);
  }

  return {
    documents: [...documentsById].map(([docId, documentBlocks]) => ({
      docId,
      blocks: documentBlocks,
    })),
    annotations: [...annotations],
    unresolvedAnnotationIds,
    unresolvedBlockIdsByAnnotation,
    unplacedAnnotationIds,
  };
}

/**
 * Which tone wins when several annotations claim one block.
 *
 * Ordered by how much a reader needs to know, not by how good the news is: a passage that
 * answers one question and contradicts another must show the contradiction. `success`
 * outranks `neutral` because "this was found" is a claim and "nothing was found" is the
 * absence of one, so the claim is the more informative of the two.
 */
const TONE_WEIGHT: Record<Tone, number> = {
  neutral: 1,
  info: 1,
  success: 2,
  warning: 3,
  danger: 4,
};

/**
 * Resolve one emphasis for a block that several annotations claim.
 *
 * `danger > caution > success > neutral`, with the badge taken from the strongest claim
 * and ties broken by declaration order. This is precedence, not domain knowledge: the
 * shared layer never learns what produced a tone.
 */
export function strongestEmphasis<TKind extends string, TRef>(
  annotations: Array<DocumentAnnotation<TKind, TRef>>,
): DocumentAnnotationEmphasis | null {
  let strongest: DocumentAnnotationEmphasis | null = null;
  for (const annotation of annotations) {
    const emphasis = annotation.emphasis;
    if (!emphasis) continue;
    if (!strongest || TONE_WEIGHT[emphasis.tone] > TONE_WEIGHT[strongest.tone]) {
      strongest = emphasis;
    }
  }
  return strongest;
}
