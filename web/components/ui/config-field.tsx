import { cn } from "@/lib/utils";
import { Label } from "./label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

/**
 * The vocabulary of a tool's configuration rail.
 *
 * Generic on purpose: these are the primitives everything above them is built
 * from. The shared, non-negotiable fields live in `configuration-fields.tsx`
 * — `ContextFields` and `SourceTypeField` — and a tool composes these directly
 * only for parameters of its own, so the rail looks the same either way.
 *
 * A tool needing an input shape that is not here adds it here rather than styling
 * one inline: the box is the shared thing, whatever the field means.
 */
export function ConfigurationShell({ children }: { children: React.ReactNode }) {
  return (
    <div aria-labelledby="configuration-title">
      <Label id="configuration-title" asChild>
        <h2 className="mb-5">Configuration</h2>
      </Label>
      {children}
    </div>
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
  ...props
}: React.ComponentPropsWithoutRef<"div">) {
  return (
    <div
      // Merged, not replaced: a caller passing spacing would otherwise drop the
      // layout this component exists to impose.
      className={cn("flex flex-col gap-4 sm:grid sm:grid-cols-2 lg:flex", className)}
      {...props}
    >
      {children}
    </div>
  );
}

export function ConfigField({
  label,
  disabled,
  children,
}: {
  label: string;
  /** Dims the field while an earlier choice it depends on is unmade. */
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={disabled ? "min-w-0 opacity-50" : "min-w-0"}>
      <div className="mb-1.5">
        <Label>{label}</Label>
      </div>
      {children}
    </div>
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
}: {
  value: string;
  onChange: (value: string) => void;
  /** ISO bound, e.g. today, so a window cannot be set into the future. */
  max?: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="date"
      value={value}
      max={max}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="flex h-9 w-full items-center rounded-md border border-input bg-card px-3 py-2 text-xs font-medium text-foreground focus:outline-none focus:ring-2 focus:ring-ring/20 disabled:cursor-not-allowed disabled:opacity-50"
    />
  );
}

export function ConfigSelect({
  value,
  options,
  disabled,
  onChange,
}: {
  value: string | undefined;
  options: { value: string; label: string }[];
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Select
      value={value}
      onValueChange={onChange}
      disabled={disabled || options.length === 0}
    >
      <SelectTrigger>
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
