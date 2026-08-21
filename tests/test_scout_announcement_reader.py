"""Turning an announcement's prose into the record the landscape groups by.

Every other source arrives structured: an adapter maps provider fields and the record is
already built. A press release is prose, so something has to read the program name out of
it, and that something cannot be the adapter - Searcher fetches, Scout interprets.

The reading is narrow on purpose. A development record may not infer a missing sponsor,
phase or status, so this stage asks for them and accepts blank. The only required field is
the program name, and an announcement naming none yields no record: a pipeline is not a
program, and a quarter is not a program.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.stages.announcement_reader import (
    AnnouncementReading,
    read_announcements,
)
from services.searcher import DevelopmentRecord, Finding


class _Client:
    def __init__(self, *payloads: dict | None) -> None:
        self.payloads = list(payloads)
        self.calls: list[str] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        self.calls.append(user_message)
        payload = self.payloads.pop(0) if self.payloads else None
        return {} if payload is None else dict(payload)


def _announcement(url: str = "https://news/1", excerpt: str = "Merck said V940 met its endpoint.") -> Finding:
    return Finding(
        url=url,
        title="Merck announces results",
        query="melanoma vaccine phase 3 trial results",
        retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        published_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
        excerpt=excerpt,
    )


class NamedProgramTests(unittest.TestCase):
    def test_a_named_program_becomes_an_announcement_record(self) -> None:
        finding = _announcement()
        reading = read_announcements(
            [finding],
            _Client(
                {
                    "names_program": "yes",
                    "program_name": "V940",
                    "sponsor": "Merck",
                    "phase": "Phase 3",
                    "status": "",
                    "reason": "Names the candidate.",
                }
            ),
        )
        self.assertEqual((reading.read, reading.named), (1, 1))
        (record,) = finding.development_records
        self.assertEqual(record.program_name, "V940")
        self.assertEqual(record.record_type, "announcement")
        self.assertEqual(record.sponsor, "Merck")
        self.assertEqual(record.phase, "Phase 3")

    def test_the_program_name_is_the_only_field_required(self) -> None:
        """A press release naming only a candidate is still a usable row."""
        finding = _announcement()
        read_announcements(
            [finding],
            _Client(
                {
                    "names_program": "yes",
                    "program_name": "V940",
                    "sponsor": "",
                    "phase": "",
                    "status": "",
                    "reason": "x",
                }
            ),
        )
        (record,) = finding.development_records
        self.assertEqual((record.sponsor, record.phase, record.status), ("", "", ""))

    def test_the_announcement_url_is_its_record_id(self) -> None:
        """There is no provider record ID, and a row with no identity cannot be opened."""
        finding = _announcement()
        read_announcements(
            [finding],
            _Client({"names_program": "yes", "program_name": "V940", "sponsor": "", "phase": "", "status": "", "reason": "x"}),
        )
        self.assertEqual(finding.development_records[0].record_id, finding.url)

    def test_it_reaches_the_landscape(self) -> None:
        """The point of the record: the projection reads it and knows nothing of prose."""
        from services.scout.models import PROGRAM_SCOPE_KEY
        from services.scout.projections import build_development_landscape

        finding = _announcement()
        read_announcements(
            [finding],
            _Client({"names_program": "yes", "program_name": "V940", "sponsor": "Merck", "phase": "", "status": "", "reason": "x"}),
        )
        (program,) = build_development_landscape({PROGRAM_SCOPE_KEY: [finding]})
        self.assertEqual(program.name, "V940")
        self.assertEqual(program.record_types, ["announcement"])


class NoProgramTests(unittest.TestCase):
    def test_an_announcement_naming_no_program_yields_nothing(self) -> None:
        """The common and correct answer. A pipeline is not a program."""
        finding = _announcement(excerpt="Merck reports third-quarter results; oncology pipeline advancing.")
        reading = read_announcements(
            [finding],
            _Client({"names_program": "no", "program_name": "", "sponsor": "", "phase": "", "status": "", "reason": "A quarter."}),
        )
        self.assertEqual((reading.read, reading.named, reading.unnamed), (1, 0, 1))
        self.assertEqual(finding.development_records, [])

    def test_a_claimed_program_with_no_name_is_refused(self) -> None:
        finding = _announcement()
        reading = read_announcements(
            [finding],
            _Client({"names_program": "yes", "program_name": "  ", "sponsor": "", "phase": "", "status": "", "reason": "x"}),
        )
        self.assertEqual((reading.read, reading.named), (1, 0))
        self.assertEqual(finding.development_records, [])

    def test_an_unreadable_reply_names_nothing(self) -> None:
        finding = _announcement()
        reading = read_announcements([finding], _Client(None))
        self.assertEqual((reading.read, reading.named), (1, 0))


class SkipTests(unittest.TestCase):
    def test_a_finding_that_already_carries_a_record_is_not_reread(self) -> None:
        """Re-reading prose would produce a weaker copy of a fact a provider stated."""
        finding = _announcement()
        finding.development_records.append(
            DevelopmentRecord(program_name="V940", record_type="clinical_trial")
        )
        client = _Client({"names_program": "yes", "program_name": "other", "sponsor": "", "phase": "", "status": "", "reason": "x"})
        reading = read_announcements([finding], client)
        self.assertEqual(client.calls, [])
        self.assertEqual((reading.read, reading.named), (0, 0))
        self.assertEqual(len(finding.development_records), 1)

    def test_a_finding_with_no_text_is_not_read(self) -> None:
        finding = _announcement(excerpt="")
        client = _Client({"names_program": "yes", "program_name": "V940", "sponsor": "", "phase": "", "status": "", "reason": "x"})
        self.assertEqual(read_announcements([finding], client).read, 0)
        self.assertEqual(client.calls, [])

    def test_no_client_still_reports_what_was_retrieved(self) -> None:
        """So a run without a provider does not report zero announcements retrieved."""
        reading = read_announcements([_announcement()], None)
        self.assertEqual((reading.read, reading.named), (1, 0))


class ReadingTests(unittest.TestCase):
    def test_unnamed_never_goes_negative(self) -> None:
        self.assertEqual(AnnouncementReading(read=2, named=5).unnamed, 0)

    def test_the_pair_distinguishes_a_weak_reading_from_a_quiet_week(self) -> None:
        """The reason both numbers are reported rather than only the useful one."""
        weak = AnnouncementReading(read=18, named=4)
        quiet = AnnouncementReading(read=4, named=4)
        self.assertEqual((weak.named, quiet.named), (4, 4))
        self.assertNotEqual(weak.unnamed, quiet.unnamed)


if __name__ == "__main__":
    unittest.main()
