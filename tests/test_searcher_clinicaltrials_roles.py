from __future__ import annotations

import unittest

from services.searcher.stages.clinicaltrials import clinicaltrial_to_finding


def _study(*, interventions: list[dict], arm_groups: list[dict]) -> dict:
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00000001",
                "briefTitle": "Structured arm-role study",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "designModule": {"phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["Malaria"]},
            "armsInterventionsModule": {
                "armGroups": arm_groups,
                "interventions": interventions,
            },
        }
    }


class ClinicalTrialsRoleTests(unittest.TestCase):
    def test_explicit_arm_types_survive_normalization(self) -> None:
        finding = clinicaltrial_to_finding(
            _study(
                interventions=[
                    {"name": "Candidate A", "armGroupLabels": ["Experimental"]},
                    {"name": "Standard therapy", "armGroupLabels": ["Comparator"]},
                    {"name": "Saline", "armGroupLabels": ["Placebo"]},
                ],
                arm_groups=[
                    {
                        "label": "Experimental",
                        "type": "EXPERIMENTAL",
                        "interventionNames": ["Candidate A"],
                    },
                    {
                        "label": "Comparator",
                        "type": "ACTIVE_COMPARATOR",
                        "interventionNames": ["Standard therapy"],
                    },
                    {
                        "label": "Placebo",
                        "type": "PLACEBO_COMPARATOR",
                        "interventionNames": ["Saline"],
                    },
                ],
            ),
            "malaria vaccine",
        )

        self.assertIsNotNone(finding)
        roles = {
            record.program_name: record.source_role
            for record in (finding.development_records if finding else [])
        }
        self.assertEqual(
            roles,
            {
                "Candidate A": "experimental",
                "Standard therapy": "comparator",
                "Saline": "control",
            },
        )

    def test_conflicting_explicit_arm_roles_become_unknown(self) -> None:
        finding = clinicaltrial_to_finding(
            _study(
                interventions=[
                    {
                        "name": "Candidate A",
                        "armGroupLabels": ["Experimental", "Comparator"],
                    }
                ],
                arm_groups=[
                    {"label": "Experimental", "type": "EXPERIMENTAL"},
                    {"label": "Comparator", "type": "ACTIVE_COMPARATOR"},
                ],
            ),
            "malaria vaccine",
        )

        self.assertIsNotNone(finding)
        self.assertEqual(finding.development_records[0].source_role, "unknown")

    def test_missing_structured_arm_metadata_stays_unknown(self) -> None:
        finding = clinicaltrial_to_finding(
            _study(
                interventions=[{"name": "Placebo-looking product"}],
                arm_groups=[],
            ),
            "malaria vaccine",
        )

        self.assertIsNotNone(finding)
        self.assertEqual(finding.development_records[0].source_role, "unknown")


if __name__ == "__main__":
    unittest.main()
