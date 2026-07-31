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
 * Every tool panel renders its configuration in `RunPanel`'s left column. Most
 * select one `(org, source_type, intervention_class)` triple through
 * `HeaderPicker`; a tool whose configuration genuinely differs — Aligner needs a
 * source type per document — composes these primitives instead, so the rail
 * still looks and behaves the same either way.
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
 */
export function ConfigFieldGrid({
  children,
  ...props
}: React.ComponentPropsWithoutRef<"div">) {
  return (
    <div className="flex flex-col gap-4 sm:grid sm:grid-cols-2 lg:flex" {...props}>
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
