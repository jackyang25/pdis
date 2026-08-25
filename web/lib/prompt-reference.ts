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

/**
 * Whether an anchor names a prompt belonging to one tool.
 *
 * The documentation renders one `PromptReference` per tool, each holding its own copy of
 * the file. Without this every one of them would fetch on any prompt deep link, so five
 * sections would load 100 KB apiece to satisfy a link naming one of them.
 *
 * Built from `promptAnchor` rather than matching `prompt-${tool}-` directly, so the anchor
 * format stays owned by one function.
 */
export function isPromptAnchorFor(id: string, tool: ToolKey): boolean {
  return id.startsWith(promptAnchor(tool, ""));
}

/** A link to the instructions behind one label. */
export function promptHref(tool: ToolKey, stage: string): string {
  return `/docs#${promptAnchor(tool, stage)}`;
}
