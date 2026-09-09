"use client";

import { createContext, useContext, useId } from "react";
import { cn } from "@/lib/utils";
import { Label } from "./label";
import { SearchableSelect } from "./searchable-select";
import { Check, Info } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

/**
 * Field presentation, independent of a tool's data or configuration authority.
 * Domain selectors compose these primitives; pages own their field order.
 */
export function ConfigurationShell({ children }: { children: React.ReactNode }) {
  const titleId = useId();
  return (
    <div aria-labelledby={titleId}>
      <h2 id={titleId} className="sr-only">Configuration</h2>
      <ConfigFieldGrid>{children}</ConfigFieldGrid>
    </div>
  );
}

/** Reader-facing sections share the field grid, never introduce a nested layout. */
export function ConfigSectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="col-span-full mt-4 flex min-h-6 items-center text-sm font-semibold text-foreground first:mt-0">
      {children}
    </h3>
  );
}

/** Selection appearance only; the caller owns single/multiple selection rules. */
export function ConfigChip({ selected, children, className, ...props }: React.ComponentPropsWithoutRef<"button"> & { selected: boolean }) {
  return (
    <button
      {...props}
      type="button"
      aria-pressed={selected}
      className={cn(
        "inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none",
        selected ? "border-foreground/25 bg-secondary text-secondary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      {selected && <Check aria-hidden="true" className="h-3 w-3 shrink-0" />}
      {children}
    </button>
  );
}

/** Supplementary guidance uses the existing keyboard/touch-accessible popover. */
export function ConfigFieldHelp({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`About ${label}`}
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Info aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent aria-label={`About ${label}`} className="max-w-[calc(100vw-1.5rem)] text-xs leading-relaxed">
        {children}
      </PopoverContent>
    </Popover>
  );
}

/**
 * Stacks fields in the rail, pairing them into two columns only at the narrow
 * width where the rail sits above the upload area instead of beside it.
 *
 * Every field in the rail belongs in here. Pairing on `sm:` alone looks right until
 * `lg:`, where the rail becomes a 17rem column beside the uploads: two fields then
 * share about 124px each, and a field's help text wraps into a ribbon two or three
 * words wide. Which is why the `lg:flex` is the point of this component and not a
 * detail — a hand-rolled `sm:grid-cols-2` has no way to know it is in a rail.
 */
export function ConfigFieldGrid({
  children,
  className,
  layout = "rail",
  ...props
}: React.ComponentPropsWithoutRef<"div"> & { layout?: "rail" | "wide" }) {
  return (
    <div
      // Merged, not replaced: a caller passing spacing would otherwise drop the
      // layout this component exists to impose.
      className={cn(
        "grid gap-4 sm:grid-cols-2",
        layout === "rail" ? "lg:flex lg:flex-col" : "lg:grid-cols-3",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

const FieldContext = createContext<{
  controlId: string;
  labelId: string;
  noteId?: string;
} | null>(null);

/** Essential instructions and limitations stay visible below their control. */
export function ConfigHelp({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{children}</p>
  );
}

/** One control per field. Compound controls name each input explicitly. */
export function ConfigField({
  label,
  disabled,
  action,
  note,
  help,
  children,
  id,
}: {
  label: string;
  /** Dims the field while an earlier choice it depends on is unmade. */
  disabled?: boolean;
  /**
   * A control that acts on this field — removing its row, for instance.
   *
   * Rendered on the control's own line, which is the point of it existing here. A
   * caller placing the button beside the whole field instead had it align to the
   * bottom of the tallest thing in the row, so on a field carrying help text the
   * button floated down beside the prose it has nothing to do with.
   */
  action?: React.ReactNode;
  /**
   * Help text beneath the control.
   *
   * Its own slot rather than part of `children`, so `action` can sit on the control's
   * line without the note lengthening the row it aligns to.
   */
  note?: React.ReactNode;
  /** Supplementary explanation, kept out of the main reading flow. */
  help?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
}) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const labelId = `${controlId}-label`;
  const noteId = note ? `${controlId}-note` : undefined;
  return (
    <FieldContext.Provider value={{ controlId, labelId, noteId }}>
      <div className={disabled ? "min-w-0 opacity-50" : "min-w-0"}>
        <div className="mb-1.5 flex min-h-6 items-center gap-1">
          <Label id={labelId} htmlFor={controlId}>{label}</Label>
          {help && <ConfigFieldHelp label={label}>{help}</ConfigFieldHelp>}
        </div>
        {action ? (
          <div className="flex items-center gap-1.5">
            <div className="min-w-0 flex-1">{children}</div>
            <div className="shrink-0">{action}</div>
          </div>
        ) : (
          children
        )}
        {note && <div id={noteId}>{note}</div>}
      </div>
    </FieldContext.Provider>
  );
}

const INPUT_CLASS = "flex h-9 w-full min-w-0 items-center rounded-md border border-input bg-card px-3 py-2 text-xs font-medium text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50";

/** Shared text/date input styling; value interpretation belongs to the caller. */
export function ConfigTextInput({
  className,
  type = "text",
  id,
  "aria-labelledby": labelledBy,
  "aria-describedby": describedBy,
  ...props
}: React.ComponentPropsWithoutRef<"input">) {
  const field = useContext(FieldContext);
  return (
    <input
      {...props}
      type={type}
      id={id ?? field?.controlId}
      aria-labelledby={labelledBy ?? (props["aria-label"] ? undefined : field?.labelId)}
      aria-describedby={[field?.noteId, describedBy].filter(Boolean).join(" ") || undefined}
      className={cn(INPUT_CLASS, className)}
    />
  );
}

/**
 * A date bound in the rail, boxed exactly like `ConfigSelect`'s trigger.
 *
 * Here rather than in the one tool that needs a date, because the box is the
 * shared thing: a hand-rolled input beside a select is where the two drift by a
 * pixel of height, and the second tool to want a date copies whatever the first
 * one wrote.
 */
export function ConfigDateInput({
  value,
  onChange,
  max,
  disabled,
  ...props
}: {
  value: string;
  onChange: (value: string) => void;
  /** ISO bound, e.g. today, so a window cannot be set into the future. */
  max?: string;
  disabled?: boolean;
} & Omit<React.ComponentPropsWithoutRef<"input">, "value" | "onChange" | "type">) {
  return (
    <ConfigTextInput
      {...props}
      type="date"
      value={value}
      max={max}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export function ConfigSelect({
  value,
  options,
  disabled,
  onChange,
  searchLabel,
  id,
  "aria-label": ariaLabel,
  "aria-labelledby": labelledBy,
  "aria-describedby": describedBy,
}: {
  value: string | undefined;
  options: { value: string; label: string }[];
  disabled?: boolean;
  onChange: (value: string) => void;
  /** Opt long lists into local search; short selectors retain the standard menu. */
  searchLabel?: string;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
}) {
  const field = useContext(FieldContext);
  if (searchLabel) {
    return (
      <SearchableSelect
        value={value} options={options} onChange={onChange} searchLabel={searchLabel}
        disabled={disabled || options.length === 0}
        id={id ?? field?.controlId}
        aria-label={ariaLabel}
        aria-labelledby={labelledBy ?? (ariaLabel ? undefined : field?.labelId)}
        aria-describedby={[field?.noteId, describedBy].filter(Boolean).join(" ") || undefined}
      />
    );
  }
  return (
    <Select
      value={value}
      onValueChange={onChange}
      disabled={disabled || options.length === 0}
    >
      <SelectTrigger
        id={id ?? field?.controlId}
        aria-label={ariaLabel}
        aria-labelledby={labelledBy ?? (ariaLabel ? undefined : field?.labelId)}
        aria-describedby={[field?.noteId, describedBy].filter(Boolean).join(" ") || undefined}
      >
        <SelectValue placeholder="Select" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
