import assert from "node:assert/strict";
import test from "node:test";
import { CURRENT_RELEASE, RELEASES, formatReleaseDate } from "./releases.ts";

test("published releases have unique identities and newest-first version and date order", () => {
  assert.ok(RELEASES.length > 0);
  assert.equal(CURRENT_RELEASE, RELEASES[0]);
  assert.equal(new Set(RELEASES.map((release) => release.version)).size, RELEASES.length);
  assert.equal(new Set(RELEASES.map((release) => release.productionBuild)).size, RELEASES.length);
  for (const [index, release] of RELEASES.entries()) {
    assert.match(release.version, /^\d+\.\d+\.\d+$/);
    assert.ok(Number.isFinite(Date.parse(release.releasedAt)));
    assert.ok(release.title.trim());
    assert.ok(release.changes.length > 0);
    assert.ok(release.changes.every((change) => change.trim()));
    const older = RELEASES[index + 1];
    if (older) {
      assert.ok(Date.parse(release.releasedAt) >= Date.parse(older.releasedAt));
      assert.ok(release.version.localeCompare(older.version, "en", { numeric: true }) > 0);
    }
  }
});

test("release times use Eastern time, independent of the reader's time zone", () => {
  assert.equal(formatReleaseDate("2026-09-03T00:17:00-04:00"), "Sep 3, 2026, 12:17 AM EDT");
  assert.equal(formatReleaseDate("2026-09-14T14:10:00-04:00"), "Sep 14, 2026, 2:10 PM EDT");
  assert.equal(formatReleaseDate("2026-09-14T16:31:00-04:00"), "Sep 14, 2026, 4:31 PM EDT");
});
