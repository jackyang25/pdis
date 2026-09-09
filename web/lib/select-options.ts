export type SelectOption = { value: string; label: string };

/** Local presentation filtering only. Never normalize or replace the stored key. */
export function filterSelectOptions(options: readonly SelectOption[], query: string): SelectOption[] {
  const text = query.trim().toLowerCase();
  return options.filter((option) => option.label.toLowerCase().includes(text));
}
