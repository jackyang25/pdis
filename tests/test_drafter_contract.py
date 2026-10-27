"""A draft result is one Drafter could have produced, or it is refused."""

from __future__ import annotations

import unittest

from services.drafter.contract import validate_result_contract


def observation(identifier: str, basis: str = "comparable_product") -> dict:
    return {
        "id": identifier, "basis": basis, "url": "https://example.org/a", "title": "Trial A",
        "source_label": "PubMed", "product": "RTS,S", "measure": "efficacy",
        "quote": "Efficacy was 56% over 12 months.",
        "value": {"value": 56.0, "lower": None, "upper": None, "unit": "%", "text": "56%"}
        if basis == "comparable_product" else None,
        "numeric_eligible": basis == "comparable_product",
        "published_at": "2021-04-01" if basis == "comparable_product" else None,
        "published_precision": "month" if basis == "comparable_product" else "",
    }


def suggested(**overrides) -> dict:
    variable = {
        "name": "vaccine.efficacy", "label": "Efficacy", "description": "Protective efficacy.",
        "evidence_domain": "clinical", "status": "complete",
        "failure": None,
        "observations": [observation("vaccine.efficacy:o1"), observation("vaccine.efficacy:g1", "published_guidance")],
        "statistics": [],
        "suggestion": {
            "kind": "range", "minimum": "50%", "preferred": "75%", "statement": "",
            "rationale": "Comparable vaccines reached 56%; guidance prefers 75%.",
            "leans_on": "both", "basis_ids": ["vaccine.efficacy:o1", "vaccine.efficacy:g1"],
        },
    }
    variable.update(overrides)
    return variable


def result(*variables: dict) -> dict:
    return {
        "org": "bmgf", "source_type": "itpp", "intervention_class": "vaccine",
        "indication": "malaria", "intended_use": "", "display_name": "BMGF Intervention TPP - Vaccine",
        "sources": ["pubmed"], "failed_sources": [], "unconfigured_sources": [], "source_errors": [],
        "variables": list(variables or (suggested(),)),
    }


class ContractTests(unittest.TestCase):
    def assertRefused(self, value: dict) -> None:
        with self.assertRaises(ValueError):
            validate_result_contract(value)

    def test_a_complete_result_is_accepted_and_returned(self):
        value = result()
        self.assertIs(validate_result_contract(value), value)

    def test_the_intended_use_is_text_trimmed_and_bounded(self):
        for bad in (None, " padded ", "x" * 601):
            with self.subTest(bad=bad):
                self.assertRefused({**result(), "intended_use": bad})
        self.assertTrue(validate_result_contract({**result(), "intended_use": "Maternal immunization."}))

    def test_a_range_without_a_basis_is_refused(self):
        variable = suggested()
        variable["suggestion"]["basis_ids"] = []
        self.assertRefused(result(variable))

    def test_a_basis_the_variable_does_not_hold_is_refused(self):
        variable = suggested()
        variable["suggestion"]["basis_ids"] = ["vaccine.efficacy:o9"]
        self.assertRefused(result(variable))

    def test_insufficient_evidence_carries_no_values(self):
        variable = suggested()
        variable["suggestion"] = {
            "kind": "insufficient", "minimum": "50%", "preferred": "", "statement": "",
            "rationale": "Too little evidence.", "leans_on": "", "basis_ids": [],
        }
        self.assertRefused(result(variable))

    def test_leaning_on_guidance_requires_a_guidance_basis(self):
        variable = suggested()
        variable["suggestion"]["leans_on"] = "guidance"
        variable["suggestion"]["basis_ids"] = ["vaccine.efficacy:o1"]
        self.assertRefused(result(variable))

    def test_a_failure_is_not_a_suggestion(self):
        failed = suggested(status="failed", failure={"code": "suggestion_failed", "message": "No valid reply.",
                                                     "cause": "invalid_model_response"})
        self.assertRefused(result(failed))
        failed["suggestion"] = None
        validate_result_contract(result(failed))
        failed["failure"]["code"] = "something_else"
        self.assertRefused(result(failed))

    def test_a_failed_call_carries_its_cause_and_missing_evidence_carries_none(self):
        failed = suggested(status="failed", suggestion=None,
                           failure={"code": "suggestion_failed", "message": "Cut off.", "cause": None})
        self.assertRefused(result(failed))
        failed["failure"]["cause"] = "not_a_cause"
        self.assertRefused(result(failed))
        failed["failure"] = {"code": "evidence_unavailable", "message": "Sources failed.", "cause": "provider_error"}
        self.assertRefused(result(failed))
        failed["failure"]["cause"] = None
        validate_result_contract(result(failed))

    def test_stored_figures_must_be_the_arithmetic_of_the_observations(self):
        variable = suggested()
        second = observation("vaccine.efficacy:o2")
        second["quote"] = "Efficacy was 60% over 12 months."
        second["value"] = {"value": 60.0, "lower": None, "upper": None, "unit": "%", "text": "60%"}
        variable["observations"].append(second)
        self.assertRefused(result(variable))
        variable["statistics"] = [{"unit": "%", "observation_ids": ["vaccine.efficacy:o1", "vaccine.efficacy:o2"],
                                   "count": 2, "minimum": 56.0, "maximum": 60.0, "median": 58.0,
                                   "lower_quartile": 57.0, "upper_quartile": 59.0}]
        validate_result_contract(result(variable))
        variable["statistics"][0]["observation_ids"] = ["vaccine.efficacy:o2", "vaccine.efficacy:o1"]
        self.assertRefused(result(variable))
        variable["statistics"][0]["observation_ids"] = ["vaccine.efficacy:o1", "vaccine.efficacy:o2"]
        variable["statistics"][0]["median"] = 70.0
        self.assertRefused(result(variable))

    def test_a_stated_value_carries_the_words_of_its_quote_that_state_it(self):
        variable = suggested()
        variable["observations"][0]["value"]["text"] = "65%"
        self.assertRefused(result(variable))
        variable["observations"][0]["value"]["text"] = ""
        self.assertRefused(result(variable))

    def test_the_basis_a_suggestion_leans_on_is_the_basis_it_cites(self):
        variable = suggested()
        variable["suggestion"]["leans_on"] = "comparable_products"
        self.assertRefused(result(variable))

    def test_a_guidance_value_never_enters_statistics(self):
        variable = suggested()
        variable["observations"][1]["numeric_eligible"] = True
        self.assertRefused(result(variable))

    def test_an_observation_states_its_publication_date_at_a_known_precision_or_none(self):
        for field, value in (("published_precision", ""), ("published_precision", "season"),
                             ("published_at", "April 2021"), ("published_at", None)):
            with self.subTest(field=field, value=value):
                variable = suggested()
                variable["observations"][0][field] = value
                self.assertRefused(result(variable))
        variable = suggested()
        del variable["observations"][0]["published_at"]
        self.assertRefused(result(variable))
        undated = suggested()
        undated["observations"][1]["published_precision"] = "year"
        self.assertRefused(result(undated))

    def test_variable_names_are_unique(self):
        self.assertRefused(result(suggested(), suggested()))


if __name__ == "__main__":
    unittest.main()
