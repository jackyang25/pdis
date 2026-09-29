import type { ExternalToolDefinition } from "./tools.ts";

/** A product an external workflow opens in, named as its shortcut is labelled. */
export type BrandName = ExternalToolDefinition["shortcuts"][number]["label"];

export type BrandMark = {
  /** The file under public/icons/brands. */
  file: string;
  /**
   * How its maker presents it: `own` in the colour the file carries, `monochrome` in black on
   * a light surface and white on a dark one.
   *
   * Per brand rather than one rule for all, because the brands differ: OpenAI's mark is
   * black or white, and Claude's is its terracotta. Drawing both in one colour matched them
   * to each other at the cost of showing one of them in a colour its maker does not use.
   */
  colour: "own" | "monochrome";
};

/**
 * Where each linked product's mark lives, and how it is coloured.
 *
 * Keyed by the shortcut label, so a new destination in `lib/tools.ts` does not compile until
 * it has a mark. These are other companies' logos, not PDIS identity icons, which is why they
 * sit beside `icons/pdis` rather than in it. The files are the official ones, unmodified:
 * not redrawn, cropped or recoloured, because brand guidelines permit the mark as supplied.
 */
export const BRAND_MARKS: Record<BrandName, BrandMark> = {
  ChatGPT: { file: "chatgpt.svg", colour: "monochrome" },
  Claude: { file: "claude.svg", colour: "own" },
};
