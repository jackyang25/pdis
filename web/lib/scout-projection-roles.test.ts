import assert from "node:assert/strict";
import test from "node:test";

import {
  filterProjectionsByRelationship,
  isContextualRelationship,
  relationshipLabel,
  sourceRoleLabel,
} from "./scout-projection-roles.ts";

test("labels every closed projection relationship", () => {
  assert.equal(relationshipLabel("direct"), "Direct to uploaded product");
  assert.equal(relationshipLabel("analogous"), "Analogous product");
  assert.equal(relationshipLabel("adjacent"), "Adjacent context");
  assert.equal(relationshipLabel("unrelated"), "Unrelated");
  assert.equal(relationshipLabel("unknown"), "Relationship unknown");
});

test("labels every closed source-study role", () => {
  assert.equal(sourceRoleLabel("experimental"), "Experimental arm");
  assert.equal(sourceRoleLabel("comparator"), "Comparator arm");
  assert.equal(sourceRoleLabel("control"), "Control arm");
  assert.equal(sourceRoleLabel("co_intervention"), "Co-intervention");
  assert.equal(sourceRoleLabel("unknown"), "Study role unknown");
});

test("identifies contextual relationships without treating unknown as context", () => {
  assert.equal(isContextualRelationship("analogous"), true);
  assert.equal(isContextualRelationship("adjacent"), true);
  assert.equal(isContextualRelationship("direct"), false);
  assert.equal(isContextualRelationship("unrelated"), false);
  assert.equal(isContextualRelationship("unknown"), false);
});

test("filters by relationship while retaining unknown records in the default view", () => {
  const projections = [
    { id: "direct", target_relationship: "direct" as const },
    { id: "unknown", target_relationship: "unknown" as const },
    { id: "adjacent", target_relationship: "adjacent" as const },
  ];

  assert.deepEqual(filterProjectionsByRelationship(projections, "all"), projections);
  assert.deepEqual(filterProjectionsByRelationship(projections, "direct"), [projections[0]]);
  assert.deepEqual(filterProjectionsByRelationship(projections, "unknown"), [projections[1]]);
});
