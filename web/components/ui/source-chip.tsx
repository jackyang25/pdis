import type { ReactNode } from "react";
import { FileText, Globe } from "lucide-react";

import type { SourceFormat } from "@/lib/api";
import { EYEBROW } from "@/lib/typography";
import { cn } from "@/lib/utils";

/**
 * A citation: a pointer to the one source a claim rests on.
 *
 * One shape wherever the interface names a single source - an answer citing a passage or a
 * web page, a passage list naming which document each passage is in - so a reader learns
 * it once. It is not "In document", which opens a list of passages rather than naming one;
 * not a source record (title, date, attribution), which is `SourceEntry`; and not a
 * category or a verdict, which are `Badge` and `VerdictPill`. `source-chip.test.ts` keeps
 * it to the places that mean this; a passage's document and location go through
 * `PassageSource` below, so every list of passages names one the same way.
 *
 * Neutral by design. Red and green carry findings in this suite, so a red PDF mark beside a
 * red verdict would read as a second warning.
 *
 * The leading mark says what kind of source it is: the file type the parser recorded, a
 * globe for a web page, or a plain file glyph when a block predates the recorded format.
 * Never a format worked out from what else the block holds.
 *
 * Presentational: a caller wraps it in the button or link that opens the source, and the
 * chip answers that control's hover.
 */
export function SourceChip({
  format,
  children,
  className,
}: {
  format: SourceFormat | "web" | null | undefined;
  /** What the chip names: a label, or a document and where in it. */
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-md border border-border/70 bg-card px-1.5 py-px align-baseline text-[11px] font-medium leading-4 text-foreground",
        "transition-colors group-hover/source:border-foreground/25 motion-reduce:transition-none",
        className,
      )}
    >
      <SourceMark format={format} />
      <span className="min-w-0 truncate">{children}</span>
    </span>
  );
}

/**
 * Where a passage is: its document as a citation, then where in it.
 *
 * The one line every list or panel of passages names a passage with - the result's passage
 * popover, the trace's passage list, an Assistant citation. `document` is given only when
 * naming it tells the reader something: a result spanning several documents, or a citation
 * that may open over a page holding none of them. The location never gives way to a long
 * file name; the name truncates instead, because "Slide 34" is the part a reader acts on.
 */
export function PassageSource({
  format,
  document,
  location,
  className,
}: {
  format: SourceFormat | null | undefined;
  /** The document's display name, when it should be named. */
  document?: string;
  /** Where in it, from `documentBlockLocationLabel`. */
  location?: string;
  className?: string;
}) {
  if (!document && !location) return null;
  return (
    <span className={cn("flex min-w-0 items-center gap-1.5", className)}>
      {document && <SourceChip format={format} className="min-w-0">{document}</SourceChip>}
      {location && <span className={cn("shrink-0 whitespace-nowrap", EYEBROW)}>{location}</span>}
    </span>
  );
}

const FORMAT_TAG: Record<SourceFormat, string> = {
  docx: "DOCX",
  pptx: "PPTX",
  pdf: "PDF",
  image: "IMG",
};

function SourceMark({ format }: { format: SourceFormat | "web" | null | undefined }) {
  if (format === "web") {
    return <Globe aria-hidden="true" className="h-3 w-3 shrink-0 text-muted-foreground" />;
  }
  if (!format) {
    return <FileText aria-hidden="true" className="h-3 w-3 shrink-0 text-muted-foreground" />;
  }
  return (
    <span className="shrink-0 font-mono text-[9px] font-medium tracking-wide text-muted-foreground">
      {FORMAT_TAG[format]}
    </span>
  );
}
