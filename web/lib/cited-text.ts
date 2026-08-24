/**
 * Where a cited quote sits inside the passage it came from.
 *
 * Replaces showing the quote twice: once in its own box, then again inside the surrounding
 * passage. Marking it in place puts the words in their context in one pass, instead of
 * asking a reader to compare two strings and work out that they are the same sentence.
 *
 * The whole difficulty is whitespace. On a real run 15 of 36 quotes matched their block only
 * after runs of spaces and newlines were collapsed, because the quote was captured from a
 * table row that the parse renders with different spacing. So a plain `includes` would fail
 * on nearly half of them and quietly drop the highlight. Matching happens on normalised text
 * and the result is mapped back to offsets in the original, so the passage still renders with
 * its own line breaks.
 *
 * `unplaced` is the safety net. A quote that cannot be located is returned rather than
 * dropped, so the caller can still show it: removing the separate box is only safe if
 * nothing can fall through the gap.
 */

export type PassageSegment = {
  text: string;
  /** True when this run of characters is part of a cited quote. */
  cited: boolean;
};

export type CitedPassage = {
  segments: PassageSegment[];
  /** Quotes that could not be found in the passage, verbatim or normalised. */
  unplaced: string[];
};

/** Collapse whitespace, and remember where each surviving character came from. */
function normalizeWithMap(value: string): { text: string; origin: number[] } {
  let text = "";
  const origin: number[] = [];
  let previousWasSpace = true; // leading whitespace is dropped, as in a trim
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (/\s/.test(character)) {
      if (previousWasSpace) continue;
      text += " ";
      origin.push(index);
      previousWasSpace = true;
      continue;
    }
    text += character;
    origin.push(index);
    previousWasSpace = false;
  }
  // A single trailing space would otherwise let a quote match one character too far.
  while (text.endsWith(" ")) {
    text = text.slice(0, -1);
    origin.pop();
  }
  return { text, origin };
}

export function markCitedText(content: string, quotes: string[]): CitedPassage {
  if (!content) return { segments: [], unplaced: quotes.filter(Boolean) };
  const wanted = Array.from(new Set(quotes.filter((quote) => quote.trim())));
  if (wanted.length === 0) {
    return { segments: [{ text: content, cited: false }], unplaced: [] };
  }

  const { text: normalized, origin } = normalizeWithMap(content);
  const ranges: { start: number; end: number }[] = [];
  const unplaced: string[] = [];

  for (const quote of wanted) {
    const target = normalizeWithMap(quote).text;
    if (!target) continue;
    // Search every occurrence, and take the first that does not overlap a range already
    // claimed by another quote. Two quotes can legitimately share a passage.
    let found = false;
    let from = 0;
    while (from <= normalized.length - target.length) {
      const at = normalized.indexOf(target, from);
      if (at < 0) break;
      const start = origin[at];
      const end = origin[at + target.length - 1] + 1;
      const overlaps = ranges.some((range) => start < range.end && end > range.start);
      if (!overlaps) {
        ranges.push({ start, end });
        found = true;
        break;
      }
      from = at + 1;
    }
    if (!found) unplaced.push(quote);
  }

  if (ranges.length === 0) {
    return { segments: [{ text: content, cited: false }], unplaced };
  }

  ranges.sort((left, right) => left.start - right.start);
  const segments: PassageSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start > cursor) {
      segments.push({ text: content.slice(cursor, range.start), cited: false });
    }
    segments.push({ text: content.slice(range.start, range.end), cited: true });
    cursor = range.end;
  }
  if (cursor < content.length) {
    segments.push({ text: content.slice(cursor), cited: false });
  }
  return { segments, unplaced };
}
