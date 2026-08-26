"use client";

import { useCallback, useState } from "react";

/**
 * A request to show one passage in the document trace.
 *
 * One value rather than two parallel props, because the two travel together and always
 * have: every caller that has a block also knows which finding sent it there, and the
 * viewer needs both to answer "which layer should be showing when this opens".
 *
 * `annotationId` is optional and its absence means something. A click on a specific
 * finding names that finding; a click from a section card or a priority row names only a
 * passage, and the viewer is right to show every layer on it rather than guess.
 */
export type TraceFocus = {
  blockId: string;
  /** The annotation the reader clicked, when one sent them. */
  annotationId?: string;
};

/**
 * The state every tool page kept for its document trace.
 *
 * All four tools held the same `useState` plus the same two `useCallback`s, identical down
 * to the tab they switch to. Four copies is how the annotation half of this would have
 * been added to three of them and forgotten in the fourth.
 *
 * `reveal` is the only part that was ever tool-specific — where the trace lives on that
 * page — so it is the only part passed in. It must be stable, like any dependency.
 */
export function useTraceFocus(reveal: () => void) {
  const [focus, setFocus] = useState<TraceFocus | null>(null);

  const open = useCallback(
    (next: TraceFocus) => {
      setFocus(next);
      reveal();
    },
    [reveal],
  );

  /**
   * Cleared only if it is still the request that was served.
   *
   * A second click on the same passage has to change the state to be noticed, so a stale
   * consume must not wipe a newer request that arrived while the first was in flight.
   */
  const consume = useCallback((served: TraceFocus) => {
    setFocus((current) => (current?.blockId === served.blockId ? null : current));
  }, []);

  return { focus, open, consume };
}
