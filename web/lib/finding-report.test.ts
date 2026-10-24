import assert from "node:assert/strict";
import test from "node:test";

import { findingReportText } from "./finding-report.ts";

test("a report carries what the team needs to find the finding again", () => {
  const text = findingReportText({
    tool: "Screener",
    finding: "Partly answered: Product Development Strategy · PDS.LCS.10",
    detail: "  DARE-NHC plans CDMO RFQs.  ",
    reference: "PDS.LCS.10",
    location: "CDMO Identification Report · Page 12",
    note: "The plan is in section 4, so this is answered.",
  });
  assert.equal(text, [
    "PDIS finding report",
    "Tool: Screener",
    "Finding: Partly answered: Product Development Strategy · PDS.LCS.10",
    "Text: DARE-NHC plans CDMO RFQs.",
    "Reference: PDS.LCS.10",
    "Where: CDMO Identification Report · Page 12",
    "What is wrong: The plan is in section 4, so this is answered.",
  ].join("\n"));
});

test("absent parts are left out, and a report without a note says so", () => {
  const text = findingReportText({ tool: "Drafter", finding: "Suggested target: Efficacy" });
  assert.equal(text, "PDIS finding report\nTool: Drafter\nFinding: Suggested target: Efficacy\nWhat is wrong: (not stated)");
});
