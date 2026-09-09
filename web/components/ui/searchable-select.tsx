"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { filterSelectOptions, type SelectOption } from "@/lib/select-options";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";
import { SELECT_TRIGGER_CLASS } from "./select";

/** A closed-list picker: text filters choices, but only selecting commits a value. */
export function SearchableSelect({
  value, options, onChange, searchLabel, disabled, id,
  "aria-label": ariaLabel, "aria-labelledby": labelledBy, "aria-describedby": describedBy,
}: {
  value: string | undefined;
  options: SelectOption[];
  onChange: (value: string) => void;
  searchLabel: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
}) {
  const uid = useId();
  const inputId = `${uid}-search`;
  const listId = `${uid}-options`;
  const valueId = `${uid}-value`;
  const input = useRef<HTMLInputElement>(null);
  const activeOption = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const filtered = filterSelectOptions(options, query);
  const active = Math.min(activeIndex, filtered.length - 1);
  const selectedLabel = options.find((option) => option.value === value)?.label ?? "Select";

  function changeOpen(next: boolean) {
    setOpen(next);
    setQuery("");
    setActiveIndex(Math.max(0, options.findIndex((option) => option.value === value)));
  }

  function select(option: SelectOption) {
    onChange(option.value);
    changeOpen(false);
  }

  useEffect(() => {
    if (open) activeOption.current?.scrollIntoView({ block: "nearest" });
  }, [open, active, query]);

  useEffect(() => {
    if (disabled) {
      setOpen(false);
      setQuery("");
      setActiveIndex(0);
    }
  }, [disabled]);

  return (
    <Popover modal open={open && !disabled} onOpenChange={changeOpen}>
      <PopoverTrigger asChild>
        <button
          type="button" id={id} disabled={disabled}
          aria-label={ariaLabel ? `${ariaLabel}: ${selectedLabel}` : undefined}
          aria-labelledby={labelledBy ? `${labelledBy} ${valueId}` : undefined}
          aria-describedby={describedBy}
          className={cn(SELECT_TRIGGER_CLASS, "min-w-0 gap-2")}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              changeOpen(true);
            }
          }}
        >
          <span id={valueId} className="truncate" title={selectedLabel}>{selectedLabel}</span>
          <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        aria-label={searchLabel}
        className="flex w-[var(--radix-popover-trigger-width)] min-w-0 flex-col overflow-hidden rounded-md p-1"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          input.current?.focus();
          // The portal mounts after the parent effect; reveal the selected row
          // here as well as when keyboard navigation changes the active option.
          activeOption.current?.scrollIntoView({ block: "nearest" });
        }}
      >
        <div className="shrink-0 border-b border-border p-2">
          <label htmlFor={inputId} className="mb-1.5 block text-xs font-medium">{searchLabel}</label>
          <input
            ref={input} id={inputId} role="combobox" autoComplete="off" spellCheck={false}
            aria-autocomplete="list" aria-expanded={true} aria-controls={listId}
            aria-activedescendant={active >= 0 ? `${uid}-option-${active}` : undefined}
            value={query} placeholder="Type to filter"
            className="h-9 w-full rounded-sm border border-input bg-card px-2 text-base focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring sm:text-xs"
            onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return;
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const direction = event.key === "ArrowDown" ? 1 : -1;
                setActiveIndex(Math.max(0, Math.min(filtered.length - 1, active + direction)));
              } else if (event.key === "Enter") {
                event.preventDefault();
                if (filtered[active]) select(filtered[active]);
              }
              // Escape and focus restoration belong to the shared popover.
              // Home/End retain native text-editing behavior in this editable combobox.
            }}
          />
        </div>
        <div id={listId} role="listbox" aria-label={searchLabel} className="min-h-0 max-h-64 overflow-y-auto overscroll-contain p-1">
          {filtered.map((option, index) => (
            <div
              key={option.value} id={`${uid}-option-${index}`} role="option"
              aria-selected={option.value === value}
              ref={index === active ? activeOption : undefined}
              className={cn("relative cursor-default select-none rounded-sm py-2 pl-7 pr-2 text-xs font-medium", index === active && "bg-accent text-accent-foreground")}
              onPointerMove={() => setActiveIndex(index)}
              onPointerDown={(event) => event.preventDefault()}
              onClick={() => select(option)}
            >
              {option.value === value && <Check aria-hidden="true" className="absolute left-1 top-2 h-4 w-4" />}
              {option.label}
            </div>
          ))}
        </div>
        <p role="status" className={filtered.length ? "sr-only" : "p-3 text-xs text-muted-foreground"}>
          {filtered.length ? `${filtered.length} options` : "No matches. Try another search."}
        </p>
      </PopoverContent>
    </Popover>
  );
}
