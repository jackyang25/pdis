import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Who wrote the text on screen, encoded so a reader can tell without being told.
 *
 * A result mixes seven origins: words quoted from the uploaded document, words quoted from
 * a paper, a value a model read out of one of those, an opinion a model formed, a number
 * code computed, a sentence the backend authored, and a label the interface authored. Seven
 * paint treatments would be noise, so they collapse to four the reader can act on, because
 * the only question that matters is "if this is wrong, whose fault is it".
 *
 *   Quoted    exact words. Cannot be wrong; it is a copy. Ruled on the left, full contrast.
 *             Whose words is shown by the attribution above it, never by the styling.
 *   Reading   a model read or judged this. Muted prose behind a four-pointed star. Needs
 *             review, and is the thing to check first. The star marks a contribution
 *             rather than a sentence: a note *about* a marked sentence is `continued`,
 *             indented under it and unmarked, because it has the same author.
 *   Computed  arithmetic over admitted data. Full contrast and tabular. Wrong only if its
 *             inputs are.
 *   Interface the tool explaining itself. Muted prose, in a box when it is an aside and
 *             in the flow when it is the section's own content. Not a model's words.
 *
 * **Every distinction here is structural, not a new colour.** Reading and Interface are the
 * pair that needed it: both are muted prose, because both are subordinate to the words they
 * sit under, so no tone could tell them apart. A box tells Interface apart, and a mark
 * tells Reading apart.
 *
 * The mark reverses an earlier decision, and the reason is worth keeping. The argument
 * against it was that interface copy is banned from data rows, so muted prose inside a row
 * is a model's by position and needs no marker - which is true, and was exactly the
 * problem: it is a rule a reader has to have been told, and on screen a model's sentence
 * read as the tool's own prose. Position implies authorship; a mark states it. The cost is
 * real - a run carries over a thousand of these - which is why the mark is a glyph in
 * `currentColor` at the size of the text, not a badge, a pill, or a colour.
 *
 * Two tones, three sizes, one rule, one box, one mark, one numeral setting. No new colours,
 * and the four are not four shades of one thing.
 */

/**
 * Exact words from somewhere else.
 *
 * The rule is 2px and never any other width: a 1px variant existed in one of ten call
 * sites and read as a different kind of thing while meaning the same kind of thing.
 *
 * `attribution` renders immediately above and is the only thing that says whose words
 * these are. Document quotes usually inherit it from the section they sit in; a quote from
 * a paper must name the paper, because otherwise a reader cannot tell an outside claim from
 * their own document's.
 */
export function Quoted({
  children,
  attribution,
  /** `prominent` for a quote that is the subject of its section, `dense` inside a list. */
  size = "dense",
  className,
}: {
  children: ReactNode;
  attribution?: ReactNode;
  size?: "prominent" | "dense";
  /** Spacing only. Border, padding, tone and size belong to this component, because those
   *  are the things that drifted when eight call sites wrote them by hand. */
  className?: string;
}) {
  return (
    <>
      {attribution}
      <blockquote
        className={cn(
          "border-l-2 border-border pl-3 leading-relaxed text-foreground",
          size === "prominent" ? "mt-3 text-xs" : "mt-1 text-[11px]",
          className,
        )}
      >
        {children}
      </blockquote>
    </>
  );
}

/**
 * The cited words, marked where they sit in their passage.
 *
 * `--tone-marked` already means "a result cites this" and the full-page document trace
 * already highlights with it, so a grey `bg-secondary` in the popover and in Archivist was
 * two tools disagreeing with a third about what a citation looks like.
 *
 * `box-decoration-clone` is what keeps the rounding and padding on every line of a highlight
 * that wraps, instead of only on the first and last.
 */
export function CitedMark({ children }: { children: ReactNode }) {
  return (
    <mark className="inline box-decoration-clone rounded-[3px] bg-[hsl(var(--tone-marked))]/25 px-0.5 text-inherit">
      {children}
    </mark>
  );
}

/**
 * What a model read or concluded.
 *
 * Muted, with no rule and no badge. Inside a data row this is unambiguous by the structural
 * law above: interface copy is not permitted there, so muted prose in a row is a model's.
 */
/**
 * The mark that says a model wrote what follows.
 *
 * A four-pointed star, and deliberately not the Priorities sparkle: that one marks a
 * *selection* a tool made, this one marks a *sentence* a model wrote. Same family so
 * they read as related, different glyph so they are not confused.
 *
 * `currentColor` and no new hue. The authorship system is two tones and no colours,
 * and a gradient here would make this the only element on the page arguing for its own
 * importance. What makes it findable is that it is a mark where prose has none.
 *
 * `aria-hidden`, and that is a decision rather than an oversight. A run carries over a
 * thousand model-authored sentences, so announcing each one would bury the content it
 * is meant to qualify. Screen-reader users get authorship from the attribution above a
 * block, which is where it is stated in words.
 */
function ReadingMark() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      // Sized in `em` so it tracks every `Reading` size without a second rule, and
      // aligned with `align-middle` rather than a hand-tuned nudge.
      //
      // The nudge was the bug. An inline-block's baseline is its bottom edge, so a
      // 0.95em box sat from baseline-0.95em to the baseline while lower-case prose
      // centres around baseline+0.35em - the mark rode about two pixels high, and a
      // translate pushed it higher still. Beside a tone dot on the same line the two
      // markers visibly disagreed about where the line was. `align-middle` puts the
      // glyph's midpoint on the text's own x-height centre, which is the thing every
      // other inline marker is aligned to.
      className="mr-1 inline-block h-[0.85em] w-[0.85em] shrink-0 align-middle fill-current"
    >
      <path d="M12 2c.9 5.1 4 8.2 9.1 9.1v1.8c-5.1.9-8.2 4-9.1 9.1h-1.8C9.3 16.9 6.2 13.8 1.1 12.9v-1.8C6.2 10.2 9.3 7.1 10.2 2Z" />
    </svg>
  );
}

export function Reading({
  children,
  /**
   * Render as a `span` rather than a paragraph.
   *
   * For the sentences that sit inside a link or a line of their own text, where a
   * block element is invalid and the mark would otherwise have to be placed by hand -
   * which is how a model's sentence ends up unmarked.
   */
  inline = false,
  /**
   * A second sentence in the same authored block, subordinate to the one above it.
   *
   * The mark belongs to a *contribution*, not to a sentence. An insight and the model's
   * note about that insight are one contribution - same author, one level apart - so the
   * first carries the mark and the second is indented under it.
   *
   * Marking both was the mistake. Two stars stacked read as a list of equals, and the
   * hierarchy that used to distinguish them was contrast: the insight at full, the note
   * muted. That looked right and said the wrong thing, because contrast is the authorship
   * axis and both lines have the same author. Indentation carries level; the mark carries
   * authorship; neither does the other's job.
   */
  continued = false,
  /**
   * `body` where the sentence is the content of a panel, `prominent` for the sentence a
   * section turns on, `dense` inside a list.
   *
   * `body` exists because the trace panels had no size to reach for and wrote their own -
   * `text-sm leading-6 text-foreground/85`, a third tone that is neither the muted prose
   * of a model's words nor the full contrast of the tool's. Four panels agreed on it,
   * which is what made it look deliberate.
   */
  size = "dense",
  className,
}: {
  children: ReactNode;
  inline?: boolean;
  continued?: boolean;
  size?: "body" | "prominent" | "dense";
  /** Spacing only. Tone and size belong to this component. */
  className?: string;
}) {
  const Tag = inline ? "span" : "p";
  return (
    <Tag
      className={cn(
        "leading-relaxed text-muted-foreground",
        size === "body" && "text-sm leading-6",
        size === "prominent" && !inline && "mt-1 text-xs",
        size === "prominent" && inline && "text-xs",
        size === "dense" && !inline && "mt-1 text-[11px]",
        size === "dense" && inline && "text-[11px]",
        // A hanging indent, so every line of a marked sentence starts at the same column
        // and the mark sits alone in the gutter. Without it the first line began after
        // the mark and every wrapped line fell back to the left of it, so a two-line
        // sentence had its own two left edges - and the `continued` note below, indented
        // to clear the mark, lined up with neither.
        !continued && !inline && "pl-[1.5em] -indent-[1.5em]",
        // The note aligns with the text above it rather than with the mark, so it reads
        // as hanging off that sentence rather than as the next item in a list.
        continued && "pl-[1.5em]",
        className,
      )}
    >
      {/* Marked, which reverses an earlier decision. The argument against was that
          interface copy is banned from data rows, so muted prose in a row is a model's
          by position - which is true, and turned out to be the problem: it is a rule a
          reader has to have been told. On screen the sentence looked like the tool's own
          prose. A mark states it instead of implying it. */}
      {!continued && <ReadingMark />}
      {children}
    </Tag>
  );
}

/**
 * A number, or a fact derived from numbers.
 *
 * Full contrast because it is not in doubt, and tabular so a column of them lines up. Kept
 * distinct from `Reading` on the tone axis alone: a reader scanning for "what did it
 * measure" should not have to read prose to find the figure.
 */
export function Computed({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("tabular-nums text-foreground", className)}>{children}</span>
  );
}

/**
 * The tool explaining itself, at section level.
 *
 * **Boxed, and that is the whole distinction.** `Reading` and this were both muted prose at
 * the same size, so where they sat next to each other, a model's judgment about a program and
 * the tool's caveat about that program were indistinguishable. Tone could not separate them,
 * because both are subordinate to the quoted words above them and neither should be full
 * contrast. So the separation is structural, as everywhere else here: prose that flows in the
 * column is a model's, prose in a box is the tool's. A reader learns it from one instance.
 *
 * It stays deliberately awkward inline. It renders as a block with its own margin, so the
 * natural place for it is above or below a section rather than beside a value.
 */
export function InterfaceNote({
  children,
  /**
   * Whether this is an aside or the content itself.
   *
   * `note` is the default and is set off in a box: a caveat beside data, a warning above
   * it, a summary under it. The box says "read this differently from what surrounds it",
   * which is the whole reason it is there.
   *
   * `content` is the same voice with nothing to be set off *from*, because it is what the
   * section contains. A field whose measurable targets are none answers with a sentence
   * saying why - that sentence is the section's content, not a footnote on it, and boxing
   * it made an absence the heaviest element on a card where every real finding is flat
   * prose. Weight tracks significance, and that had it backwards.
   */
  variant = "note",
  className,
}: {
  children: ReactNode;
  variant?: "note" | "content";
  /** Spacing only. Border, padding, tone and size belong to this component. */
  className?: string;
}) {
  return (
    <div
      className={cn(
        "text-[11px] leading-relaxed text-muted-foreground",
        variant === "note" && "rounded-md border border-border/60 bg-card px-3 py-2",
        className,
      )}
    >
      {children}
    </div>
  );
}

/**
 * The exact string a run sent to a machine: a search query, a record id, a place code.
 *
 * Not a fifth authorship mode, and deliberately not prose. Nobody wrote a query as a
 * sentence, so asking whose opinion it is has no answer; what a reader needs is to see it
 * character for character, which is what the monospace says. The app already used monospace
 * for exactly this, on record ids and place codes, so this names the convention rather than
 * adding one. It always renders under a label that says what the string is.
 */
export function Literal({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("break-words font-mono text-[11px] text-muted-foreground", className)}>
      {children}
    </span>
  );
}

/**
 * One cited thing, in the shape every list of them uses.
 *
 * The comparator cohort, the excluded panel, the sources panel and an insight were four
 * different arrangements of the same four parts, which is most of why the page read as
 * undifferentiated text. One shape:
 *
 *     title (linked)                              value or date, computed
 *     | the exact words
 *     what a model made of them
 *
 * Nothing else. The internal provenance that used to sit here ("typed calculation inputs
 * and evidence-unit deduplication were retained") is interface copy about the pipeline and
 * belongs nowhere near a citation.
 */
export function SourceEntry({
  title,
  href,
  meta,
  quote,
  reading,
  children,
}: {
  title: ReactNode;
  href?: string;
  /** Computed detail: a value, a unit, a date. */
  meta?: ReactNode;
  quote?: string;
  /** What a model read or concluded from the quote. */
  reading?: ReactNode;
  /** Anything this list needs that the shape does not cover, e.g. a nested disclosure. */
  children?: ReactNode;
}) {
  return (
    <li className="list-none border-t border-border/60 py-2 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="min-w-0 text-[11px] font-medium text-foreground hover:underline"
          >
            {title}
          </a>
        ) : (
          <span className="min-w-0 text-[11px] font-medium text-foreground">{title}</span>
        )}
        {meta && (
          <Computed className="shrink-0 text-[11px] text-muted-foreground">{meta}</Computed>
        )}
      </div>
      {quote && <Quoted>{quote}</Quoted>}
      {reading && <Reading>{reading}</Reading>}
      {children}
    </li>
  );
}
