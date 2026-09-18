import assert from "node:assert/strict";
import test from "node:test";
import { CURRENT_RELEASE, RELEASES } from "./releases.ts";

test("versions have unique identities and newest-first order independent of deployment dates", () => {
  assert.ok(RELEASES.length > 0);
  assert.equal(CURRENT_RELEASE, RELEASES[0]);
  assert.equal(new Set(RELEASES.map(release => release.version)).size, RELEASES.length);
  for (const [index, release] of RELEASES.entries()) {
    assert.match(release.version, /^\d+\.\d+\.\d+$/);
    assert.ok(release.title.trim());
    assert.ok(release.sections.length > 0);
    for (const section of release.sections) {
      if (section.title !== undefined) assert.ok(section.title.trim());
      assert.ok(section.changes.length > 0);
      assert.ok(section.changes.every(change => change.trim()));
    }
    const older = RELEASES[index + 1];
    if (older) assert.ok(release.version.localeCompare(older.version, "en", { numeric: true }) > 0);
  }
});
