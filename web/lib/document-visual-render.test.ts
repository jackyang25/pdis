import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadComponent } from "../test-support/load-component.ts";

const { DocumentVisual, closeDocumentVisualOnEscape } = loadComponent(fileURLToPath(new URL("../components/document-visual.tsx", import.meta.url)));

test("Escape closes only the active enlarged visual and cancels an enclosing dismiss", () => {
  let closed = false;
  let prevented = false;
  const dialog = { close: () => { closed = true; } };
  const event = {
    target: {
      closest: (selector: string) => selector === "dialog[data-document-visual][open]" ? dialog : null,
    },
    preventDefault: () => { prevented = true; },
  };

  assert.equal(closeDocumentVisualOnEscape(
    event as unknown as Parameters<typeof closeDocumentVisualOnEscape>[0],
  ), true);
  assert.equal(prevented, true);
  assert.equal(closed, true);
});

test("Escape without an enlarged visual remains available to the enclosing overlay", () => {
  let prevented = false;
  const event = {
    target: { closest: () => null },
    preventDefault: () => { prevented = true; },
  };

  assert.equal(closeDocumentVisualOnEscape(
    event as unknown as Parameters<typeof closeDocumentVisualOnEscape>[0],
  ), false);
  assert.equal(prevented, false);
});

test("retained visual names its scope, preserves aspect ratio, and exposes a larger view", () => {
  for (const [scope, label] of [["full_slide", "Slide visual"], ["full_page", "Page visual"], ["embedded_picture", "Document image"]]) {
    const html = renderToStaticMarkup(React.createElement(DocumentVisual, {
      block: { id: "doc/b-1", content: "[image]", heading_stack: [], structural_meta: { visual_scope: scope },
        image: { media_type: "image/png", data_base64: "AA==", width: 1600, height: 900 } },
    }));
    assert.match(html, new RegExp(label));
    assert.match(html, /width="1600" height="900"/);
    assert.match(html, /View larger/);
    assert.match(html, /<dialog[^>]*data-document-visual="true"[^>]*aria-labelledby=/);
    assert.doesNotMatch(html, /\[image\]/);
  }
});

test("historical images without dimensions do not claim zero size", () => {
  const html = renderToStaticMarkup(React.createElement(DocumentVisual, {
    block: { id: "doc/b-1", content: "[image]", heading_stack: [], structural_meta: {},
      image: { media_type: "image/png", data_base64: "AA==", width: 0, height: 0 } },
  }));
  for (const tag of html.match(/<img[^>]*>/g) ?? []) {
    assert.doesNotMatch(tag, /width=|height=/);
  }
  assert.equal(html.match(/<img/g)?.length, 2);
});
