import type { SourceRole, TargetRelationship } from "./api.ts";

export type ProjectionRelationshipFilter = TargetRelationship | "all";

const RELATIONSHIP_LABELS: Record<TargetRelationship, string> = {
  direct: "Direct to uploaded product",
  analogous: "Analogous product",
  adjacent: "Adjacent context",
  unrelated: "Unrelated",
  unknown: "Relationship unknown",
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

export function filterProjectionsByRelationship<
  T extends { target_relationship: TargetRelationship },
>(items: readonly T[], relationship: ProjectionRelationshipFilter): T[] {
  if (relationship === "all") return [...items];
  return items.filter((item) => item.target_relationship === relationship);
}
