import type { SemanticSlot, QuantitativeTarget, QuantitativeSemanticProfile } from "./api";

export function semanticSlotLabel(slot: SemanticSlot | undefined): string {
  if (!slot) return "Not available";
  if (slot.state === "specified") return slot.value || "Specified";
  if (slot.state === "other") return slot.other || "Other";
  if (slot.state === "unknown") return "Unknown";
  return "Not specified";
}

export function dimensionLabel(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function comparisonDimensions(
  target: QuantitativeTarget,
): Array<keyof QuantitativeSemanticProfile> {
  return (
    Object.keys(target.comparison_contract) as Array<
      keyof QuantitativeSemanticProfile
    >
  ).filter(
    (dimension) =>
      target.comparison_contract[dimension].mode !== "unconstrained",
  );
}

export function comparisonRuleLabel(
  rule:
    | QuantitativeTarget["comparison_contract"][keyof QuantitativeSemanticProfile]
    | undefined,
): string {
  if (!rule) return "Comparison scope unavailable";
  if (rule.mode === "unconstrained") return "Does not control comparison";
  if (rule.mode === "unknown")
    return `Scope needs review${rule.reason ? `: ${rule.reason}` : ""}`;
  return `${rule.mode === "exact" ? "Exact" : "Compatible"} match: ${rule.scope}`;
}
