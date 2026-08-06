"""Every shipped rubric produces the same shape, whatever its own structure.

The rubrics differ a great deal: a TPP declares prose sections and two variable
tables, an IPDP declares eleven variable-bearing functional domains and no prose at
all, and the device profiles carry 50 units where a diagnostic carries 26. None of
that may reach the result. A consumer reading an IPDP assessment and a vaccine iTPP
assessment must be reading one shape.

This is the test that lets a rubric gain a field without anything downstream
breaking: it exercises assembly and the contract over every config actually
shipped, so a structural assumption that only holds for TPPs fails here rather than
in a run.
"""

from __future__ import annotations

import unittest

from services.chunker import find_config as find_chunker_config
from services.inspector.assembly import (
    absent_unit_findings,
    assess_sections,
    rank_findings,
    rubric_units,
)
from services.inspector.contract import validate_result_contract
from services.inspector.models import (
    Finding,
    InspectionResult,
    available_configs,
    inspection_result_to_dict,
)


def _blocks(config):
    """One block per section, labelled the way the chunker would label it."""
    from services.chunker import ContentBlock

    return [
        ContentBlock(
            id=f"doc:b{index}",
            doc_id="doc",
            ordinal=index,
            block_type="paragraph",
            content=f"content for {section.name}",
            heading_stack=[],
            structural_meta={},
            style_hint={},
            section_label=section.name,
        )
        for index, section in enumerate(config.sections, start=1)
    ]


class EveryRubricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.configs = available_configs()
        self.assertGreaterEqual(len(self.configs), 11, "configs failed to load")

    def test_every_rubric_declares_at_least_one_unit_per_section(self) -> None:
        """A section with no unit would be a row a reader cannot open."""
        for config in self.configs:
            units = rubric_units(config)
            for section in config.sections:
                owned = [u for u in units if u[0] == section.name]
                self.assertTrue(
                    owned,
                    f"{config.type_key}: section {section.name!r} contributes no unit",
                )

    def test_a_prose_section_and_a_table_section_both_yield_units(self) -> None:
        """The shape does not branch on which kind a rubric happens to use.

        IPDP rubrics declare no prose sections and every TPP declares several, so a
        consumer that handled only one kind would work on some documents and not
        others.
        """
        prose = [
            config.type_key
            for config in self.configs
            if any(not s.variables for s in config.sections)
        ]
        tabular = [
            config.type_key
            for config in self.configs
            if all(s.variables for s in config.sections)
        ]
        self.assertTrue(prose, "no rubric exercises the prose path")
        self.assertTrue(tabular, "no rubric exercises the all-variables path")

    def test_every_rubric_assembles_and_validates(self) -> None:
        """Assembly and the contract hold for each shipped rubric as it stands."""
        for config in self.configs:
            blocks = _blocks(config)
            mapped = {b.section_label: [b.id] for b in blocks}
            sections = assess_sections(
                config,
                findings=[],
                mapped_blocks=mapped,
            )
            result = InspectionResult(
                doc_id="doc",
                sections=sections,
                consistency_status="complete",
                assessment_status="complete",
                blocks=blocks,
            )

            validate_result_contract(result, config)

            self.assertEqual(
                sum(len(s.units) for s in result.sections),
                len(rubric_units(config)),
                f"{config.type_key}: published units differ from the rubric",
            )

    def test_every_rubric_survives_a_finding_on_every_unit(self) -> None:
        """The worst case: nothing supplied anywhere, in every rubric."""
        for config in self.configs:
            findings = [
                finding
                for section in config.sections
                for finding in absent_unit_findings(config, section.name)
            ]
            sections = assess_sections(config, findings=findings)
            ordered = rank_findings(config, sections)

            statuses = {unit.status for s in sections for unit in s.units}
            self.assertTrue(statuses <= {"not_met", "not_applicable"}, config.type_key)
            # Ranks are dense and unique, so a worklist cannot show two items in the
            # same position however many units a rubric declares.
            self.assertEqual(
                [f.rank for f in ordered],
                list(range(len(ordered))),
                f"{config.type_key}: ranks are not dense",
            )

    def test_the_published_payload_has_the_same_keys_for_every_rubric(self) -> None:
        """A config field added upstream must not change the published shape."""
        shapes = set()
        for config in self.configs:
            blocks = _blocks(config)
            sections = assess_sections(
                config,
                findings=[],
                mapped_blocks={b.section_label: [b.id] for b in blocks},
            )
            payload = inspection_result_to_dict(
                InspectionResult(
                    doc_id="doc",
                    sections=sections,
                    consistency_status="complete",
                    assessment_status="complete",
                    blocks=blocks,
                )
            )
            shapes.add(tuple(sorted(payload)))
            unit = payload["sections"][0]["units"][0]
            shapes.add(tuple(sorted(unit)))
        # Two shapes exactly: the result's keys and a unit's keys. A rubric that
        # leaked its own structure into the payload would add a third.
        self.assertEqual(len(shapes), 2, "the published shape varies by rubric")

    def test_no_rubric_field_reaches_the_published_result(self) -> None:
        """Rubric text stays upstream; the result carries assessment, not config.

        This is what keeps a new config field from breaking consumers: nothing
        downstream reads the rubric, so adding to it cannot change what they see.
        """
        config = self.configs[0]
        blocks = _blocks(config)
        sections = assess_sections(
            config,
            findings=[],
            mapped_blocks={b.section_label: [b.id] for b in blocks},
        )
        payload = inspection_result_to_dict(
            InspectionResult(
                doc_id="doc",
                sections=sections,
                consistency_status="complete",
                assessment_status="complete",
                blocks=blocks,
            )
        )

        # Checked as keys, not as substrings: "Environmental description" is a unit
        # name a device rubric legitimately declares, and matching text would flag it.
        def keys(node) -> set[str]:
            if isinstance(node, dict):
                return set(node) | {k for v in node.values() for k in keys(v)}
            if isinstance(node, list):
                return {k for item in node for k in keys(item)}
            return set()

        published = keys(payload)
        for rubric_only in ("description", "expectations", "stage_guidance", "mirrors"):
            self.assertNotIn(
                rubric_only, published, f"{rubric_only} leaked into the result"
            )


class SectionVocabularyTests(unittest.TestCase):
    """Inspector matches blocks by the label the chunker assigned them.

    The two services carry the section names separately, so a rename in one silently
    stops blocks mapping in the other. Nothing else enforces that agreement.
    """

    def test_every_rubric_section_is_one_the_chunker_can_label(self) -> None:
        for config in available_configs():
            chunker = find_chunker_config(
                config.org, config.source_type, config.intervention_class
            )
            labels = {entry["name"] for entry in chunker.section_taxonomy}
            for section in config.sections:
                self.assertIn(
                    section.name,
                    labels,
                    f"{config.type_key}: the chunker cannot label {section.name!r}, "
                    "so no block will ever map to it",
                )


if __name__ == "__main__":
    unittest.main()
