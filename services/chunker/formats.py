"""The document formats PDIS reads, declared once for every tool and Ask.

One set, not one per tool: every tool judges documents, and a format one tool accepts and
another refuses makes the tools read different kinds of evidence. DOCX, PPTX and XLSX
declare their structure and produce exact, traceable passages. PDF is the one less precise
mode - page text and a page image, never inferred headings or cells - and its limit travels
on every passage it produces (`pdf_text_layout`), so each tool states it the same way.

The legacy Office formats are not read on their own: each converts to its modern format and
is read by that format's one reader, so an old file yields the passages its modern version
would. Its passages still name the file it came from.
"""

from typing import Literal, get_args

#: Each legacy Office format and the modern format it converts to before reading.
LEGACY_SUFFIXES: dict[str, str] = {".doc": ".docx", ".ppt": ".pptx", ".xls": ".xlsx"}

DOCUMENT_SUFFIXES = frozenset({".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".pdf"})

#: The file a block was parsed from, recorded by the parser that read it. Carried on
#: every block so a reader can say which kind of file a passage came from without
#: working it out from what else the block happens to hold. `image` is a standalone
#: image attachment, which has no document around it.
SourceFormat = Literal["docx", "doc", "pptx", "ppt", "xlsx", "xls", "pdf", "image"]
SOURCE_FORMATS: frozenset[str] = frozenset(get_args(SourceFormat))

SOURCE_FORMAT_BY_SUFFIX: dict[str, SourceFormat] = {
    ".docx": "docx",
    ".doc": "doc",
    ".pptx": "pptx",
    ".ppt": "ppt",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".pdf": "pdf",
}
