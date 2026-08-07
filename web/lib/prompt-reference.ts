/**
 * Where a published prompt lives in the documentation.
 *
 * Mirrors `catalog_reference` in `shared/prompt_catalog.py`. A tooltip that
 * wants to link to the instructions behind a label, the documentation panel that
 * renders them, and the deep-link handler all compose the anchor here rather
 * than each writing the same template string.
 */

/** Tools whose model instructions are published. */
export type ToolKey = "chunker" | "inspector" | "aligner" | "expert" | "scout";

/**
 * A prompt's anchor, qualified by tool.
 *
 * Stage names are unique only within a tool — two tools may reasonably both call
 * a stage `grader` — so the tool is part of the identity, not decoration.
 */
export function promptAnchor(tool: ToolKey, stage: string): string {
  return `prompt-${tool}-${stage}`;
}

/** A link to the instructions behind one label. */
export function promptHref(tool: ToolKey, stage: string): string {
  return `/docs#${promptAnchor(tool, stage)}`;
}
