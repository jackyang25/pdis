import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

test("Aligner uses the shared authority copy and comparison count presentation", () => {
  const page = readFileSync(new URL("../app/aligner/page.tsx", import.meta.url), "utf8");
  assert.match(page, /description=\{toolAuthority\("aligner"\)\}/);
  assert.match(page, /<CollapsibleCard[\s\S]*?count=\{findings.length\}/);
  assert.doesNotMatch(page, /Coherence, not feasibility/);
});

test("Aligner only shows the whole-block citation note for block connections", () => {
  const { AlignerTraceInspector } = loadComponent(fileURLToPath(new URL("../components/aligner-document-trace.tsx", import.meta.url)), {}, ["AlignerTraceInspector"]);
  for (const type of ["exact", "block", "unavailable"]) {
    const html = renderToStaticMarkup(React.createElement(AlignerTraceInspector, {
      annotation: { sourceRef: { side: "comparison", verdict: "falls_short", comparison: "Reference → Plan", requirementId: "r-1", question: "Does the plan meet the bar?", requirement: "The target is 24 months.", statement: "The plan states 36 months." } },
      connection: { type, blockId: "b-1" },
      passages: { passages: [], reveal: () => {} },
    }));
    assert.equal(html.includes("not as exact quotations"), type === "block");
  }
});

test("Aligner trace marks extracted requirements as model readings on both sides", () => {
  const { AlignerTraceInspector } = loadComponent(fileURLToPath(new URL("../components/aligner-document-trace.tsx", import.meta.url)), {}, ["AlignerTraceInspector"]);
  for (const side of ["reference", "comparison"]) {
    const html = renderToStaticMarkup(React.createElement(AlignerTraceInspector, {
      annotation: { sourceRef: { side, verdict: "falls_short", comparison: "Reference → Plan", requirementId: "r-1", question: "Does the plan meet the bar?", requirement: "The target is 24 months.", statement: "The plan states 36 months." } },
      connection: { type: "exact", blockId: "b-1" },
      passages: { passages: [], reveal: () => {} },
    }));
    assert.match(html, /The comparison asks/);
    assert.match(html, /The target is 24 months/);
    const requirementSection = html.split("The requirement</div>")[1].split("</section>")[0];
    assert.match(requirementSection, /<svg[^>]*aria-hidden="true"[\s\S]*?<\/svg>The target is 24 months/);
    assert.equal(html.includes("The plan states 36 months."), side === "comparison");
  }
});
