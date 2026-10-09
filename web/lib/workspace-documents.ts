import type { ContentBlock } from "./api";

/**
 * Which document a run read, decided by content rather than by filename.
 *
 * A block's address is `<filename stem>/b-<ordinal>`, so two runs over different versions
 * of `cTPP.docx` produce the same addresses. Each run's document is fingerprinted from its
 * blocks; one fingerprint per name is one document shared by every run that read it. More
 * than one fingerprint under a name tags every version - `cTPP@3f9a1c` - so each run's
 * citations open the text it actually read, whatever order the runs arrive in.
 *
 * Only reference fields are rewritten: a string that is exactly a renamed block ID, and a
 * `doc_id` / `*_doc_id` field that is exactly a renamed document. Prose is never touched.
 */
export type WorkspaceRun = { id: string; blocks: ContentBlock[]; analysis: unknown };

export function resolveDocumentVersions<T extends WorkspaceRun>(runs: T[]): T[] {
  const fingerprints = runs.map((run) => {
    const byDoc = new Map<string, ContentBlock[]>();
    for (const block of run.blocks) byDoc.set(block.doc_id, [...(byDoc.get(block.doc_id) ?? []), block]);
    return new Map([...byDoc].map(([doc, blocks]) => [doc, fingerprint(blocks)]));
  });
  const versions = new Map<string, Set<string>>();
  for (const prints of fingerprints) {
    for (const [doc, print] of prints) versions.set(doc, (versions.get(doc) ?? new Set()).add(print));
  }
  // Computed once per name, not per run: two runs sharing a document must agree on its tag,
  // and the collision check needs every version under a name in hand at once.
  const tagsByDoc = new Map<string, Map<string, string>>();
  for (const [doc, prints] of versions) {
    if (prints.size > 1) tagsByDoc.set(doc, versionTags([...prints]));
  }
  return runs.map((run, index) => {
    const docRenames = new Map<string, string>();
    for (const [doc, print] of fingerprints[index]) {
      const tags = tagsByDoc.get(doc);
      if (tags) docRenames.set(doc, `${doc}@${tags.get(print)}`);
    }
    if (docRenames.size === 0) return run;
    const blockRenames = new Map<string, string>();
    const blocks = run.blocks.map((block) => {
      const doc = docRenames.get(block.doc_id);
      if (!doc) return block;
      const suffix = block.id.startsWith(`${block.doc_id}/`) ? block.id.slice(block.doc_id.length + 1) : block.id;
      const id = `${doc}/${suffix}`;
      blockRenames.set(block.id, id);
      return { ...block, id, doc_id: doc };
    });
    return {
      ...run,
      blocks,
      analysis: rewrite(run.analysis, blockRenames, docRenames, ""),
    };
  });
}

/**
 * One short tag per distinct fingerprint, falling back to the full fingerprint for every
 * version under a name the moment two of them disagree on it.
 *
 * The short tag is the fingerprint's low six hex digits, not its high ones: `fingerprint`
 * packs a 53-bit hash into 14 hex characters, so the leading digit only ever carries a
 * couple of bits and the high end of the string is the weak end. Taking six characters from
 * there would make two different documents far likelier to tag alike than six random hex
 * digits should — which silently re-merges exactly the versions this module exists to keep
 * apart. Exported so the collision path is testable without finding a real collision.
 */
export function versionTags(prints: string[]): Map<string, string> {
  const short = new Map(prints.map((print) => [print, print.slice(-6)] as const));
  const counts = new Map<string, number>();
  for (const tag of short.values()) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  const collided = [...counts.values()].some((count) => count > 1);
  return collided ? new Map(prints.map((print) => [print, print])) : short;
}

function rewrite(value: unknown, blocks: Map<string, string>, docs: Map<string, string>, key: string): unknown {
  if (typeof value === "string") {
    if (blocks.has(value)) return blocks.get(value);
    if ((key === "doc_id" || key.endsWith("_doc_id")) && docs.has(value)) return docs.get(value);
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => rewrite(item, blocks, docs, key));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([child, item]) => [child, rewrite(item, blocks, docs, child)]));
  }
  return value;
}

/** A stable 53-bit hash (cyrb53) of a document's block IDs, text and image hashes. */
function fingerprint(blocks: ContentBlock[]): string {
  const text = blocks.map((block) => `${block.id}\u0000${block.content}\u0000${block.image?.sha256 ?? ""}`).join("\u0001");
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ code, 2654435761);
    h2 = Math.imul(h2 ^ code, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
}
