import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

// Exercise the actual page's render gate without mocking its result viewer,
// network hooks, or configuration tree. Navigation remounts local setup state
// as false when a previous result exists; busy survives in the session store.
function panelIsVisible(tool: string, result: unknown, busy: boolean, opened: boolean): boolean {
  const file = ts.createSourceFile(
    "page.tsx",
    readFileSync(new URL(`../app/${tool}/page.tsx`, import.meta.url), "utf8"),
    ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX,
  );
  let gate: ts.Expression | undefined;
  function visit(node: ts.Node) {
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) && node.tagName.getText(file) === "RunPanel") {
      let parent = node.parent;
      while (!ts.isJsxExpression(parent) && parent.parent) parent = parent.parent;
      if (ts.isJsxExpression(parent) && parent.expression && ts.isBinaryExpression(parent.expression)) {
        assert.equal(parent.expression.operatorToken.kind, ts.SyntaxKind.AmpersandAmpersandToken);
        gate = parent.expression.left;
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(file);
  assert.ok(gate, `${tool} must expose a conditional run panel`);
  return Boolean(new Function("result", "busy", "showRunPanel", "showSetup", "session",
    `return (${gate.getText(file)});`)(result, busy, opened, opened, { result, busy }));
}

for (const tool of ["inspector", "aligner", "scout", "screener"]) {
  test(`${tool}: returning to an active run shows progress despite a previous result`, () => {
    assert.equal(panelIsVisible(tool, { id: "previous" }, true, false), true);
  });
  test(`${tool}: idle results stay collapsed and New analysis still opens setup`, () => {
    assert.equal(panelIsVisible(tool, { id: "previous" }, false, false), false);
    assert.equal(panelIsVisible(tool, { id: "previous" }, false, true), true);
    assert.equal(panelIsVisible(tool, null, false, false), true);
  });
}
