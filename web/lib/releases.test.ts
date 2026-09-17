import assert from "node:assert/strict";
import test from "node:test";
import { CURRENT_RELEASE, RELEASES, formatReleaseDate } from "./releases.ts";

test("published releases have unique identities and newest-first version and date order", () => {
  assert.ok(RELEASES.length > 0);
  assert.equal(CURRENT_RELEASE, RELEASES[0]);
  assert.equal(new Set(RELEASES.map((release) => release.version)).size, RELEASES.length);
  const builds = RELEASES.flatMap(release => release.productionBuild === undefined ? [] : [release.productionBuild]);
  assert.equal(new Set(builds).size, builds.length);
  for (const [index, release] of RELEASES.entries()) {
    assert.match(release.version, /^\d+\.\d+\.\d+$/);
    assert.match(release.releasedOn, /^\d{4}-\d{2}-\d{2}$/);
    assert.equal(new Date(release.releasedOn).toISOString().slice(0, 10), release.releasedOn);
    assert.ok(release.title.trim());
    assert.ok(release.changes.length > 0);
    assert.ok(release.changes.every((change) => change.trim()));
    const older = RELEASES[index + 1];
    if (older) {
      assert.ok(release.releasedOn >= older.releasedOn);
      assert.ok(release.version.localeCompare(older.version, "en", { numeric: true }) > 0);
    }
  }
});

test("release dates preserve the authored calendar day without a completion time", () => {
  assert.equal(formatReleaseDate("2026-09-03"), "Sep 3, 2026");
  assert.equal(formatReleaseDate("2026-09-14"), "Sep 14, 2026");
  assert.equal(formatReleaseDate("2026-01-01"), "Jan 1, 2026");
});
