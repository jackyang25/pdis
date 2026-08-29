/**
 * A heading and one line of explanation, above a list inside a result.
 *
 * Shared rather than repeated: this began as a local helper in Inspector's page,
 * and Screener is the second consumer. Lifting it here on the second, not the third,
 * is what keeps two near-identical headings from drifting a font weight apart.
 */
export function SectionHeading({
  title,
  description,
  trailing,
}: {
  /**
   * Text, or text with a count beside it.
   *
   * Widened from `string` so a count can be styled apart from the title without a
   * caller pre-formatting one into the other — `"Gaps · 7"` and `"Priorities 7"`
   * were two grammars for one thing, and a string forced that choice on the caller.
   */
  title: React.ReactNode;
  description: string;
  /** Right-aligned detail, e.g. a count. Omitted when there is nothing to say. */
  trailing?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
      </div>
      {trailing && (
        // `min-w-0` and wrapping rather than `shrink-0`: a trailing string long enough
        // to exceed the row was clipped mid-word at the container edge, because
        // refusing to shrink is refusing to wrap. A count that runs long should take a
        // second line, never disappear.
        <p className="min-w-0 text-xs leading-5 tabular-nums text-muted-foreground">
          {trailing}
        </p>
      )}
    </div>
  );
}
