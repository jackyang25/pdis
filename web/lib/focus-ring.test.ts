/**
 * One focus indicator, strong enough to see.
 *
 * There were three: a ring at 20, 25, 30 or 40% of `--ring`, a solid browser outline on some
 * chips and links, and a full-strength ring on a few buttons. The common one, a 20% slate
 * ring on white, measured about 1.4:1 - below the 3:1 a focus indicator needs - so a keyboard
 * reader moving through a result could not see where they were. Controls now share one ring
 * at 60%, and text fields take a ring-coloured border with a soft halo on any focus.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");

function sources(dir: string): string[] {
  return readdirSync(path.join(WEB, dir)).flatMap((name) => {
    const relative = path.join(dir, name);
    if (statSync(path.join(WEB, relative)).isDirectory()) return sources(relative);
    return /\.tsx?$/.test(name) && !name.includes(".test.") ? [relative] : [];
  });
}

const FILES = [...sources("components"), ...sources("app"), ...sources("lib")];

test("every keyboard focus ring is the one visible strength", () => {
  const offenders = FILES.flatMap((file) => {
    const text = readFileSync(path.join(WEB, file), "utf8");
    return [...text.matchAll(/focus-visible:(?:ring-ring(?:\/\d+)?|outline-ring)(?![\w/-])/g)]
      .map((match) => match[0])
      .filter((value) => value !== "focus-visible:ring-ring/60")
      .map((value) => `${file}: ${value}`);
  });
  assert.deepEqual(offenders, [], "use focus-visible:ring-2 focus-visible:ring-ring/60");
});

test("no control relies on the browser's own outline", () => {
  const offenders = FILES.filter((file) =>
    /focus-visible:outline-(?:2|offset-\d)(?![\w-])/.test(readFileSync(path.join(WEB, file), "utf8")),
  );
  assert.deepEqual(offenders, []);
});
