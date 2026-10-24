"""One read over a finished result: what it amounts to, and where to look first.

The caller hands over every finding the result holds, in one shape every tool maps into,
and gets back a short summary and a few points. Each point names the findings it is about
by ID, drawn from a closed list of the result's own IDs, so a point is a pointer at the
result and never a copy of it: the reader opens the findings the point names, with the
names and verdicts the tool's own page gives them.

The order and selection are the model's, and the card says so. What stays authoritative is
the tool's own result below it, which this read never edits, re-ranks or overturns.

Nothing here is stored. The read is derived when a result is opened, so it improves with the
prompt and needs no saved-result migration.

Agnostic by construction: no tool name, no document type and no indication appears in the
prompt. The caller supplies the authority sentence its tool already publishes, one focus
sentence for what to raise first, the context tags the result carries, and its findings.
A fifth tool is served by this file unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from shared.ai import Effort, ModelTask, Verbosity, request_validated
from shared.references import reference_array
from shared.schemas import non_empty_text
from shared.vocabulary import search_term

#: Most points a reader is offered. The tool's sections are the full result; this is where
#: to start, and a list long enough to scroll competes with them instead of leading into them.
MAX_POINTS = 5

#: Longest summary, in words.
MAX_SUMMARY_WORDS = 110

#: Longest the findings may be inside the prompt, in characters.
#:
#: Refused rather than truncated: a model handed part of a result would summarise the part
#: and present it as the whole.
MAX_FINDINGS_CHARACTERS = 200_000

#: One reading of the whole result: what it amounts to is a statement about the set of
#: findings, the case the one-item-per-request rule exempts.
RESULTS_PER_REQUEST = 1
#: The reasoning tier: choosing what a reader should see first is a judgement over every
#: finding, and it is the opening panel of every tool that judges a document.
TASK: ModelTask = "reasoning"
#: Low: the findings already carry the tool's verdicts, so the reading selects and
#: orders rather than re-deriving them, and it is read on every page open, where latency
#: is the reader's. Higher effort spent its budget reasoning over 50k-token inputs.
EFFORT: Effort = "low"
#: The answer is ~110 words and five short points; the rest is reasoning room, so a long
#: result is not cut off at the 2000 this used to be, which surfaced as a 502 on the card.
MAX_TOKENS = 8000


class PriorityRequestTooLarge(ValueError):
    """The result holds more than one read can honestly cover."""


class LLMClientProtocol(Protocol):
    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        trailing_text: str = "",
        task: ModelTask = "reasoning",
        effort: Effort | None = None,
        verbosity: Verbosity | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True)
class PriorityFinding:
    """One thing the result judged, as the tool's own page names it."""

    id: str
    #: What it is about: a rubric unit, a requirement, a field, a question.
    subject: str
    #: Where it sits in the tool's own structure: a section, a comparison, a discipline.
    group: str = ""
    #: The tool's verdicts on it, each in the tool's own words. Code-assigned.
    verdicts: tuple[str, ...] = ()
    #: Sentences the tool's model wrote about it.
    statements: tuple[str, ...] = ()
    #: Facts code derived about it, kept apart so they are never read as a model's.
    notes: tuple[str, ...] = ()
    #: The document's own words, where the finding is about something the document states.
    quote: str = ""


@dataclass(frozen=True)
class PriorityRequest:
    """Everything the read needs, all of it already published by the caller."""

    #: The tool's catalog sentence: what it reads, and the authority it judges against.
    authority: str
    #: What this tool's reader needs first, in one sentence.
    focus: str
    findings: tuple[PriorityFinding, ...]
    org: str = ""
    intervention_class: str = ""
    indication: str = ""


@dataclass
class PriorityPoint:
    title: str
    statement: str
    finding_ids: list[str] = field(default_factory=list)


@dataclass
class PriorityReading:
    summary: str
    points: list[PriorityPoint] = field(default_factory=list)


def build_system_prompt() -> str:
    """The one prompt, for every tool. Names none of them."""
    return f"""You are reading every finding of one finished analysis, so that a reader knows what it amounts to and where to look first.

Write two things.

`summary`: at most {MAX_SUMMARY_WORDS} words, one or two short paragraphs.
- Say what the result amounts to as a whole: what kind of problem recurs, where it
  concentrates, and what is in good shape.
- Name the authority the tool judged against. A sentence saying a document "has gaps"
  without saying what it was held to is the sentence most likely to be repeated wrongly.
- No identifiers and no citations; it is read on screen above the points.

`points`: at most {MAX_POINTS}, most useful first, and fewer is fine.
- Each point is one thing worth a reader's attention first, following the focus you are
  given. A point may gather several findings when they are one problem.
- `title`: a short headline in plain words.
- `statement`: one or two sentences saying what it is and why it matters, from the findings.
- `finding_ids`: the IDs of the findings the point is about, drawn from those supplied.
- Return no points when nothing in the findings needs attention.

Reading the findings:
- `verdict` lines are the tool's own judgements, assigned by its pipeline. `says` lines are
  sentences its model wrote. `note` lines are facts code derived. `document` lines are the
  document's own words.
- Never overturn, soften or contradict a verdict. Where you think one is wrong, say nothing.
- Do not score, total or grade anything, and do not invent a severity the verdicts do not carry.
- Do not use your own knowledge of the field to add a finding. The domain is context for
  reading, never a source: it tells you which findings are consequential, and licenses no
  claim the findings do not make."""


def _finding_text(finding: PriorityFinding) -> str:
    lines = [f"[{finding.id}] {finding.subject}"]
    if finding.group:
        lines.append(f"  in: {finding.group}")
    lines.extend(f"  verdict: {verdict}" for verdict in finding.verdicts)
    if finding.quote:
        lines.append(f"  document: {finding.quote}")
    lines.extend(f"  says: {statement}" for statement in finding.statements)
    lines.extend(f"  note: {note}" for note in finding.notes)
    return "\n".join(lines)


def build_user_message(request: PriorityRequest) -> str:
    """Context, focus, then every finding, each part labelled for what it holds."""
    context = [f"The tool: {request.authority}"]
    domain = " · ".join(
        part
        for part in (
            request.org,
            search_term(request.intervention_class),
            search_term(request.indication),
        )
        if part
    )
    if domain:
        context.append(f"Run context: {domain}")
    if request.focus:
        context.append(f"What to raise first: {request.focus}")

    findings = "\n\n".join(_finding_text(finding) for finding in request.findings)
    if len(findings) > MAX_FINDINGS_CHARACTERS:
        raise PriorityRequestTooLarge(
            f"this result holds {len(request.findings)} findings, more than one read can cover"
        )
    return "\n\n".join([
        "\n".join(context),
        f"Findings ({len(request.findings)}):\n{findings or '(none)'}",
    ])


#: Text that says something. The parser normalises whitespace and refuses what is left
#: empty, so the schema refuses whitespace too rather than permit a reply it rejects.
_TEXT = non_empty_text()


def reading_schema(finding_ids: list[str]) -> dict[str, Any]:
    """The closed shape. Every constraint the parser enforces is stated here."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "points"],
        "properties": {
            "summary": _TEXT,
            "points": {
                "type": "array",
                "maxItems": MAX_POINTS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "statement", "finding_ids"],
                    "properties": {
                        "title": _TEXT,
                        "statement": _TEXT,
                        "finding_ids": {**reference_array(finding_ids), "minItems": 1},
                    },
                },
            },
        },
    }


def read_priorities(
    request: PriorityRequest,
    *,
    llm_client: LLMClientProtocol,
) -> PriorityReading:
    """One summary and up to `MAX_POINTS` points, validated against the result's IDs.

    An answer that breaks the contract is asked for once more with the reason; one that
    stays broken, is cut off or is refused raises ``ModelResponseError`` with its code.
    """
    if not request.findings:
        raise ValueError("a result with no findings has nothing to read")
    finding_ids = list(dict.fromkeys(finding.id for finding in request.findings))
    known = frozenset(finding_ids)
    return request_validated(
        llm_client,
        build_system_prompt(),
        build_user_message(request),
        schema_name="priority_reading",
        schema=reading_schema(finding_ids),
        max_tokens=MAX_TOKENS,
        task=TASK,
        effort=EFFORT,
        parse=lambda payload: _parse_payload(payload, known),
        failure="The priority reading could not be produced",
    )


def _parse_payload(payload: object, known: frozenset[str]) -> PriorityReading:
    """Validate one reading, raising ``ValueError`` naming what is wrong."""
    if not isinstance(payload, dict):
        raise ValueError("model returned no priority reading")
    summary = _prose(payload.get("summary"))
    if not summary:
        raise ValueError("a summary that says nothing is worse than none")
    points: list[PriorityPoint] = []
    for entry in payload.get("points") or []:
        if not isinstance(entry, dict):
            raise ValueError("a point must be an object")
        title = " ".join(str(entry.get("title") or "").split())
        statement = _prose(entry.get("statement"))
        finding_ids = list(dict.fromkeys(str(item) for item in entry.get("finding_ids") or []))
        # The schema already closes all three; a reply that breaks them is a broken reply,
        # refused whole rather than shown as a point that opens nothing.
        if not title or not statement or not finding_ids:
            raise ValueError("a point needs a title, a statement and at least one finding")
        unknown = [item for item in finding_ids if item not in known]
        if unknown:
            raise ValueError(f"a point names findings this result does not hold: {unknown}")
        points.append(PriorityPoint(title=title, statement=statement, finding_ids=finding_ids))
    if len(points) > MAX_POINTS:
        raise ValueError(f"at most {MAX_POINTS} points")
    return PriorityReading(summary=summary, points=points)


def _prose(value: object) -> str:
    """Whitespace normalised inside each paragraph, the break between paragraphs kept."""
    paragraphs = (" ".join(part.split()) for part in str(value or "").split("\n\n"))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
