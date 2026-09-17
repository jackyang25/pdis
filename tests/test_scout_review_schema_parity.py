"""Conditional wire constraints are visible to the provider, including nested slots."""
import unittest

from services.scout.ai_wire import EvidenceUnitIdentityWire, inline_json_schema
from services.scout.ai_contracts import document_quantitative_ledger_batch


class ReviewSchemaParityTest(unittest.TestCase):
    def test_document_qualifiers_require_citations_only_when_asserted(self):
        contract = document_quantitative_ledger_batch(["context-1"], ["unit-1"], ["field-1"])
        target = contract.schema["properties"]["reviews"]["items"]["properties"]["targets"]["items"]["properties"]
        for branch in target["semantic_profile"]["properties"]["population"]["anyOf"]:
            asserted = branch["properties"]["state"]["enum"][0] in {"specified", "other"}
            refs = branch["properties"]["source_refs"]
            self.assertEqual(refs["minItems" if asserted else "maxItems"], 1 if asserted else 0)
        for branch in target["comparison_contract"]["properties"]["population"]["anyOf"]:
            props = branch["properties"]
            mode = props["mode"]["enum"][0]
            if mode in {"exact", "compatible"}:
                self.assertEqual(props["scope"]["minLength"], 1)
            elif mode == "unknown":
                self.assertEqual(props["reason"]["minLength"], 1)
            else:
                self.assertEqual(props["scope"]["enum"], [""])

    def test_nested_identity_branches_state_assertion_requirements(self):
        schema = inline_json_schema(EvidenceUnitIdentityWire)
        resolved_group, resolved_cohort, unresolved = schema["anyOf"]
        self.assertEqual(resolved_group["properties"]["status"]["enum"], ["resolved"])
        for slot in resolved_group["properties"]["group"]["anyOf"]:
            state = slot["properties"]["state"]["enum"][0]
            self.assertIn(state, {"specified", "other"})
            key = "value" if state == "specified" else "other"
            self.assertEqual(slot["properties"][key]["minLength"], 1)
        self.assertEqual(resolved_cohort["properties"]["cohort"], resolved_group["properties"]["group"])
        self.assertEqual(unresolved["properties"]["status"]["enum"], ["record_level", "uncertain"])
        self.assertEqual(unresolved["properties"]["reason"]["minLength"], 1)


if __name__ == "__main__":
    unittest.main()
