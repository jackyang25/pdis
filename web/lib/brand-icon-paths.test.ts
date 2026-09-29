import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { BRAND_MARKS } from "./brand-icon-paths.ts";
import { EXTERNAL_TOOLS } from "./tools.ts";

const BRANDS = path.join(path.resolve(import.meta.dirname, ".."), "public/icons/brands");

// The type makes every label name a path; only the disk can say the file is there. A missing
// mark draws nothing at all, because a mask with no image hides the box it covers.
test("every product a shortcut opens in has its mark on disk", () => {
  const labels = new Set(EXTERNAL_TOOLS.flatMap((tool) => tool.shortcuts.map((shortcut) => shortcut.label)));
  assert.ok(labels.size > 0, "no shortcuts were found");
  for (const label of labels) {
    const file = path.join(BRANDS, BRAND_MARKS[label].file);
    assert.ok(existsSync(file), `${label} maps to ${BRAND_MARKS[label].file}, which is not in public/icons/brands`);
  }
});
