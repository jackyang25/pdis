"""Whether a quotation appears in its source, comparing text rather than typesetting.

Shared because two services verify excerpts: Scout, for document targets and the
measurements mapped to them, and Drafter, for what a source says about a variable. A quote
earns its citation by appearing in the source, and the rule for "appears" must be one rule.
"""

from __future__ import annotations

import html


# Characters a word processor renders differently while the words stay the same.
# An excerpt is compared on its text, not on its typesetting: DOCX autocorrect
# produces curly quotes and en dashes that a model retypes as ASCII, and the
# excerpt is then rejected as inexact although it was quoted correctly.
#
# Deliberately NOT unicodedata.normalize("NFKC"): that maps "10²" to "102" and
# "½" to "1/2", which changes a value rather than its rendering and could verify
# an excerpt the document does not contain. Only marks are folded here; digits,
# letters, superscripts, and fractions are left exactly as written.
TYPOGRAPHIC_EQUIVALENCE = {
    # Invisible: line-breaking and joining hints that carry no text.
    0x00AD: None,  # soft hyphen
    0x200B: None,  # zero width space
    0x200C: None,  # zero width non-joiner
    0x200D: None,  # zero width joiner
    0xFEFF: None,  # zero width no-break space
    # Quotation marks.
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'",
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"',
    # Hyphens, dashes, and the minus sign.
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-",
    0x2014: "-", 0x2015: "-", 0x2212: "-",
    # Marks with a settled ASCII spelling. Unlike the folds above this is a
    # judgment that the two spellings mean the same thing, which holds for a
    # comparison operator and is why the set stops here.
    0x2026: "...",
    0x2264: "<=",
    0x2265: ">=",
}


def normalize_quote(value: str) -> str:
    folded = html.unescape(value).translate(TYPOGRAPHIC_EQUIVALENCE)
    return " ".join(folded.split()).casefold()


def quote_in_text(quote: str, source_text: str) -> bool:
    normalized_quote = normalize_quote(quote)
    return bool(normalized_quote) and normalized_quote in normalize_quote(source_text)
