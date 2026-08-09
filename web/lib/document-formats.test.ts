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
  attachablePaste,
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


/**
 * A clipboard or a drag, filtered to what may actually be attached.
 *
 * `DataTransfer` is not constructible in this runtime, so these stand one in: the
 * function reads only `getData` and `files`, and the point of the tests is the decision,
 * not the DOM.
 */
function transfer(
  { text = "", files = [] as { name: string; type: string }[] } = {},
): DataTransfer {
  return {
    getData: (format: string) => (format === "text/plain" ? text : ""),
    files: files as unknown as FileList,
  } as unknown as DataTransfer;
}

test("a pasted screenshot is attachable", () => {
  const { files, textWon } = attachablePaste(
    transfer({ files: [{ name: "image.png", type: "image/png" }] }),
  );
  assert.equal(files.length, 1);
  assert.equal(textWon, false);
});

test("a pasted document is attachable", () => {
  // The picker accepts DOCX and PPTX, so a paste that carries one accepts it too:
  // filtering differently here would advertise one set and accept another.
  const { files } = attachablePaste(
    transfer({ files: [{ name: "profile.docx", type: "" }] }),
  );
  assert.equal(files.length, 1);
});

test("a paste carrying text is left alone, even when it also carries a picture", () => {
  // Copying a table from a spreadsheet puts plain text, HTML and an image of itself on
  // the clipboard at once. Attaching the image would silently replace a paste the user
  // meant as text.
  const { files, textWon } = attachablePaste(
    transfer({
      text: "Measure\tTarget\nEfficacy\t80%",
      files: [{ name: "image.png", type: "image/png" }],
    }),
  );
  assert.deepEqual(files, []);
  // Reported, not swallowed: the caller says the file did not come with the text, so a
  // dropped figure is a visible choice rather than a silent one.
  assert.equal(textWon, true);
});

test("a plain text paste reports nothing to say", () => {
  // No file was carried, so there is nothing the text took precedence over.
  const { files, textWon } = attachablePaste(transfer({ text: "just words" }));
  assert.deepEqual(files, []);
  assert.equal(textWon, false);
});

test("an unsupported file is not attached", () => {
  const { files, textWon } = attachablePaste(
    transfer({ files: [{ name: "notes.pdf", type: "application/pdf" }] }),
  );
  assert.deepEqual(files, []);
  // Nothing to report either: an unsupported file is not something text won over.
  assert.equal(textWon, false);
});

test("nothing at all is handled without throwing", () => {
  assert.deepEqual(attachablePaste(null), { files: [], textWon: false });
  assert.deepEqual(attachablePaste(transfer()), { files: [], textWon: false });
});
