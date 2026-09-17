import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import { createPreviewWorkspace } from "./preview-scout-review.mjs";

test("preview copies real components without credentials or production routes and cleans up", async () => {
  const preview = await createPreviewWorkspace();
  try {
    assert.match(await readFile(`${preview.web}/app/scout/page.tsx`, "utf8"), /export function DocumentTargetReviewCheckpoint/);
    await assert.rejects(access(`${preview.web}/.env.local`));
    await assert.rejects(access(`${preview.web}/app/api`));
    assert.match(await readFile(`${preview.web}/app/layout.tsx`, "utf8"), /connect-src 'self'/);
    assert.doesNotMatch(await readFile(`${preview.web}/app/layout.tsx`, "utf8"), /<AppShell>/);
  } finally {
    await preview.cleanup();
  }
  await assert.rejects(access(preview.root));
});
