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
 *   Reading   a model read or judged this. Muted prose, flowing in the column. Needs review,
 *             and is the thing to check first.
 *   Computed  arithmetic over admitted data. Full contrast and tabular. Wrong only if its
 *             inputs are.
 *   Interface the tool explaining itself. Muted prose in a box. Not about this document.
 *
 * **Every distinction here is structural, not a new colour.** Reading and Interface are the
 * pair that needed it: both are muted prose, because both are subordinate to the words they
 * sit under, so no tone could tell them apart. A box does, and one instance teaches it. On
 * top of that, interface copy is not allowed inside a data row at all, which means muted
 * prose in a row is a model's, always, and needs no marker of its own. That is what keeps
 * this quiet rather than badge-ridden: a real run carries over 1,500 model-authored
 * sentences, and a per-sentence marker would be on every one of them.
 *
 * Two tones, three sizes, one rule, one box, one numeral setting. No new colours, and the
 * four are not four shades of one thing.
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
export function Reading({
  children,
  /** `prominent` for the sentence a section turns on, `dense` inside a list. */
  size = "dense",
  className,
}: {
  children: ReactNode;
  size?: "prominent" | "dense";
  /** Spacing only. Tone and size belong to this component. */
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mt-1 leading-relaxed text-muted-foreground",
        size === "prominent" ? "text-xs" : "text-[11px]",
        className,
      )}
    >
      {children}
    </p>
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
  className,
}: {
  children: ReactNode;
  /** Spacing only. Border, padding, tone and size belong to this component. */
  className?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-border/60 bg-card px-3 py-2 text-[11px] leading-relaxed text-muted-foreground",
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
