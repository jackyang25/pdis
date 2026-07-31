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

/** Whether a picked file carries a supported document extension. */
export function isSupportedDocument(name: string): boolean {
  const lowered = name.toLowerCase();
  return DOCUMENT_SUFFIXES.some((suffix) => lowered.endsWith(suffix));
}
