/**
 * The one web-side statement of which document formats PDIS accepts.
 *
 * `services/chunker/pipeline.py` owns the decision — a format qualifies only if
 * it declares its own structure. This mirrors that set for the browser, and
 * `document-formats.test.ts` fails if the two stop matching.
 *
 * Upload controls derive both their `accept` attribute and their visible hint
 * from here. Restating the extensions in a component lets a control advertise
 * one set while accepting another.
 */
export const DOCUMENT_SUFFIXES = [".docx", ".pptx"] as const;

/** Value for an `<input type="file">` accept attribute. */
export const DOCUMENT_ACCEPT = DOCUMENT_SUFFIXES.join(",");

/** Reader-facing format list, e.g. `DOCX, PPTX`. */
export const DOCUMENT_FORMAT_HINT = DOCUMENT_SUFFIXES.map((suffix) =>
  suffix.replace(".", "").toUpperCase(),
).join(", ");

/**
 * Media-type prefixes a conversation attachment may add on top of documents.
 *
 * `services/chunker/pipeline.py` owns this set too. An attachment is read once
 * and discarded rather than analysed, so it may accept a format the analysis
 * path refuses — but never fewer than that path accepts.
 */
export const ATTACHMENT_MEDIA_PREFIXES = ["image/"] as const;

/** Value for an attachment `<input type="file">` accept attribute. */
export const ATTACHMENT_ACCEPT = [
  ...DOCUMENT_SUFFIXES,
  ...ATTACHMENT_MEDIA_PREFIXES.map((prefix) => `${prefix}*`),
].join(",");

/** Reader-facing attachment list, e.g. `DOCX, PPTX, or image files`. */
export const ATTACHMENT_FORMAT_HINT = `${DOCUMENT_FORMAT_HINT}, or image files`;

/**
 * What a clipboard or a drag holds that could be attached, and what won.
 *
 * A clipboard can carry several representations of one copy at once: a table copied
 * from a spreadsheet arrives as plain text, HTML, *and* a picture of itself. Attaching
 * the picture there would quietly replace a paste meant as text, so text wins whenever
 * it is present — which leaves a screenshot, having no text version, free to attach.
 *
 * `textWon` is the reason this returns a pair rather than a list. Dropping the file
 * silently is the only real fault in that rule: a reader who copied a region of a
 * document containing a figure would never learn the figure did not come with it. The
 * caller can say so without the rule changing.
 *
 * Kept beside the accept list because "what may be attached" is one decision, and a
 * paste handler filtering differently from the file picker beside it is two answers to it.
 */
export type AttachablePaste = {
  /** Files to attach. Empty when text won, or when nothing supported was carried. */
  files: File[];
  /** True when supported files were present but text took precedence. */
  textWon: boolean;
};

export function attachablePaste(transfer: DataTransfer | null): AttachablePaste {
  if (!transfer) return { files: [], textWon: false };
  const files = [...transfer.files].filter((file) =>
    isSupportedDocument(file.name)
    || ATTACHMENT_MEDIA_PREFIXES.some((prefix) => file.type.startsWith(prefix)),
  );
  if (transfer.getData("text/plain").trim()) {
    return { files: [], textWon: files.length > 0 };
  }
  return { files, textWon: false };
}

/** Whether a picked file carries a supported document extension. */
export function isSupportedDocument(name: string): boolean {
  const lowered = name.toLowerCase();
  return DOCUMENT_SUFFIXES.some((suffix) => lowered.endsWith(suffix));
}
