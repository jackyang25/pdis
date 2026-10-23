"""Turning a variable's evidence into a suggestion, and its comparable values into figures."""

from __future__ import annotations

import unittest

from services.drafter.assembly import summarise
from services.drafter.models import Observation, ObservedValue
from services.drafter.stages.suggester import suggest
from shared.errors import ModelResponseError
from shared.vocabulary import AttributeDefinition
from tests.drafter_support import ScriptedClient

EFFICACY = AttributeDefinition("vaccine.efficacy", "Protective efficacy.", "clinical")


def observed(identifier: str, value: float | None, unit: str = "%", basis: str = "comparable_product", eligible: bool = True) -> Observation:
    return Observation(
        id=identifier, basis=basis, url="https://example.org", title="Source", source_label="PubMed",
        product="Product", measure="efficacy", quote=f"efficacy {value}{unit}",
        value=ObservedValue(value, None, None, unit) if value is not None else None, numeric_eligible=eligible,
    )


class SummaryTests(unittest.TestCase):
    def test_values_in_different_units_are_never_pooled(self):
        groups = summarise([observed("o1", 56), observed("o2", 77), observed("o3", 3, "per 1000"), observed("o4", 4, "per 1000")])
        self.assertEqual([(group.unit, group.count) for group in groups], [("%", 2), ("per 1000", 2)])
        self.assertEqual(groups[0].median, 66.5)

    def test_a_lone_value_or_an_ineligible_one_makes_no_figure(self):
        self.assertEqual(summarise([observed("o1", 56), observed("o2", 77, eligible=False)]), [])

    def test_units_are_grouped_as_written_so_case_is_never_assumed_away(self):
        # mIU/mL and MIU/mL are a thousand-billion-fold apart; only spacing is folded.
        groups = summarise([observed("o1", 2, "mIU/mL"), observed("o2", 3, "MIU/mL"), observed("o3", 4, "mIU/mL ")])
        self.assertEqual([(group.unit, group.count) for group in groups], [("mIU/mL", 2)])


def reply(**overrides) -> dict:
    value = {"kind": "range", "minimum": "50%", "preferred": "75%", "statement": "",
             "rationale": "Comparable vaccines reached 56%.", "leans_on": "comparable_products", "basis_ids": ["o1"]}
    value.update(overrides)
    return value


class SuggesterTests(unittest.TestCase):
    def suggest(self, *replies, observations=None):
        client = ScriptedClient({"vaccine.efficacy": list(replies)})
        held = observations if observations is not None else [observed("o1", 56)]
        return suggest(EFFICACY, held, summarise(held), client, indication="malaria", intervention_term="vaccine"), client

    def test_a_valid_range_is_returned_with_its_basis(self):
        suggestion, client = self.suggest(reply())
        self.assertEqual((suggestion.kind, suggestion.minimum, suggestion.basis_ids), ("range", "50%", ("o1",)))
        self.assertIn("[o1]", client.calls[0][1])

    def test_a_pairing_violation_is_retried_once_then_fails(self):
        suggestion, client = self.suggest(reply(basis_ids=[]), reply())
        self.assertEqual(len(client.calls), 2)
        self.assertIn("prior answer", client.calls[1][1])
        with self.assertRaises(ModelResponseError):
            self.suggest(reply(kind="statement"), reply(kind="statement"))

    def test_a_reply_cut_off_at_its_limit_is_tried_once_more_with_more_room(self):
        # Live runs saw a reasoning model spend a whole budget thinking; one more try usually lands.
        cut_off = RuntimeError("The model reached the response limit before completing its answer.")
        suggestion, client = self.suggest(cut_off, reply())
        self.assertEqual(suggestion.kind, "range")
        self.assertGreater(client.calls[1][2]["max_tokens"], client.calls[0][2]["max_tokens"])
        with self.assertRaises(RuntimeError):
            self.suggest(cut_off, cut_off)

    def test_leaning_on_guidance_while_citing_a_product_is_invalid(self):
        with self.assertRaises(ModelResponseError):
            self.suggest(reply(leans_on="guidance"), reply(leans_on="guidance"))

    def test_with_nothing_to_cite_the_variable_is_insufficient_without_a_call(self):
        suggestion, client = self.suggest(observations=[])
        self.assertEqual((suggestion.kind, suggestion.rationale, suggestion.basis_ids), ("insufficient", "", ()))
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
