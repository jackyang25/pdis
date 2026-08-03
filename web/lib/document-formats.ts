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

/** Whether a picked file carries a supported document extension. */
export function isSupportedDocument(name: string): boolean {
  const lowered = name.toLowerCase();
  return DOCUMENT_SUFFIXES.some((suffix) => lowered.endsWith(suffix));
}
