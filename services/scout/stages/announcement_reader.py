"""Read a development program out of an announcement's prose.

Retrieval is deterministic by design: every adapter maps provider fields, so a registry
finding arrives with its `DevelopmentRecord` already built. An announcement arrives as
prose, because that is all a press release is, and the landscape groups by program name.
So something has to read the name, and it cannot be the adapter - Searcher fetches,
Scout interprets, and putting a model call inside an adapter would erase that line.

The reading is deliberately narrow. A development record may not infer a missing sponsor,
phase or status, so this stage asks for them and accepts blank. The one required field is
the program name, and an announcement that names no program yields no record: "Merck
reports third-quarter earnings, oncology pipeline advancing" is a real announcement and
not competitive intelligence about a program.

What it does *not* do is judge. Whether the named program competes with the document's
target is `projection_classifier`'s decision, from the same record every other source
produces. This stage only turns prose into that shape.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from services.searcher import DevelopmentRecord, Finding

from shared.ai import RECORDABLE_FAILURES, Effort, FailureCode, ModelTask, failure_code
from shared.batching import map_ordered

from ..ai import request_validated
from ..ai_contracts import announcement_record
from ..models import LLMClientProtocol

logger = logging.getLogger(__name__)

#: Reasoning counts against the budget, so it is sized for the thinking, not the reply.
DEFAULT_MAX_TOKENS = 8000
#: One announcement per request. A per-item decision, so the rule in `batching.py`
#: applies: two announcements in one prompt influence each other's reading.
ANNOUNCEMENTS_PER_REQUEST = 1
#: The fast tier at low effort: reading a name out of a press release is transcription,
#: and the landscape row it produces says it rests on an announcement.
TASK: ModelTask = "fast"
EFFORT: Effort = "low"
READER_WORKERS = 8


@dataclass(frozen=True)
class AnnouncementReading:
    """How many announcements were read, how many named a program, and how many failed.

    Reported rather than inferred from the landscape, because a program that named
    nothing leaves no trace there. Without the pair, a weak reading and a quiet week look
    identical - the same failure the lane report fixed one layer down. A reading that
    failed is counted apart from one that named nothing: the first is the pipeline's
    failure, the second is the model's answer about the text.
    """

    read: int = 0
    named: int = 0
    failed: int = 0
    #: The failures by code, so a refusal and a provider outage read differently.
    failed_by_code: dict[str, int] = field(default_factory=dict)

    @property
    def unnamed(self) -> int:
        return max(self.read - self.named - self.failed, 0)


def build_system_prompt() -> str:
    return """You are reading one announcement to decide which development program it is about.

`names_program`: "yes" only if the text names a specific product, candidate or program -
a code name, a brand name, or an INN. "no" for an announcement about a company, a
quarter, a pipeline in general, a therapeutic area, or a partnership with no named asset.
That answer is common and correct; a pipeline is not a program.

`program_name`: the name as the announcement writes it. Prefer the development code or
product name over a description of it. Empty when `names_program` is "no".

`sponsor`, `phase`, `status`: only when the text states them for this program. Leave any
of them empty otherwise. Do not derive a phase from the kind of result described, do not
infer a sponsor from who issued the announcement, and do not convert a claim of success
into a status. An empty field is a fact about the announcement; a filled one that the
text does not support is a fact about nothing.

You are not judging whether this program competes with anything, and you are not
assessing whether its claims are true. You are naming what it is about."""


def _user_message(finding: Finding) -> str:
    return (
        f"title: {finding.title}\n"
        f"url: {finding.url}\n"
        f"published: {finding.published_at.date().isoformat() if finding.published_at else '(not stated)'}\n\n"
        f"text:\n{finding.excerpt or '(no text was captured)'}\n\n"
        "Decide now."
    )


def read_announcements(
    findings: list[Finding],
    llm_client: LLMClientProtocol | None,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    progress: Callable[[int, int], None] | None = None,
) -> AnnouncementReading:
    """Attach an `announcement` record to every finding that names a program.

    Mutates the findings, which is how a record reaches the landscape: that projection
    reads `finding.development_records` and knows nothing about where they came from.

    Findings that already carry records are skipped. A program-scope query set may target
    a registry one day, and those findings arrive structured; re-reading their prose would
    produce a second, weaker copy of a fact the provider already stated.
    """
    candidates = [
        finding
        for finding in findings
        if not finding.development_records and (finding.excerpt or "").strip()
    ]
    if not candidates or llm_client is None:
        return AnnouncementReading(read=len(candidates))

    def read_one(finding: Finding) -> bool | FailureCode:
        """Whether it named a program, or the code of the failure that stopped it."""
        try:
            return _read_one(finding, llm_client, max_tokens=max_tokens)
        except RECORDABLE_FAILURES as exc:
            logger.warning("Announcement unreadable after retry: %s (%s)", finding.url, exc)
            return failure_code(exc)

    if progress:
        progress(0, len(candidates))
    outcomes = map_ordered(candidates, read_one, workers=READER_WORKERS, on_progress=progress)
    failures = Counter(outcome for outcome in outcomes if isinstance(outcome, str))
    reading = AnnouncementReading(
        read=len(candidates),
        named=sum(outcome is True for outcome in outcomes),
        failed=sum(failures.values()),
        failed_by_code=dict(sorted(failures.items())),
    )
    if reading.unnamed or reading.failed:
        logger.info(
            "Announcements read: %d named a program, %d named none, %d failed",
            reading.named,
            reading.unnamed,
            reading.failed,
        )
    return reading


def _read_one(
    finding: Finding,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> bool:
    def parse(parsed: object) -> tuple[str, dict] | None:
        if not isinstance(parsed, dict):
            raise ValueError("no structured reading was returned")
        names_program = str(parsed.get("names_program", "")).strip().lower()
        if names_program not in {"yes", "no"}:
            raise ValueError('names_program must be "yes" or "no"')
        if names_program == "no":
            return None
        name = " ".join(str(parsed.get("program_name") or "").split())
        if not name:
            raise ValueError('names_program is "yes" but program_name is empty')
        return name, parsed

    reading = request_validated(
        llm_client,
        announcement_record(),
        build_system_prompt(),
        _user_message(finding),
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
        parse=parse,
        failure=f"Announcement reading failed for {finding.url}",
    )
    if reading is None:
        return False
    name, parsed = reading
    finding.development_records.append(
        DevelopmentRecord(
            program_name=name,
            record_type="announcement",
            # The announcement's own URL is its identity. There is no provider record ID.
            record_id=finding.url,
            sponsor=" ".join(str(parsed.get("sponsor") or "").split()),
            phase=" ".join(str(parsed.get("phase") or "").split()),
            status=" ".join(str(parsed.get("status") or "").split()),
        )
    )
    return True
