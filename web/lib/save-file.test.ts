import assert from "node:assert/strict";
import test from "node:test";

import { saveBlob } from "./save-file.ts";

test("a download's object URL outlives the click that starts it", async (t) => {
  const events: string[] = [];
  t.mock.method(URL, "createObjectURL", () => "blob:file");
  t.mock.method(URL, "revokeObjectURL", (url: string) => events.push(`revoke ${url}`));
  const link = { href: "", download: "", click: () => events.push(`click ${link.download}`) };
  (globalThis as { document?: unknown }).document = { createElement: () => link };
  t.after(() => delete (globalThis as { document?: unknown }).document);

  saveBlob(new Blob(["{}"]), "pdis-scout.json");
  // Revoking in the same task cancelled the download in Safari.
  assert.deepEqual(events, ["click pdis-scout.json"]);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(events, ["click pdis-scout.json", "revoke blob:file"]);
});
