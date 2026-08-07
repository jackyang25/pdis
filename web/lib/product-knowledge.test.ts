/**
 * The documentation catalogue must be renderable, not merely valid.
 *
 * `/docs` is statically prerendered, so a lookup that misses does not degrade one
 * card — it fails the whole build. That is exactly what happened when Expert's
 * workflow graph was added to `shared/product_knowledge.json` with no icon entry:
 * `Record<string, …>` compiled cleanly and the export died with "Cannot read
 * properties of undefined (reading 'split')". `npm run build` reports it, but only
 * after the compile step it is easy to stop reading at.
 *
 * The catalogue is read from the file rather than through `product-knowledge.ts`,
 * because that module imports JSON the way webpack allows and plain node does not.
 * Reading the bytes also means this checks what ships.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  PDIS_ICON_PATHS,
  graphIcon,
  graphIconIsDeclared,
} from "./pdis-icon-paths.ts";

type Graph = { id: string; nodes: { id: string }[] };

function architectureGraphs(): Graph[] {
  const raw = readFileSync(
    new URL("../../shared/product_knowledge.json", import.meta.url),
    "utf8",
  );
  const knowledge = JSON.parse(raw) as {
    sections: { content: { type: string; graphs?: Graph[] }[] }[];
  };
  return knowledge.sections.flatMap((section) =>
    section.content.flatMap((block) =>
      block.type === "architecture" ? (block.graphs ?? []) : [],
    ),
  );
}

test("the catalogue publishes some workflow graphs", () => {
  // Guards the reader itself: a shape change that returned nothing would make
  // every other test here pass vacuously.
  assert.ok(architectureGraphs().length >= 5);
});

test("every published workflow graph declares an icon", () => {
  const missing = architectureGraphs()
    .map((graph) => graph.id)
    .filter((id) => !graphIconIsDeclared(id));
  assert.deepEqual(
    missing,
    [],
    "add these graph ids to GRAPH_ICONS in lib/pdis-icon-paths.ts",
  );
});

test("every icon a graph resolves to has a real asset path", () => {
  for (const graph of architectureGraphs()) {
    const name = graphIcon(graph.id);
    assert.ok(
      PDIS_ICON_PATHS[name],
      `${graph.id} maps to icon "${name}", which has no path`,
    );
  }
});

test("an undeclared graph falls back rather than throwing", () => {
  // The fallback keeps a future omission a wrong picture instead of a failed
  // deploy. The test above is what stops it staying wrong.
  assert.ok(PDIS_ICON_PATHS[graphIcon("a-tool-nobody-has-built")]);
});

test("every tool that runs a pipeline publishes a graph", () => {
  const published = new Set(architectureGraphs().map((graph) => graph.id));
  for (const tool of ["chunker", "inspector", "aligner", "expert", "scout"]) {
    assert.ok(published.has(tool), `${tool} publishes no workflow graph`);
  }
});

test("graph ids are unique, so a selector cannot show two as one", () => {
  const ids = architectureGraphs().map((graph) => graph.id);
  assert.equal(new Set(ids).size, ids.length);
});

/**
 * Per-tool content sits at one altitude.
 *
 * A section whose id is a tool id is that tool's reference and renders inside its
 * detail panel. Scout's evidence semantics used to be a page-level peer of "Overview",
 * which is how one tool came to be documented at system altitude and twice over.
 */
test("a section named after a tool is not also a page-level section", () => {
  const raw = readFileSync(
    new URL("../../shared/product_knowledge.json", import.meta.url),
    "utf8",
  );
  const ids: string[] = (JSON.parse(raw) as { sections: { id: string }[] }).sections.map(
    (section) => section.id,
  );
  const toolIds = new Set(architectureGraphs().map((graph) => graph.id));
  const atToolAltitude = ids.filter((id) => toolIds.has(id));

  // Scout is the only tool with reference content today. If another gains some, it
  // belongs in the same place — and if one is added to PAGE_SECTIONS by mistake, the
  // docs page would render it twice.
  assert.deepEqual(atToolAltitude, ["scout"]);
});
