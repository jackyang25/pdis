"""Turning a variable's evidence into a suggestion, and its comparable values into figures."""

from __future__ import annotations

import unittest

from services.drafter.assembly import summarise
from services.drafter.models import Observation, ObservedValue
from services.drafter.stages.suggester import EFFORT, _schema, suggest
from shared.ai import ResponseTruncatedError
from shared.errors import ModelResponseError
from shared.vocabulary import AttributeDefinition
from tests.drafter_support import ScriptedClient

EFFICACY = AttributeDefinition("vaccine.efficacy", "Protective efficacy.", "clinical")


def observed(identifier: str, value: float | None, unit: str = "%", basis: str = "comparable_product", eligible: bool = True) -> Observation:
    return Observation(
        id=identifier, basis=basis, url="https://example.org", title="Source", source_label="PubMed",
        product="Product", measure="efficacy", quote=f"efficacy {value}{unit}",
        value=ObservedValue(value, None, None, unit, f"{value}{unit}") if value is not None else None,
        numeric_eligible=eligible,
    )


class SummaryTests(unittest.TestCase):
    def test_values_in_different_units_are_never_pooled(self):
        groups = summarise([observed("o1", 56), observed("o2", 77), observed("o3", 3, "per 1000"), observed("o4", 4, "per 1000")])
        self.assertEqual([(group.unit, group.count) for group in groups], [("%", 2), ("per 1000", 2)])
        self.assertEqual(groups[0].median, 66.5)
        # Lineage is listed, never counted: each figure names the observations it came from.
        self.assertEqual([group.observation_ids for group in groups], [("o1", "o2"), ("o3", "o4")])

    def test_a_lone_value_or_an_ineligible_one_makes_no_figure(self):
        self.assertEqual(summarise([observed("o1", 56), observed("o2", 77, eligible=False)]), [])

    def test_units_are_grouped_as_written_so_case_is_never_assumed_away(self):
        # mIU/mL and MIU/mL are a thousand-billion-fold apart; only spacing is folded.
        groups = summarise([observed("o1", 2, "mIU/mL"), observed("o2", 3, "MIU/mL"), observed("o3", 4, "mIU/mL ")])
        self.assertEqual([(group.unit, group.count) for group in groups], [("mIU/mL", 2)])


def reply(**overrides) -> dict:
    value = {"kind": "range", "minimum": "50%", "preferred": "75%", "statement": "",
             "rationale": "Comparable vaccines reached 56%.", "basis_ids": ["o1"]}
    value.update(overrides)
    return {"suggestion": value}


class SuggesterTests(unittest.TestCase):
    def suggest(self, *replies, observations=None):
        client = ScriptedClient({"Variable: efficacy": list(replies)})
        held = observations if observations is not None else [observed("o1", 56)]
        return suggest(EFFICACY, held, summarise(held), client, indication="malaria", intervention_term="vaccine"), client

    def test_a_valid_range_is_returned_with_its_basis(self):
        suggestion, client = self.suggest(reply())
        self.assertEqual((suggestion.kind, suggestion.minimum, suggestion.basis_ids), ("range", "50%", ("o1",)))
        self.assertIn("[o1]", client.calls[0][1])

    def test_the_basis_it_leans_on_is_read_off_what_it_cites(self):
        guidance = observed("g1", 75, basis="published_guidance", eligible=False)
        held = [observed("o1", 56), guidance]
        for basis_ids, leans_on in ((["o1"], "comparable_products"), (["g1"], "guidance"),
                                    (["o1", "g1"], "both")):
            with self.subTest(basis_ids=basis_ids):
                suggestion, _ = self.suggest(reply(basis_ids=basis_ids), observations=held)
                self.assertEqual(suggestion.leans_on, leans_on)
        self.assertNotIn("leans_on", str(_schema(["o1"])), "the model is not asked for it")

    def test_the_message_gives_each_observation_its_measure_eligibility_and_figure_lineage(self):
        held = [observed("o1", 56), observed("o2", 77), observed("o3", 60, eligible=False)]
        _, client = self.suggest(reply(), observations=held)
        message = client.calls[0][1]
        self.assertIn("Variable: efficacy\n", message, "the phrase, not the attribute key")
        self.assertNotIn("vaccine.efficacy", message)
        self.assertIn("measures: efficacy", message)
        self.assertIn("read as 56 % (may supply a figure)", message)
        self.assertIn("read as 60 % (context, not a figure)", message)
        self.assertIn("from o1, o2", message)
        self.assertNotIn("  ", message)

    def test_each_kind_is_its_own_variant_in_the_schema(self):
        variants = _schema(["o1"])["properties"]["suggestion"]["anyOf"]
        kinds = [variant["properties"]["kind"]["enum"] for variant in variants]
        self.assertEqual(kinds, [["range"], ["range"], ["statement"], ["insufficient"]])
        insufficient = variants[-1]["properties"]
        self.assertEqual(insufficient["basis_ids"]["maxItems"], 0)
        self.assertEqual(insufficient["minimum"], {"type": "string", "enum": [""]})
        for variant in variants[:3]:
            self.assertEqual(variant["properties"]["basis_ids"]["minItems"], 1)

    def test_a_pairing_violation_is_retried_once_then_fails(self):
        suggestion, client = self.suggest(reply(basis_ids=[]), reply())
        self.assertEqual(len(client.calls), 2)
        self.assertIn("prior answer", client.calls[1][1])
        with self.assertRaises(ModelResponseError):
            self.suggest(reply(kind="statement"), reply(kind="statement"))

    def test_a_reply_cut_off_at_its_limit_is_tried_once_more_with_less_reasoning(self):
        # Live runs saw a reasoning model spend a whole budget thinking, and then a doubled one.
        cut_off = ResponseTruncatedError("The model reached the response limit before completing its answer.")
        suggestion, client = self.suggest(cut_off, reply())
        self.assertEqual(suggestion.kind, "range")
        first, second = client.calls[0][2], client.calls[1][2]
        self.assertEqual((first["effort"], second["effort"]), (EFFORT, "low"))
        self.assertEqual(first["max_tokens"], second["max_tokens"])
        with self.assertRaises(ResponseTruncatedError):
            self.suggest(cut_off, cut_off)

    def test_every_model_answer_gives_a_rationale_and_the_schema_says_so(self):
        insufficient = reply(kind="insufficient", minimum="", preferred="", rationale="", basis_ids=[])
        with self.assertRaises(ModelResponseError):
            self.suggest(insufficient, insufficient)
        for variant in _schema(["o1"])["properties"]["suggestion"]["anyOf"]:
            self.assertEqual(variant["properties"]["rationale"]["pattern"], "\\S")

    def test_with_nothing_to_cite_the_variable_is_insufficient_without_a_call(self):
        suggestion, client = self.suggest(observations=[])
        self.assertEqual((suggestion.kind, suggestion.rationale, suggestion.basis_ids), ("insufficient", "", ()))
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
