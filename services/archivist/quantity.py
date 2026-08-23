"""Read a number out of the document's own words, in code, or read nothing.

`stated` is what the document said. `magnitude` and `unit` exist so that identical
answers sort and group, and they are parsed here rather than asked of a model, because a
number a model retyped is a number that can silently differ from the document's.

Two rules make this narrow on purpose.

**It never converts.** "2 years" parses as (2, "years") and not as 24 months. Canonicalising
would make the two documents group, and it would also put a number in the corpus that
neither document contains, on an axis nobody declared - a month is 28 to 31 days, so the
conversion is not even exact. The document's words stay authoritative; grouping happens
within a unit, which is what a reviewer expects when they read the column.

**It fails closed.** Anything ambiguous parses as nothing, and nothing is a perfectly good
answer: `stated` still carries the full value, and the row still counts. A range ("24 to
36 months") has no single magnitude, and inventing one by taking an end would be a claim
the document did not make. Roughly half of real values parse, and the half that does not
is mostly ranges and compound presentations.

The parse is driven by the *declared* quantity kind of the column, never guessed from the
text. "24 months" under a shelf life is a duration; the same characters under a price
are not, and a parser that sniffed for units would happily read a storage temperature as
a price.
"""

from __future__ import annotations

import re

#: Unit words per quantity kind, mapped to the name recorded on the record.
#:
#: Plural forms collapse ("month" and "months" both record "months") because the choice
#: between them is grammar, not measurement, and two spellings would split a group in
#: half. That is normalising the *name* of the unit, which is not the same as converting
#: the quantity it measures.
UNIT_WORDS: dict[str, dict[str, str]] = {
    "duration": {
        "hour": "hours", "hours": "hours",
        "day": "days", "days": "days",
        "week": "weeks", "weeks": "weeks",
        "month": "months", "months": "months",
        "year": "years", "years": "years",
    },
    "count": {
        "dose": "doses", "doses": "doses",
        "visit": "visits", "visits": "visits",
        "injection": "injections", "injections": "injections",
        "administration": "administrations", "administrations": "administrations",
    },
    "temperature": {
        "c": "celsius", "°c": "celsius", "celsius": "celsius", "centigrade": "celsius",
    },
}

#: Counts are routinely written as words in these documents ("a two-dose schedule"), and
#: a schedule that parses only when written in digits would split the column by prose
#: style. Limited to the range a dosing schedule actually uses.
NUMBER_WORDS = {
    "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "eleven": 11.0, "twelve": 12.0,
}

_NUMBER = r"(?:\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")"
_RANGE_JOIN = r"(?:\s*(?:-|–|—|to|and|or)\s*)"
#: Currency symbols and codes accepted before or after the number.
_CURRENCY = re.compile(
    r"(?:(?P<low>\d+(?:\.\d+)?)" + _RANGE_JOIN + r")?"
    r"(?:(?:US)?\$|USD\s*)\s*(?P<value>\d+(?:\.\d+)?)"
    r"|"
    r"(?:(?P<low2>\d+(?:\.\d+)?)" + _RANGE_JOIN + r")?"
    r"(?P<value2>\d+(?:\.\d+)?)\s*(?:USD|US\s*dollars?)",
    re.IGNORECASE,
)


def parse_quantity(stated: str, kind: str) -> tuple[float | None, str]:
    """The magnitude and unit of `stated`, if the declared kind admits exactly one.

    Returns `(None, "")` for a column that declares no quantity, for a range, for a value
    carrying two comparable quantities, and for anything else that does not resolve to one
    number and one unit.
    """
    text = " ".join((stated or "").split())
    if not text or not kind:
        return None, ""
    if kind == "currency":
        return _parse_currency(text)
    words = UNIT_WORDS.get(kind)
    if not words:
        return None, ""
    return _parse_with_unit(text, words)


def _parse_with_unit(text: str, words: dict[str, str]) -> tuple[float | None, str]:
    pattern = re.compile(
        r"(?P<low>" + _NUMBER + r")?" + r"(?(low)" + _RANGE_JOIN + r")"
        r"(?P<value>" + _NUMBER + r")"
        r"[\s\-–]*"
        r"(?P<unit>" + "|".join(sorted(words, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    matches = [match for match in pattern.finditer(text)]
    if len(matches) != 1:
        # Zero: the value names no quantity of this kind. More than one: the value carries
        # two, as "24 months at 2-8C" would under a duration column if C were a duration -
        # either way there is no single magnitude to record.
        return None, ""
    match = matches[0]
    if match.group("low"):
        return None, ""
    value = _number(match.group("value"))
    if value is None:
        return None, ""
    return value, words[match.group("unit").lower()]


def _parse_currency(text: str) -> tuple[float | None, str]:
    matches = list(_CURRENCY.finditer(text))
    if len(matches) != 1:
        return None, ""
    match = matches[0]
    if match.group("low") or match.group("low2"):
        return None, ""
    raw = match.group("value") or match.group("value2")
    value = _number(raw)
    if value is None:
        return None, ""
    # Only USD is recognised, so the unit is not read from the text. A profile priced in
    # another currency parses as nothing rather than as dollars.
    return value, "usd"


def _number(token: str) -> float | None:
    token = token.strip().lower()
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    try:
        return float(token)
    except ValueError:
        return None
