/**
 * The header leaving on the way down and returning on the way up.
 *
 * A pure function so these rules are testable at all: the alternative is logic inside a scroll
 * handler, where the only way to check the jitter floor or the reduced-motion rule is to
 * scroll a real page and watch.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import {
  HEADER_HIDE_AFTER,
  HEADER_SCROLL_DELTA,
  nextHeaderVisibility,
  type HeaderVisibility,
} from "./header-visibility.ts";

/** One scroll event, from a current state and a movement. */
const move = (
  current: HeaderVisibility,
  from: number,
  to: number,
  reduceMotion = false,
) => nextHeaderVisibility(current, { scrollY: to, previousScrollY: from, reduceMotion });

test("scrolling down hides it, scrolling up brings it back", () => {
  assert.equal(move("visible", 400, 500), "hidden");
  assert.equal(move("hidden", 500, 400), "visible");
});

test("near the top it is always showing", () => {
  // Above this the header has not been scrolled past, so hiding it would remove something the
  // reader can still see rather than something in the way.
  assert.equal(move("hidden", 0, HEADER_HIDE_AFTER), "visible");
  assert.equal(move("hidden", 200, 10), "visible");
  assert.equal(move("visible", 0, 20), "visible");
});

test("it hides only once the header itself has gone by", () => {
  assert.equal(move("visible", HEADER_HIDE_AFTER - 10, HEADER_HIDE_AFTER), "visible");
  assert.equal(move("visible", HEADER_HIDE_AFTER, HEADER_HIDE_AFTER + 20), "hidden");
});

test("an elastic overscroll past the top does not hide it", () => {
  // macOS reports a negative scroll position during a bounce.
  assert.equal(move("visible", 30, -40), "visible");
  assert.equal(move("hidden", 30, -40), "visible");
});

test("a movement too small to be a direction changes nothing", () => {
  // A trackpad emits a drizzle of one and two pixel events, often alternating sign at the end
  // of a fling. Without a floor the header flickers, which is worse than one that never moves.
  for (const delta of [0, 1, -1, HEADER_SCROLL_DELTA - 1, -(HEADER_SCROLL_DELTA - 1)]) {
    assert.equal(move("hidden", 500, 500 + delta), "hidden", `delta ${delta}`);
    assert.equal(move("visible", 500, 500 + delta), "visible", `delta ${delta}`);
  }
});

test("a movement at the floor does count", () => {
  assert.equal(move("visible", 500, 500 + HEADER_SCROLL_DELTA), "hidden");
  assert.equal(move("hidden", 500, 500 - HEADER_SCROLL_DELTA), "visible");
});

test("a reader who asked for less motion gets a header that does not move", () => {
  // Not a header that appears and disappears without a transition, which is the same movement
  // with the easing removed: more startling, not less.
  assert.equal(move("visible", 400, 900, true), "visible");
  assert.equal(move("hidden", 400, 900, true), "visible");
  assert.equal(move("visible", 900, 400, true), "visible");
});

test("the floor is smaller than the distance before hiding", () => {
  // Otherwise one scroll event could cross the threshold and be dismissed as jitter in the
  // same step, and the header would never hide at all.
  assert.ok(HEADER_SCROLL_DELTA < HEADER_HIDE_AFTER);
});

test("a long fling down then up ends showing", () => {
  // The property that matters, as a sequence rather than a single step.
  let state: HeaderVisibility = "visible";
  for (let y = 0; y < 2000; y += 50) state = move(state, y, y + 50);
  assert.equal(state, "hidden");
  for (let y = 2000; y > 0; y -= 50) state = move(state, y, y - 50);
  assert.equal(state, "visible");
});

test("the header slides rather than reflowing, and says so once", () => {
  const shell = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "app-shell.tsx"),
    "utf8",
  );
  // A transform, so the page does not shift under a reader's eyes when the header goes.
  assert.match(shell, /-translate-y-full/);
  assert.match(shell, /HEADER_SLIDE_MOTION/, "the slide is not the shared recipe");
  // Every rule is in the pure function; the component asks and renders.
  assert.match(shell, /nextHeaderVisibility/);
  assert.ok(
    !/scrollY >|scrollY <|prefers-reduced-motion.*hidden/.test(shell),
    "a visibility rule is being decided in the component",
  );
});

test("tabbing into a hidden header brings it back", () => {
  // Otherwise a keyboard reader is operating a control they cannot see.
  const shell = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "app-shell.tsx"),
    "utf8",
  );
  assert.match(shell, /onFocusCapture=\{reveal\}/);
});

test("the scroll listener does not block scrolling", () => {
  const shell = readFileSync(
    path.resolve(import.meta.dirname, "..", "components", "app-shell.tsx"),
    "utf8",
  );
  // The handler never calls `preventDefault`, and saying so lets the browser scroll without
  // waiting for it.
  assert.match(shell, /\{ passive: true \}/);
  assert.match(shell, /removeEventListener\("scroll"/, "the listener is never removed");
});
