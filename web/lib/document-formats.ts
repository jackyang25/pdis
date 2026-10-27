/**
 * The one web-side statement of which document formats PDIS accepts.
 *
 * `services/chunker/formats.py` owns the set, and every tool and Ask accepts all of it:
 * DOCX, PPTX and XLSX with their structure, PDF as page text. This mirrors that set for
 * the browser, and `document-formats.test.ts` fails if the two stop matching.
 *
 * Upload controls derive both their `accept` attribute and their visible hint
 * from here. Restating the extensions in a component lets a control advertise
 * one set while accepting another.
 */
export const DOCUMENT_SUFFIXES = [".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".pdf"] as const;

export type DocumentFormats = {
  suffixes: readonly string[];
  accept: string;
  hint: string;
  note?: string;
};

function documentFormats(suffixes: readonly string[]): DocumentFormats {
  return {
    suffixes, accept: suffixes.join(","),
    hint: suffixes.map((suffix) => suffix.slice(1).toUpperCase()).join(", "),
  };
}

export const DOCUMENT_FORMATS: DocumentFormats = {
  ...documentFormats(DOCUMENT_SUFFIXES),
  note: "Word, PowerPoint and Excel files keep their structure (older DOC, PPT and XLS files are converted first), so findings point to the exact passage, slide or row. PDFs are read as page text with an image of each page: tables and columns may be out of order and findings point to the page, so upload the original file when you have it. PDFs must be unlocked, up to 20 MB and 200 pages, with selectable text on every page; scans are not supported. Workbooks may be up to 20 MB and 2,000 filled rows.",
};

/** Reader-facing format list, e.g. `DOCX, DOC, PPTX, PPT, XLSX, XLS, PDF`. */
export const DOCUMENT_FORMAT_HINT = DOCUMENT_FORMATS.hint;

/**
 * Media-type prefixes a conversation attachment may add on top of documents.
 *
 * `services/chunker/pipeline.py` owns this set. Attachments add images to the document
 * formats every tool accepts.
 */
export const ATTACHMENT_MEDIA_PREFIXES = ["image/"] as const;

/** Value for an attachment `<input type="file">` accept attribute. */
export const ATTACHMENT_ACCEPT = [
  ...DOCUMENT_SUFFIXES,
  ...ATTACHMENT_MEDIA_PREFIXES.map((prefix) => `${prefix}*`),
].join(",");

/** Reader-facing attachment list, e.g. `DOCX, DOC, PPTX, PPT, XLSX, XLS, PDF, or image files`. */
export const ATTACHMENT_FORMAT_HINT = `${DOCUMENT_FORMAT_HINT}, or image files`;

/** How many files one conversation may attach. */
export const MAX_ATTACHMENTS = 5;

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
