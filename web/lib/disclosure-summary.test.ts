import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return sources(full);
    return entry.name.endsWith(".tsx") && !entry.name.includes(".test.") ? [full] : [];
  });
}

test("no disclosure draws the browser's own marker", () => {
  // The native triangle was the one marker in the suite nobody styled: a different weight,
  // colour and position on each platform, beside Lucide chevrons everywhere else. Every
  // `<summary>` either is `DisclosureSummary`, is a full-width `EXPANDABLE_ROW`, or hides the
  // marker because it draws its own chevron.
  const offenders: string[] = [];
  for (const file of [...sources(path.join(WEB, "app")), ...sources(path.join(WEB, "components"))]) {
    const text = readFileSync(file, "utf8");
    for (const match of text.matchAll(/<summary\b[^>]*>/g)) {
      // A mention in a comment is written in backticks; an element never is.
      if (text[(match.index ?? 0) - 1] === "`") continue;
      if (!/webkit-details-marker\]:hidden|EXPANDABLE_ROW/.test(match[0])) {
        offenders.push(`${path.relative(WEB, file)}: ${match[0].slice(0, 80)}`);
      }
    }
  }
  assert.deepEqual(offenders, []);
});
