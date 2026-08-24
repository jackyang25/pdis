import type { SourceRole, TargetRelationship } from "./api.ts";

export type ProjectionRelationshipFilter = TargetRelationship | "all";

const RELATIONSHIP_LABELS: Record<TargetRelationship, string> = {
  direct: "Direct to uploaded product",
  analogous: "Analogous product",
  adjacent: "Adjacent context",
  unrelated: "Unrelated",
  // "Relationship unknown" left the word unqualified while Scout's fourth result axis is a
  // relation too, so two different questions shared one name. Its siblings already say
  // "product", so this only finishes the sentence they started.
  unknown: "Product relation unknown",
};

const SOURCE_ROLE_LABELS: Record<SourceRole, string> = {
  experimental: "Experimental arm",
  comparator: "Comparator arm",
  control: "Control arm",
  co_intervention: "Co-intervention",
  unknown: "Study role unknown",
};

export function relationshipLabel(relationship: TargetRelationship): string {
  return RELATIONSHIP_LABELS[relationship];
}

export function sourceRoleLabel(role: SourceRole): string {
  return SOURCE_ROLE_LABELS[role];
}

export function isContextualRelationship(relationship: TargetRelationship): boolean {
  return relationship === "analogous" || relationship === "adjacent";
}

/**
 * Reading order for a projection's relationship to the uploaded product.
 *
 * Measured on a real run: of 502 development records, 13 were `direct`, 37 `analogous`,
 * 281 `adjacent` and 171 `unrelated`. Emitted in retrieval order, the 13 that describe the
 * product in front of the reader sat anywhere in a flat list of 502. So the list is
 * grouped, in this order, and every group starts closed behind its count.
 */
export const RELATIONSHIP_READING_ORDER: TargetRelationship[] = [
  "direct",
  "analogous",
  "adjacent",
  "unrelated",
  "unknown",
];

export type ProjectionGroup<T> = {
  relationship: TargetRelationship;
  items: T[];
};

/**
 * Projections grouped by relationship, in reading order, empty groups dropped.
 *
 * Grouping rather than sorting: a count per group is what tells a reader that 13 of 502
 * records are about their product, and a sorted flat list cannot say that.
 */
export function groupProjectionsByRelationship<
  T extends { target_relationship: TargetRelationship },
>(items: readonly T[]): ProjectionGroup<T>[] {
  return RELATIONSHIP_READING_ORDER.map((relationship) => ({
    relationship,
    items: items.filter((item) => item.target_relationship === relationship),
  })).filter((group) => group.items.length > 0);
}

export function filterProjectionsByRelationship<
  T extends { target_relationship: TargetRelationship },
>(items: readonly T[], relationship: ProjectionRelationshipFilter): T[] {
  if (relationship === "all") return [...items];
  return items.filter((item) => item.target_relationship === relationship);
}
