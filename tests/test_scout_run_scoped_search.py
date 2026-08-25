"""A search planned from the run's own scope, not from a variable.

The development landscape and the burden indicators are asked about the *run*: its
condition, its intervention class. Those intents carry `PROGRAM_SCOPE_KEY` as their scope
because there is no variable that owns them, and the projections they produce reach the
contract with the same sentinel, which two checks there already accept.

The trace that produced them did not. So any run whose burden lane actually fired was
rejected by its own contract:

    search trace 'indicator_name_contains:polio' references unknown field 'program'

Nothing exercised it, because no test built a run-scoped `SearchTrace` and validated it.
"""

from __future__ import annotations

import unittest

from services.scout.contract import validate_result_contract
from services.scout.models import PROGRAM_SCOPE_KEY, SearchTrace

from tests.test_scout_contract import _result as minimal_result


class RunScopedSearchTraceTests(unittest.TestCase):
    def _with_trace(self, **over) -> object:
        result = minimal_result()
        result.search_plan = [
            SearchTrace(
                attribute_ref=over.pop("attribute_ref", PROGRAM_SCOPE_KEY),
                lane="who_gho",
                query="indicator_name_contains:polio",
                intent_ids=["intent-1"],
                input_queries=["polio"],
                **over,
            )
        ]
        return result

    def test_a_run_scoped_search_is_accepted(self):
        """The bug. A burden lane firing was enough to fail the whole result."""
        validate_result_contract(self._with_trace())

    def test_a_run_scoped_search_still_cannot_claim_a_passage(self):
        """The sentinel is a hole in the field check; it is not one in the lineage checks.

        A search built from the configured condition never read a document block, so
        claiming one would be a lineage the run cannot support.
        """
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(doc_block_ids=["document/b-0001"]))
        self.assertIn("document blocks", str(raised.exception))

    def test_a_run_scoped_search_still_cannot_claim_a_target(self):
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(target_ids=["qt-1"]))
        self.assertIn("targets", str(raised.exception))

    def test_a_variable_scoped_search_still_names_a_real_variable(self):
        """Unchanged. Only the one sentinel is exempt, not any unknown string."""
        with self.assertRaises(ValueError) as raised:
            validate_result_contract(self._with_trace(attribute_ref="not_a_field"))
        self.assertIn("references unknown field", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
