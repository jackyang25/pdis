"""The document formats PDIS reads, declared once for every tool and Ask.

One set, not one per tool: every tool judges documents, and a format one tool accepts and
another refuses makes the tools read different kinds of evidence. DOCX, PPTX and XLSX
declare their structure and produce exact, traceable passages. PDF is the one less precise
mode - page text and a page image, never inferred headings or cells - and its limit travels
on every passage it produces (`pdf_text_layout`), so each tool states it the same way.
Legacy `.xls` workbooks are converted to XLSX and read as one.
"""

from typing import Literal, get_args

DOCUMENT_SUFFIXES = frozenset({".docx", ".pptx", ".xlsx", ".xls", ".pdf"})

#: The file a block was parsed from, recorded by the parser that read it. Carried on
#: every block so a reader can say which kind of file a passage came from without
#: working it out from what else the block happens to hold. `image` is a standalone
#: image attachment, which has no document around it.
SourceFormat = Literal["docx", "pptx", "xlsx", "xls", "pdf", "image"]
SOURCE_FORMATS: frozenset[str] = frozenset(get_args(SourceFormat))

SOURCE_FORMAT_BY_SUFFIX: dict[str, SourceFormat] = {
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".pdf": "pdf",
}
