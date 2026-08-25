/**
 * One shape per kind of text, enforced rather than remembered.
 *
 * Eight call sites wrote a quotation's styling by hand and had already drifted apart: two
 * used the muted tone where a quote should be full contrast, one used `pl-2.5` where the
 * rest used `pl-3`, and the size split between `text-xs` and `text-[11px]`. Every one looked
 * fine on its own, which is why nobody caught it.
 *
 * These tests are about who owns the styling, not about how it looks.
 */

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const WEB = path.resolve(import.meta.dirname, "..");

/** Every file that renders a Scout or Archivist result. */
const RESULT_VIEWS = [
  "app/scout/page.tsx",
  "app/archivist/page.tsx",
  "components/evidence-provenance.tsx",
  "components/excluded-measurements.tsx",
  "components/comparator-cohort.tsx",
  "components/comparator-distribution-plot.tsx",
  "components/document-source-trace.tsx",
  "components/scout-evidence-map.tsx",
];

/**
 * Files allowed to write a left rule by hand, and why.
 *
 * Both use the same two pixels for something other than a quotation, which is exactly why
 * they have to be named rather than left to a reader's judgment.
 */
const RULE_EXEMPT: Record<string, string> = {
  "components/assistant/ask.tsx":
    "the assistant indenting its own answer: a model's prose, muted, not the document's words",
  "components/labeled-item.tsx":
    "Inspector's coloured status rule, amber or foreground rather than the neutral border",
};

/**
 * Identifiers the interface composed itself, and why each one is not upstream text.
 *
 * The check flags any interpolation rather than only a dotted field path, because upstream
 * text threaded through a prop loses its dot and a dotted-path rule missed one. The cost is
 * that a sentence the interface built from its own literals looks the same, so those are
 * named here with the reason. A name, not a pattern: "anything not containing a dot" is the
 * rule that let the prop-threaded one through in the first place.
 */
const INTERFACE_COMPOSED: Record<string, string> = {
  children: "a component that exists to hold one shape is the fix, not the offence",
  message:
    "the document-context notice builds this from the run's own configuration and three literals",
};

const read = (file: string) => readFileSync(path.join(WEB, file), "utf8");

/** Every view file in the app, so a check cannot be dodged by adding a file. */
function allViews(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(path.join(WEB, dir), { withFileTypes: true })) {
      const next = `${dir}/${entry.name}`;
      if (entry.isDirectory()) walk(next);
      else if (entry.name.endsWith(".tsx")) found.push(next);
    }
  };
  walk("app");
  walk("components");
  return found;
}

test("no result view writes a quotation by hand", () => {
  // `Quoted` owns the border, the padding, the tone and the size. A raw `<blockquote>` is how
  // those four came to have two values each.
  const offenders = RESULT_VIEWS.filter((file) => read(file).includes("<blockquote"));
  assert.deepEqual(
    offenders,
    [],
    "use <Quoted> from components/ui/evidence-text instead of a raw <blockquote>",
  );
});

test("no result view writes a citation highlight by hand", () => {
  // `--tone-marked` already means "a result cites this", and the full-page document trace
  // already highlights with it. A local `<mark>` is how the popover and Archivist came to use
  // grey while the trace used yellow.
  const offenders = RESULT_VIEWS.filter((file) => /<mark\b/.test(read(file)));
  assert.deepEqual(
    offenders,
    [],
    "use <CitedMark> from components/ui/evidence-text instead of a raw <mark>",
  );
});

test("a citation highlight uses the token that means a result cites this", () => {
  // Scoped to the component body, not the file. The first version read the whole file and
  // failed on the comment explaining why the grey was wrong.
  const primitives = read("components/ui/evidence-text.tsx");
  const body = primitives.slice(
    primitives.indexOf("export function CitedMark"),
    primitives.indexOf("export function SourceEntry"),
  );
  assert.match(body, /--tone-marked/);
  assert.ok(
    !body.includes("bg-secondary"),
    "the highlight went back to a neutral grey, which reads as a surface rather than a citation",
  );
});

test("a quotation is full contrast, because it is not the tool's opinion", () => {
  // The tone axis is the whole authorship distinction: exact words at full contrast, a
  // model's reading muted. A muted quotation reads as a judgment.
  const primitives = read("components/ui/evidence-text.tsx");
  const quoted = primitives.slice(
    primitives.indexOf("export function Quoted"),
    primitives.indexOf("export function CitedMark"),
  );
  assert.match(quoted, /text-foreground/);
  assert.ok(
    !quoted.includes("text-muted-foreground"),
    "Quoted must not use the muted tone; that tone means a model wrote it",
  );
});

test("a model's prose and the tool's prose are not the same shape", () => {
  // The pair that needed enforcing. Both are muted at the same size, so tone cannot separate
  // them, and on two lines of the programs table a model's judgment about a program sat
  // directly above the tool's caveat about it looking identical. The box is the difference.
  const primitives = read("components/ui/evidence-text.tsx");
  const slice = (from: string, to: string) =>
    primitives.slice(primitives.indexOf(from), primitives.indexOf(to));
  const reading = slice("export function Reading", "export function Computed");
  const note = slice("export function InterfaceNote", "export function SourceEntry");

  assert.match(reading, /text-muted-foreground/);
  assert.match(note, /text-muted-foreground/);
  assert.ok(
    !/\bborder\b/.test(reading),
    "Reading gained a box, which is what marks the tool's own words",
  );
  assert.match(note, /rounded-md border/);
});

test("upstream text is never rendered in prose styled by hand", () => {
  // The rule this enforces: a value that came from the pipeline has an author, and the reader
  // is entitled to know which one, so it goes through a mode. A literal sentence in the
  // source file has no authorship question at all, which is why a footer, a form's help text
  // or an empty state can still style itself.
  //
  // So the test flags any interpolated body and lets literal text through. A first version
  // keyed on the dot instead, taking `{measurement.semantic_reason}` as upstream and a bare
  // `{description}` as the interface's own, and that missed a pipeline sentence threaded
  // through a prop, which had lost its dot on the way in. `{children}` is the exception: a
  // component that exists to hold one shape is the fix, not the offence.
  //
  // Eight hand-styled upstream sentences existed, at four different margins with one at the
  // wrong size, which is the blockquote drift one step behind.
  const offenders: string[] = [];
  for (const file of RESULT_VIEWS) {
    const lines = read(file).split("\n");
    lines.forEach((line, index) => {
      const isHandStyledProse =
        /<(p|span|div) className="[^"]*leading-relaxed[^"]*text-muted-foreground/.test(line);
      if (!isHandStyledProse) return;
      // The value usually sits on the next line, in the JSX body. Unless the element closes
      // on its own line, in which case the next line belongs to a sibling and reading it
      // blamed this one for the sibling's content.
      const closes = /<\/(p|span|div)>/.test(line);
      const body = closes ? line : `${line}\n${lines[index + 1] ?? ""}`;
      const interpolated = body.match(/\{[a-zA-Z_][A-Za-z0-9_.?[\]]*\}/g) ?? [];
      if (interpolated.some((value) => !(value.slice(1, -1) in INTERFACE_COMPOSED))) {
        offenders.push(`${file}:${index + 1}`);
      }
    });
  }
  assert.deepEqual(
    offenders,
    [],
    "route upstream text through <Reading>, <Computed>, <Quoted> or <InterfaceNote>",
  );
});

test("each mode has a caller, so none is a shape nobody uses", () => {
  // `Quoted` and `InterfaceNote` both sat at zero callers while the page hand-rolled the same
  // styling, which is how a primitive becomes documentation of an intention rather than a
  // constraint on the output.
  const source = RESULT_VIEWS.map(read).join("\n");
  const shapes = ["Quoted", "Reading", "Computed", "InterfaceNote", "CitedMark", "SourceEntry", "Literal"];
  for (const mode of shapes) {
    assert.match(source, new RegExp(`<${mode}[\\s/>]`), `<${mode}> has no callers`);
  }
});

test("the modes are declared in one file, and nothing re-declares them", () => {
  const others = RESULT_VIEWS.filter((file) =>
    /export function (Quoted|Reading|Computed|InterfaceNote|CitedMark|Literal)\b/.test(read(file)),
  );
  assert.deepEqual(others, [], "a second definition of a mode defeats the point of having one");
});

test("every result view file in the list still exists", () => {
  // A renamed file would silently drop out of the checks above.
  for (const file of RESULT_VIEWS) {
    assert.doesNotThrow(() => read(file), `${file} is listed but missing`);
  }
});

test("a left rule means a quotation, everywhere in the app", () => {
  // The check that has to sweep the whole app rather than a list. `RESULT_VIEWS` is hand-kept
  // and missed the evidence map, where a model's reasoning carried the quotation rule while
  // the document's own words next to it did not: the shape said the opposite of the truth in
  // both directions. Anything using those two pixels for something else is named above.
  const offenders = allViews().filter(
    (file) =>
      !RULE_EXEMPT[file] &&
      !file.endsWith("ui/evidence-text.tsx") &&
      /border-l-2[^"]*border-border[^"]*pl-3|<blockquote|<mark\b/.test(read(file)),
  );
  assert.deepEqual(
    offenders,
    [],
    "use <Quoted> or <CitedMark>, or name the file in RULE_EXEMPT with its reason",
  );
});

test("every exemption still exists and still needs to be one", () => {
  for (const [file, reason] of Object.entries(RULE_EXEMPT)) {
    assert.doesNotThrow(() => read(file), `${file} is exempt but missing`);
    assert.ok(reason.length > 20, `${file} is exempt without a stated reason`);
  }
});
