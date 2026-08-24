import assert from "node:assert/strict";
import test from "node:test";

import {
  RELATIONSHIP_READING_ORDER,
  groupProjectionsByRelationship,
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
  // Says "product", like its siblings. Unqualified, it collided with Scout's fourth result
  // axis, which is a relation to the *target* and has its own "Unrelated" bucket.
  assert.equal(relationshipLabel("unknown"), "Product relation unknown");
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


test("records about the uploaded product come first", () => {
  // 13 of 502 records were `direct` on a real run. In retrieval order they sat anywhere in
  // a flat list, so the 13 that describe the reader's own product were the hardest to find.
  // Order is the whole mechanism: nothing here decides what to expand.
  const groups = groupProjectionsByRelationship([
    { id: "u", target_relationship: "unrelated" as const },
    { id: "a", target_relationship: "adjacent" as const },
    { id: "d", target_relationship: "direct" as const },
    { id: "n", target_relationship: "analogous" as const },
  ]);
  assert.deepEqual(
    groups.map((group) => group.relationship),
    ["direct", "analogous", "adjacent", "unrelated"],
  );
});

test("no group carries an expansion flag, so nothing can open itself", () => {
  const [group] = groupProjectionsByRelationship([
    { id: "d", target_relationship: "direct" as const },
  ]);
  assert.deepEqual(Object.keys(group).sort(), ["items", "relationship"]);
});

test("a relationship with no records draws no group", () => {
  const groups = groupProjectionsByRelationship([
    { id: "d", target_relationship: "direct" as const },
  ]);
  assert.deepEqual(groups.map((group) => group.relationship), ["direct"]);
});

test("every record lands in exactly one group", () => {
  const items = [
    { id: "1", target_relationship: "adjacent" as const },
    { id: "2", target_relationship: "adjacent" as const },
    { id: "3", target_relationship: "unknown" as const },
  ];
  const grouped = groupProjectionsByRelationship(items).flatMap((group) => group.items);
  assert.equal(grouped.length, items.length);
});

test("the reading order covers every relationship the contract declares", () => {
  // A relationship missing from the order would silently drop its records from the list.
  assert.deepEqual(
    [...RELATIONSHIP_READING_ORDER].sort(),
    ["adjacent", "analogous", "direct", "unknown", "unrelated"],
  );
});
