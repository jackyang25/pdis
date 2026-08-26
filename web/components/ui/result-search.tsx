import { Search } from "lucide-react";

/**
 * The search box that leads a toolbar.
 *
 * Three sites wrote this out and the class strings were character-for-character
 * identical: Scout's field list, Scout's development and safety records, Inspector's
 * sections. Identical is how it starts - the copies were made from each other - and
 * one of them getting a different focus ring or a different height is how it ends,
 * with nobody able to say which one was right.
 *
 * The label is the accessible name and the placeholder is the hint, and they are
 * separate arguments because they say different things: "Search fields" names the
 * control, "Find a field…" says what typing does. Passing one string for both put
 * "Find a field…" into the accessibility tree as the name of a control.
 *
 * `flex-1` with a cap, because a toolbar's remaining slots - a filter, a count - are
 * fixed width and this is what absorbs the difference.
 */
export function ResultSearch({
  label,
  placeholder,
  value,
  onChange,
}: {
  /** Names the control for a screen reader. Not shown. */
  label: string;
  /** Says what typing here does. Shown. */
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="relative min-w-0 flex-1 sm:max-w-xs">
      <span className="sr-only">{label}</span>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-8 w-full rounded-md border border-input bg-card pl-8 pr-3 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-foreground/30 focus:ring-2 focus:ring-ring/10 motion-reduce:transition-none"
      />
    </label>
  );
}
