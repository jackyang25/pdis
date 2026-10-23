"""A draft result is one Drafter could have produced, or it is refused."""

from __future__ import annotations

import unittest

from services.drafter.contract import validate_result_contract


def observation(identifier: str, basis: str = "comparable_product") -> dict:
    return {
        "id": identifier, "basis": basis, "url": "https://example.org/a", "title": "Trial A",
        "source_label": "PubMed", "product": "RTS,S", "measure": "efficacy",
        "quote": "Efficacy was 56% over 12 months.",
        "value": {"value": 56.0, "lower": None, "upper": None, "unit": "%"} if basis == "comparable_product" else None,
        "numeric_eligible": basis == "comparable_product",
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
        "indication": "malaria", "display_name": "BMGF Intervention TPP - Vaccine",
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
        failed = suggested(status="failed", failure={"code": "suggestion_failed", "message": "No valid reply."})
        self.assertRefused(result(failed))
        failed["suggestion"] = None
        validate_result_contract(result(failed))
        failed["failure"]["code"] = "something_else"
        self.assertRefused(result(failed))

    def test_a_guidance_value_never_enters_statistics(self):
        variable = suggested()
        variable["observations"][1]["numeric_eligible"] = True
        self.assertRefused(result(variable))

    def test_variable_names_are_unique(self):
        self.assertRefused(result(suggested(), suggested()))


if __name__ == "__main__":
    unittest.main()
