/**
 * Binds the browser's format list to the service that owns the decision.
 *
 * Narrowing supported formats is a deliberate act in `services/chunker`. Without
 * this test the web layer keeps offering whatever it last hardcoded, so an
 * upload control can accept a file the parser will refuse.
 */

import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_FORMAT_HINT,
  ATTACHMENT_MEDIA_PREFIXES,
  DOCUMENT_ACCEPT,
  DOCUMENT_FORMAT_HINT,
  DOCUMENT_SUFFIXES,
  isSupportedDocument,
} from "./document-formats.ts";

const WEB = path.resolve(import.meta.dirname, "..");
const REPO = path.resolve(WEB, "..");
const CHUNKER_PIPELINE = path.join(REPO, "services", "chunker", "pipeline.py");
/** This module is the mirror, so it is the one file allowed to name extensions. */
const AUTHORITY = path.join("lib", "document-formats.ts");

test("the mirrored set matches services/chunker", () => {
  const source = readFileSync(CHUNKER_PIPELINE, "utf8");
  const declaration = /^DOCUMENT_SUFFIXES\s*=\s*\{([^}]*)\}/m.exec(source);
  assert.ok(declaration, "DOCUMENT_SUFFIXES is no longer declared as a set literal");
  const owned = [...declaration[1].matchAll(/"([^"]+)"|'([^']+)'/g)]
    .map((match) => match[1] ?? match[2])
    .sort();
  assert.deepEqual(
    [...DOCUMENT_SUFFIXES].sort(),
    owned,
    "web/lib/document-formats.ts drifted from services/chunker/pipeline.py",
  );
});

test("derived values stay consistent with the set", () => {
  assert.equal(DOCUMENT_ACCEPT, DOCUMENT_SUFFIXES.join(","));
  assert.equal(DOCUMENT_FORMAT_HINT, "DOCX, PPTX");
  assert.ok(isSupportedDocument("Plan.DOCX"), "extension matching must ignore case");
  assert.ok(!isSupportedDocument("plan.pdf"), "a rendered format is not a document source");
  assert.ok(!isSupportedDocument("docx"), "a bare word is not an extension");
});

test("the attachment set matches services/chunker", () => {
  const source = readFileSync(CHUNKER_PIPELINE, "utf8");
  const declaration = /^ATTACHMENT_MEDIA_PREFIXES\s*=\s*\(([^)]*)\)/m.exec(source);
  assert.ok(declaration, "ATTACHMENT_MEDIA_PREFIXES is no longer declared as a tuple");
  const owned = [...declaration[1].matchAll(/"([^"]+)"|'([^']+)'/g)]
    .map((match) => match[1] ?? match[2])
    .sort();
  assert.deepEqual(
    [...ATTACHMENT_MEDIA_PREFIXES].sort(),
    owned,
    "web/lib/document-formats.ts drifted from services/chunker/pipeline.py",
  );
});

test("an attachment accepts every document plus its own media types", () => {
  // A conversation attachment is read once and discarded, so it may include
  // formats the analysis path refuses. It may never exclude one the path accepts.
  for (const suffix of DOCUMENT_SUFFIXES) {
    assert.ok(ATTACHMENT_ACCEPT.includes(suffix), `${suffix} is not attachable`);
  }
  assert.equal(ATTACHMENT_ACCEPT, `${DOCUMENT_ACCEPT},image/*`);
  assert.equal(ATTACHMENT_FORMAT_HINT, "DOCX, PPTX, or image files");
});

function sourceFiles(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) out.push(full);
    }
  };
  for (const dir of ["app", "components", "lib"]) walk(path.join(WEB, dir));
  return out;
}

test("no component restates a document extension", () => {
  // Only the dotted form is checked. It is the functional one — an `accept`
  // attribute or a validation branch — where a stale copy silently blocks or
  // admits the wrong file. Descriptive prose that happens to name a format is
  // left readable rather than assembled from template literals.
  const offenders: string[] = [];
  for (const file of sourceFiles()) {
    const relative = path.relative(WEB, file);
    if (relative === AUTHORITY) continue;
    for (const [match] of readFileSync(file, "utf8").matchAll(/"[^"\n]*\.(?:docx|pptx)[^"\n]*"/gi)) {
      offenders.push(`${relative}: ${match}`);
    }
  }
  assert.deepEqual(
    offenders,
    [],
    "import DOCUMENT_ACCEPT or DOCUMENT_SUFFIXES from lib/document-formats.ts",
  );
});
