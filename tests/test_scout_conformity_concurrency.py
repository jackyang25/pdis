from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from services.scout.models import (
    Attribute,
    NumericExpression,
    QuantitativeFieldLink,
    QuantitativeTarget,
    SemanticSlot,
)
from services.scout.stages import conformity


def _target(value: float, role: str) -> QuantitativeTarget:
    return QuantitativeTarget(
        field_links=[QuantitativeFieldLink(attribute_ref="efficacy", relation="defines", reason="Test fixture.")],
        expression=NumericExpression(
            kind="bound",
            unit="%",
            value=value,
            comparator=">=",
        ),
        role=role,
        quote=f"Target efficacy is at least {value:g}%.",
        doc_block_ids=["document/b-0001"],
        semantic_profile={
            "measure": SemanticSlot(state="specified", value="protective efficacy")
        },
    )


class ScoutConformityConcurrencyTests(unittest.TestCase):
    def test_one_claim_calibrates_once_across_multiple_field_views(self) -> None:
        target = QuantitativeTarget(
            field_links=[
                QuantitativeFieldLink(
                    attribute_ref="presentation",
                    relation="defines",
                    reason="The claim specifies presentation.",
                ),
                QuantitativeFieldLink(
                    attribute_ref="programmatic_suitability",
                    relation="constrains",
                    reason="The same claim constrains delivery.",
                ),
                QuantitativeFieldLink(
                    attribute_ref="delivery_strategy",
                    relation="context_for",
                    reason="The claim is useful delivery context.",
                ),
            ],
            expression=NumericExpression(
                kind="bound",
                unit="vials/dose",
                value=2,
                comparator="<=",
            ),
            role="threshold",
            quote="No more than two vials per administered dose.",
            doc_block_ids=["document/b-0001"],
            semantic_profile={
                "measure": SemanticSlot(
                    state="specified",
                    value="vials per administered dose",
                )
            },
        )
        attributes = [
            Attribute(
                name=name,
                description=name.replace("_", " "),
                document_target=target.quote,
                block_ids=target.doc_block_ids,
                target_resolved=True,
                quantitative_target_ids=(
                    [target.id] if name in target.analysis_attribute_refs else []
                ),
            )
            for name in (
                "presentation",
                "programmatic_suitability",
                "delivery_strategy",
            )
        ]

        scores = conformity.score_conformity_all(
            attributes,
            [target],
            {attribute.name: [] for attribute in attributes},
            object(),
            indication="malaria",
            intervention_class="vaccine",
        )

        self.assertEqual(len(scores), 1)
        self.assertEqual(
            scores[0].attribute_refs,
            ["presentation", "programmatic_suitability"],
        )

    def test_global_batch_queue_is_bounded_and_preserves_target_order(self) -> None:
        targets = [_target(80, "threshold"), _target(90, "optimal")]
        attribute = Attribute(
            name="efficacy",
            description="Protective efficacy",
            document_target="Two efficacy targets.",
            block_ids=["document/b-0001"],
            target_resolved=True,
            quantitative_target_ids=[target.id for target in targets],
        )
        # Six passages create two batches per target: four independent jobs.
        passages = [object() for _ in range(6)]
        lock = threading.Lock()
        active = 0
        max_active = 0
        progress: list[tuple[int, int]] = []

        def fake_map(*_args, **_kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return conformity._CalibrationBatchResult([], [])

        with (
            patch.object(conformity, "_source_passages", return_value=passages),
            patch.object(conformity, "_map_source_passage_batch", side_effect=fake_map),
        ):
            scores = conformity.score_conformity_all(
                [attribute],
                targets,
                {attribute.name: []},
                object(),
                indication="malaria",
                intervention_class="vaccine",
                max_workers=2,
                progress_callback=lambda completed, total: progress.append(
                    (completed, total)
                ),
            )

        self.assertEqual(max_active, 2)
        self.assertEqual(progress[0], (0, 4))
        self.assertEqual(progress[-1], (4, 4))
        self.assertEqual(
            [score.target_id for score in scores],
            [target.id for target in targets],
        )


if __name__ == "__main__":
    unittest.main()
