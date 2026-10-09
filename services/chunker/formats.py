"""Input capabilities, separate from document-type taxonomies.

Defaults require declared structure. Text extraction is an explicit opt-in;
adding a parser must not widen every tool's accepted inputs.
"""

from typing import Literal, get_args

DOCUMENT_SUFFIXES = frozenset({".docx", ".pptx"})
TEXT_EXTRACTION_SUFFIXES = DOCUMENT_SUFFIXES | {".pdf"}

#: The file a block was parsed from, recorded by the parser that read it. Carried on
#: every block so a reader can say which kind of file a passage came from without
#: working it out from what else the block happens to hold. `image` is a standalone
#: image attachment, which has no document around it.
SourceFormat = Literal["docx", "pptx", "pdf", "image"]
SOURCE_FORMATS: frozenset[str] = frozenset(get_args(SourceFormat))

SOURCE_FORMAT_BY_SUFFIX: dict[str, SourceFormat] = {
    ".docx": "docx",
    ".pptx": "pptx",
    ".pdf": "pdf",
}
