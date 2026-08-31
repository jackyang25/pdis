/**
 * The four containers a result is built from, and which one a thing is.
 *
 * Four tools drew boxes, rows and dots by whatever looked right where they were added,
 * and the outcome was legible only to whoever wrote each screen: Screener put bordered
 * cards inside a bordered card, Inspector had already fixed the same nesting in its own
 * sections and written down why, and one of the two "cards" was not a card at all but a
 * `section` with a hand-rolled border, chevron and open state beside the component that
 * does exactly that.
 *
 * Depth is the rule, and the only rule. What a thing *is* decides how it is drawn, and
 * every tool's content sorts into the same four levels:
 *
 *   1. CARD      `CollapsibleCard` — the outermost container inside a tab. A rubric
 *                section, one comparison, one question state. Draws a border, because
 *                this is where a reader's eye needs a boundary: it separates one whole
 *                subject from the next.
 *
 *   2. GROUP     `DisclosureRow` — a labelled subset inside a card. A verdict, a
 *                relation, a discipline. A chevron, an optional tone dot, a label and a
 *                count, and *no border*: the card already drew the boundary, and a
 *                rounded border inside a rounded border reads as a third subject rather
 *                than a part of the second.
 *
 *   3. ROW       `EXPANDABLE_ROW` — one result that opens. A field, a rubric unit, a
 *                safety record. Full-bleed, separated from its neighbours by a rule
 *                rather than a box.
 *
 *   4. LEAF      a `divide-y` list — one result that does not open. A finding, a
 *                question, an assessment.
 *
 * A level may be skipped where a tool has nothing at it. Inspector has no groups: its
 * units go straight into the section card. Scout has no cards: thirty-six fields in
 * thirty-six boxes would be a page of borders, so its rows are the top level, which is
 * the case `EXPANDABLE_ROW` was written for.
 *
 * What may not happen is a level drawn as a different one — a group drawn as a card, or
 * a card hand-rolled beside the component for it.
 */
export const RESULT_LAYERS = ["card", "group", "row", "leaf"] as const;

export type ResultLayer = (typeof RESULT_LAYERS)[number];

/**
 * Which component draws each level.
 *
 * Exported so a test can name them, and so a reader arriving at any one of the four finds
 * the other three.
 */
export const LAYER_COMPONENT: Record<ResultLayer, string> = {
  card: "CollapsibleCard",
  group: "DisclosureRow",
  row: "EXPANDABLE_ROW",
  leaf: "divide-y",
};
