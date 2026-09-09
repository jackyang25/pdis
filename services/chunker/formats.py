"""Input capabilities, separate from document-type taxonomies.

Defaults require declared structure. Text extraction is an explicit opt-in;
adding a parser must not widen every tool's accepted inputs.
"""

DOCUMENT_SUFFIXES = frozenset({".docx", ".pptx"})
TEXT_EXTRACTION_SUFFIXES = DOCUMENT_SUFFIXES | {".pdf"}
