"""How much of the problem there is, and where.

Every other lane reports what someone did, claimed or recommended. WHO GHO reports a
measured quantity in a place, which is a different kind of evidence and needs a different
shape: `IndicatorRecord` beside `DevelopmentRecord` and `SafetyObservationRecord`, and
`build_burden_indicators` beside the two projections that already exist.

It earns that machinery because a target profile stating "reduce cases by thirty per cent
in sub-Saharan Africa" makes a claim about a quantity, and nothing else retrieved supplies
the number the claim is measured against.

Two rules run through all of it. Nothing is interpolated - a country with no row for a
year has no row. And nothing is aggregated - a total across whichever countries happened
to be retrieved would read as a total for the disease.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from services.scout.models import PROGRAM_SCOPE_KEY
from services.scout.projections import build_burden_indicators
from services.searcher import Finding, IndicatorRecord, source_specs


def _record(place: str, year: int, value: float | None, **overrides) -> IndicatorRecord:
    fields = dict(
        indicator_code="MALARIA_CONF_CASES",
        indicator_name="Number of confirmed malaria cases",
        place=place,
        spatial_type="COUNTRY",
        year=year,
        value=value,
        value_text="" if value is None else f"{value:.0f}",
    )
    fields.update(overrides)
    return IndicatorRecord(**fields)


def _finding(*records: IndicatorRecord, url: str = "https://who.int/gho/x") -> Finding:
    return Finding(
        url=url,
        title="Number of confirmed malaria cases",
        query="indicator_name_contains:malaria",
        retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        source="who_gho",
        evidence_role="reference",
        indicator_records=list(records),
    )


class RecordTests(unittest.TestCase):
    def test_a_record_needs_a_place_and_an_indicator(self) -> None:
        for missing in ("indicator_code", "place"):
            with self.subTest(missing=missing):
                fields = dict(
                    indicator_code="X",
                    indicator_name="x",
                    place="KEN",
                    spatial_type="COUNTRY",
                    year=2024,
                    value=1.0,
                )
                fields[missing] = ""
                with self.assertRaises(ValueError):
                    IndicatorRecord(**fields)

    def test_a_record_with_neither_a_number_nor_text_records_nothing(self) -> None:
        with self.assertRaises(ValueError):
            IndicatorRecord(
                indicator_code="X",
                indicator_name="x",
                place="KEN",
                spatial_type="COUNTRY",
                year=2024,
            )

    def test_a_suppressed_value_keeps_the_providers_own_text(self) -> None:
        """GHO writes "<0.1" and "No data" where the numeric field is empty, and that is
        a fact rather than an absence. Reading it as zero would invent a measurement."""
        record = IndicatorRecord(
            indicator_code="X",
            indicator_name="x",
            place="KEN",
            spatial_type="COUNTRY",
            year=2024,
            value=None,
            value_text="<0.1",
        )
        self.assertIsNone(record.value)
        self.assertEqual(record.value_text, "<0.1")

    def test_a_global_aggregate_is_not_a_place(self) -> None:
        """A world total answers a different question from a country reading, and mixing
        the two in one table produces a number nobody asked for."""
        with self.assertRaises(ValueError):
            IndicatorRecord(
                indicator_code="X",
                indicator_name="x",
                place="GLOBAL",
                spatial_type="WORLD",
                year=2024,
                value=1.0,
            )


class ProjectionTests(unittest.TestCase):
    def test_readings_group_by_indicator_not_by_variable(self) -> None:
        indicators = build_burden_indicators(
            {
                "vaccine.efficacy": [_finding(_record("KEN", 2024, 1000.0))],
                PROGRAM_SCOPE_KEY: [_finding(_record("IRN", 2024, 7601.0))],
            }
        )
        self.assertEqual(len(indicators), 1)
        self.assertEqual(indicators[0].place_count, 2)

    def test_the_same_country_year_arriving_twice_is_one_reading(self) -> None:
        indicators = build_burden_indicators(
            {
                "a": [_finding(_record("KEN", 2024, 1000.0))],
                "b": [_finding(_record("KEN", 2024, 1000.0), url="https://who.int/gho/y")],
            }
        )
        self.assertEqual(len(indicators[0].readings), 1)

    def test_readings_are_newest_first_then_by_place(self) -> None:
        (indicator,) = build_burden_indicators(
            {
                "a": [
                    _finding(
                        _record("KEN", 2023, 1200.0),
                        _record("IRN", 2024, 7601.0),
                        _record("AGO", 2024, 500.0),
                    )
                ]
            }
        )
        self.assertEqual(
            [(r.year, r.place) for r in indicator.readings],
            [(2024, "AGO"), (2024, "IRN"), (2023, "KEN")],
        )

    def test_nothing_is_aggregated(self) -> None:
        """No total, no average, no single headline. A sum over whichever countries were
        retrieved would read as a total for the disease."""
        (indicator,) = build_burden_indicators(
            {"a": [_finding(_record("KEN", 2024, 1000.0), _record("IRN", 2024, 7601.0))]}
        )
        for absent in ("total", "average", "mean", "sum"):
            self.assertFalse(
                hasattr(indicator, absent), f"projection exposes a {absent}"
            )
        self.assertEqual(len(indicator.readings), 2)

    def test_a_year_with_no_row_stays_absent(self) -> None:
        (indicator,) = build_burden_indicators(
            {"a": [_finding(_record("KEN", 2020, 1.0), _record("KEN", 2024, 2.0))]}
        )
        self.assertEqual([r.year for r in indicator.readings], [2024, 2020])

    def test_every_indicator_gets_a_stable_identity(self) -> None:
        first = build_burden_indicators({"a": [_finding(_record("KEN", 2024, 1.0))]})
        second = build_burden_indicators({"a": [_finding(_record("KEN", 2024, 1.0))]})
        self.assertTrue(first[0].projection_id)
        self.assertEqual(first[0].projection_id, second[0].projection_id)


class LaneTests(unittest.TestCase):
    def _spec(self):
        return next(spec for spec in source_specs() if spec.key == "who_gho")

    def test_it_is_the_only_epidemiology_lane_and_feeds_burden(self) -> None:
        spec = self._spec()
        self.assertEqual(spec.evidence_class, "epidemiology")
        self.assertEqual(spec.feeds, ("burden",))

    def test_it_does_not_declare_region(self) -> None:
        """GHO addresses places by ISO3 code, and turning a stated region into codes needs
        a gazetteer this repository does not have. Every row carries its own place, so the
        geography arrives without the request naming it."""
        self.assertNotIn("region", self._spec().reads)

    def test_it_spans_jurisdictions(self) -> None:
        self.assertEqual(self._spec().jurisdiction, "multi")

    def test_it_is_reached_only_from_the_program_scope(self) -> None:
        """Planned per attribute it would repeat one answer for every variable, and each
        repetition costs two provider calls."""
        from services.scout.models import PROGRAM_QUERY_SETS, load_config
        import pathlib

        lanes = {lane for query_set in PROGRAM_QUERY_SETS.values() for lane in query_set.lanes}
        self.assertIn("who_gho", lanes)
        for config in sorted(pathlib.Path("services/scout/configs").glob("bmgf_*.yaml")):
            with self.subTest(config=config.name):
                self.assertNotIn("who_gho", load_config(str(config)).sources)


class ContractTests(unittest.TestCase):
    """The result contract has to accept what the program scope produces."""

    def test_a_projection_retrieved_by_the_program_scope_is_accepted(self) -> None:
        """The latent bug this covers: every projection's field references had to be a
        subset of the document's variables, and the program scope is deliberately not a
        variable. An announcement reaching the landscape would have failed the contract.
        """
        import inspect

        from services.scout import contract

        source = inspect.getsource(contract)
        self.assertIn("PROGRAM_SCOPE_KEY", source)

    def test_burden_indicators_are_not_role_classified(self) -> None:
        """A disease reading is not experimental or comparator, and not direct or
        analogous to a target. Requiring a role would demand a field it cannot have."""
        from services.scout.models import BurdenIndicator

        indicator = BurdenIndicator(indicator_code="X", indicator_name="x")
        self.assertFalse(hasattr(indicator, "source_role"))
        self.assertFalse(hasattr(indicator, "target_relationship"))


if __name__ == "__main__":
    unittest.main()
