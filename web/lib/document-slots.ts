/**
 * Where several files picked or dropped together go in a document collection.
 *
 * A collection is a tool whose documents are identified by name rather than by role, so any
 * file can take any slot. The first file takes the slot it was dropped on, the rest fill the
 * empty slots in order, and whatever is left needs new slots. A file the tool cannot read is
 * refused, and so is one whose name another held file already has: the server identifies a
 * document by its filename stem and refuses a collection holding two, so letting the second
 * in would only defer the error to the end of the upload.
 */

import { isSupportedDocument } from "./document-formats.ts";

/** The server's document identity: the filename without its last extension. */
export function documentIdentity(filename: string): string {
  return filename.replace(/\.[^.]*$/, "");
}

export type FilePlacement = {
  /** Files for slots that already exist, keyed by slot id. */
  placed: Record<string, File>;
  /** Files that need a new slot each, in the order they were picked. */
  overflow: File[];
  unsupported: string[];
  repeated: string[];
};

export function placeFiles({ slotId, picked, slotIds, held, suffixes }: {
  /** The slot the files were picked or dropped on. */
  slotId: string;
  picked: readonly File[];
  /** Every slot, in display order. */
  slotIds: readonly string[];
  /** Files already held, keyed by slot id. */
  held: Readonly<Record<string, File>>;
  suffixes: readonly string[];
}): FilePlacement {
  const unsupported: string[] = [];
  const repeated: string[] = [];
  // The slot being filled gives up its file, so its old name is no longer taken.
  const taken = new Set(
    Object.entries(held)
      .filter(([id]) => id !== slotId)
      .map(([, file]) => documentIdentity(file.name)),
  );
  const accepted: File[] = [];
  for (const file of picked) {
    if (!isSupportedDocument(file.name, suffixes)) {
      unsupported.push(file.name);
      continue;
    }
    const identity = documentIdentity(file.name);
    if (taken.has(identity)) {
      repeated.push(file.name);
      continue;
    }
    taken.add(identity);
    accepted.push(file);
  }
  const targets = [slotId, ...slotIds.filter((id) => id !== slotId && !held[id])];
  const placed: Record<string, File> = {};
  accepted.slice(0, targets.length).forEach((file, index) => {
    placed[targets[index]] = file;
  });
  return { placed, overflow: accepted.slice(targets.length), unsupported, repeated };
}
