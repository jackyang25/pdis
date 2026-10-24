"""A projection lists each source once, with every lane that retrieved it."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.projections import build_development_landscape
from services.searcher import DevelopmentRecord, Finding

URL = "https://clinicaltrials.gov/study/NCT03596801"


def _finding(source: str, query: str) -> Finding:
    return Finding(
        url=URL,
        title="Trial",
        query=query,
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source=source,
        development_records=[DevelopmentRecord(
            program_name="V940", record_type="clinical_trial", record_id="NCT03596801",
        )],
    )


class LandscapeFindingIdentityTests(unittest.TestCase):
    def test_one_url_from_two_lanes_is_one_finding_keeping_both_lanes(self) -> None:
        web = _finding("web", "v940 trial")
        registry = _finding("clinicaltrials", "V940")

        [program] = build_development_landscape({
            "vaccine.efficacy": [web],
            "vaccine.safety": [registry],
        })

        self.assertEqual([finding.url for finding in program.supporting_findings], [URL])
        [merged] = program.supporting_findings
        self.assertEqual(merged.source_lanes, ["web", "clinicaltrials"])
        self.assertEqual(set(merged.queries), {"v940 trial", "V940"})

    def test_merging_leaves_each_fields_own_finding_untouched(self) -> None:
        web = _finding("web", "v940 trial")
        registry = _finding("clinicaltrials", "V940")

        build_development_landscape({"a": [web], "b": [registry]})

        self.assertEqual(web.source_lanes, ["web"])
        self.assertEqual(registry.source_lanes, ["clinicaltrials"])


if __name__ == "__main__":
    unittest.main()
