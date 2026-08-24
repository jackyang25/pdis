"""What Inspector asks the model, and what it accepts back.

One call per rubric unit, one closed reason vocabulary, and lineage required for
every claim except absence. The shape this replaced asked three questions per unit
and merged their answers afterwards, so the same defect could arrive three times
and code had to decide which axis won.
"""

from __future__ import annotations

import unittest

from services.chunker import ContentBlock
from services.inspector.models import (
    UNIT_REASONS,
    InspectionConfig,
    SectionSpec,
    VariableSpec,
)
from services.inspector.stages.assessor import (
    _assess_section,
    _parse_cross_section_payload,
    _parse_unit_payload,
    assess_document,
    assessment_schema,
    build_assessment_prompt,
    check_cross_section,
    cross_section_schema,
)


def _block(block_id: str, section: str, ordinal: int = 1) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id="document",
        ordinal=ordinal,
        block_type="paragraph",
        content=f"Content filed under {section}.",
        heading_stack=[],
        structural_meta={},
        style_hint={},
        section_label=section,
    )


def _section() -> SectionSpec:
    return SectionSpec(
        name="Profile",
        description="Product targets",
        variables=[
            VariableSpec(name="Efficacy", description="Efficacy target"),
            VariableSpec(name="Safety", description="Safety target"),
        ],
    )


def _config(sections: list[SectionSpec] | None = None) -> InspectionConfig:
    return InspectionConfig(
        type_key="test_itpp_vaccine",
        org="test",
        source_type="itpp",
        intervention_class="vaccine",
        display_name="Test",
        sections=sections
        or [
            SectionSpec(name="Profile", description="Targets"),
            SectionSpec(name="Timeline", description="Dates"),
        ],
    )


def _finding(reason: str, block_ids: list[str]) -> dict:
    return {
        "reason": reason,
        "statement": f"A {reason} problem.",
        "recommendation": "Do the thing.",
        "block_ids": block_ids,
    }


class _UnitClient:
    """Answers each unit call with a fixed finding list, recording the schema."""

    def __init__(self, findings_by_subject: dict[str, list[dict]]) -> None:
        self.findings_by_subject = findings_by_subject
        self.calls = 0
        self.reason_enum: list[str] | None = None

    def call_structured(self, _system, message, *_args, schema, **_kwargs):
        self.calls += 1
        self.reason_enum = schema["properties"]["findings"]["items"]["properties"][
            "reason"
        ]["enum"]
        subject = message.split("Assess: ", 1)[1].splitlines()[0]
        return {"findings": self.findings_by_subject.get(subject, [])}


class _EmptyClient:
    def call_structured(self, *_args, **_kwargs):
        return None


class PromptAndSchemaTests(unittest.TestCase):
    def test_the_model_is_offered_every_reason_a_unit_can_raise(self) -> None:
        schema = assessment_schema([_block("document:b1", "Profile")])
        reasons = schema["properties"]["findings"]["items"]["properties"]["reason"]["enum"]

        self.assertEqual(reasons, list(UNIT_REASONS))
        self.assertNotIn("conflicting", reasons, "a conflict belongs to no single unit")

    def test_findings_are_capped_at_one_per_reason(self) -> None:
        schema = assessment_schema([_block("document:b1", "Profile")])
        self.assertEqual(schema["properties"]["findings"]["maxItems"], len(UNIT_REASONS))

    def test_wire_schemas_do_not_use_unsupported_unique_items(self) -> None:
        blocks = [_block("document:b1", "Profile")]
        unit = assessment_schema(blocks)["properties"]["findings"]["items"]["properties"]
        self.assertNotIn("uniqueItems", unit["block_ids"])
        conflict = cross_section_schema({"Profile": blocks})["properties"]["findings"][
            "items"
        ]["properties"]
        self.assertNotIn("uniqueItems", conflict["block_ids"])

    def test_the_prompt_names_the_one_unit_being_assessed(self) -> None:
        section = _section()
        prompt = build_assessment_prompt(section, section.variables[0])

        self.assertIn("Efficacy, within the Profile section.", prompt)
        self.assertNotIn("Safety", prompt, "an unrelated unit must not sit in this prompt")

    def test_a_prose_section_is_assessed_as_itself(self) -> None:
        prompt = build_assessment_prompt(SectionSpec(name="Introduction", description="Framing."))
        self.assertIn("The Introduction section as a whole.", prompt)

    def test_unit_expectations_override_the_section_default(self) -> None:
        section = SectionSpec(
            name="Profile",
            description="Targets",
            expectations="Section default.",
            variables=[
                VariableSpec(name="Efficacy", description="Target", expectations="Unit rule."),
                VariableSpec(name="Safety", description="Target"),
            ],
        )

        self.assertIn("Expectations: Unit rule.", build_assessment_prompt(section, section.variables[0]))
        self.assertIn("Expectations: Section default.", build_assessment_prompt(section, section.variables[1]))


class OneCallPerUnitTests(unittest.TestCase):
    def test_each_unit_costs_exactly_one_request(self) -> None:
        """Three questions per unit meant three requests for one answer."""
        client = _UnitClient({})

        _assess_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=client,
            max_tokens=4000,
        )

        self.assertEqual(client.calls, 2, "two units, two calls")

    def test_a_sound_unit_produces_no_finding(self) -> None:
        findings = _assess_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=_UnitClient({}),
            max_tokens=4000,
        )

        self.assertEqual(findings, [])

    def test_findings_carry_their_unit_and_stable_ids(self) -> None:
        client = _UnitClient(
            {"Efficacy": [_finding("unclear", ["document:b1"])], "Safety": [_finding("missing", [])]}
        )

        findings = _assess_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=client,
            max_tokens=4000,
        )

        self.assertEqual(
            [(f.section_name, f.variable_name, f.reason, f.id) for f in findings],
            [
                ("Profile", "Efficacy", "unclear", "Profile|Efficacy|unclear"),
                ("Profile", "Safety", "missing", "Profile|Safety|missing"),
            ],
        )

    def test_a_failed_unit_stops_the_run_rather_than_publishing_a_hole(self) -> None:
        with self.assertRaisesRegex(ValueError, "could not assess Efficacy in Profile"):
            _assess_section(
                section_spec=_section(),
                section_blocks=[_block("document:b1", "Profile")],
                llm_client=_EmptyClient(),
                max_tokens=4000,
            )

    def test_an_unwritten_section_reports_every_unit_absent(self) -> None:
        """The denominator stays honest instead of collapsing to one line."""
        config = _config([_section(), SectionSpec(name="Timeline", description="Dates")])

        findings, mapped = assess_document(
            [_block("document:b1", "Timeline")],
            config,
            _UnitClient({}),
            max_tokens=4000,
        )

        # Presence is the mapping: Profile got no blocks, so it is absent.
        self.assertEqual(mapped["Profile"], [])
        self.assertEqual(mapped["Timeline"], ["document:b1"])
        self.assertEqual(
            [(f.variable_name, f.reason) for f in findings],
            [("Efficacy", "missing"), ("Safety", "missing")],
        )


class ParseTests(unittest.TestCase):
    def _parse(self, findings: list[dict]):
        return _parse_unit_payload(
            {"findings": findings},
            section_name="Profile",
            variable_name="Efficacy",
            section_blocks=[_block("document:b1", "Profile")],
        )

    def test_a_reported_problem_must_say_where_it_was_read(self) -> None:
        for reason in ("placeholder", "unmet", "off_template", "unclear"):
            with self.assertRaisesRegex(ValueError, "without citing a block"):
                self._parse([_finding(reason, [])])

    def test_absence_cites_nothing_even_when_the_model_offers_a_block(self) -> None:
        parsed = self._parse([_finding("missing", ["document:b1"])])
        self.assertEqual(parsed[0].cited_block_ids, [])

    def test_absence_silences_every_other_reason_for_that_unit(self) -> None:
        """One absence used to become two findings, written by code."""
        parsed = self._parse(
            [_finding("missing", []), _finding("off_template", ["document:b1"])]
        )

        self.assertEqual([f.reason for f in parsed], ["missing"])

    def test_the_same_reason_twice_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "raised unclear twice"):
            self._parse([_finding("unclear", ["document:b1"]), _finding("unclear", ["document:b1"])])

    def test_an_unknown_block_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown block ID"):
            self._parse([_finding("unclear", ["document:b9"])])

    def test_a_finding_with_no_statement_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no statement"):
            self._parse([{"reason": "unclear", "statement": "", "recommendation": "", "block_ids": ["document:b1"]}])

    def test_findings_come_back_in_the_published_reason_order(self) -> None:
        parsed = self._parse(
            [_finding("unclear", ["document:b1"]), _finding("off_template", ["document:b1"])]
        )
        self.assertEqual([f.reason for f in parsed], ["off_template", "unclear"])


class CrossSectionTests(unittest.TestCase):
    def _blocks_by_section(self) -> dict[str, list[ContentBlock]]:
        return {
            "Profile": [_block("document:b1", "Profile", 1)],
            "Timeline": [_block("document:b2", "Timeline", 2)],
        }

    def test_a_conflict_must_cite_two_different_sections(self) -> None:
        payload = {"findings": [_finding("conflicting", ["document:b1"])]}
        self.assertIsNone(_parse_cross_section_payload(payload, self._blocks_by_section()))

    def test_a_spanning_conflict_becomes_a_document_finding(self) -> None:
        payload = {
            "findings": [
                {
                    "statement": "Values conflict.",
                    "recommendation": "Reconcile them.",
                    "block_ids": ["document:b1", "document:b2"],
                }
            ]
        }

        findings = _parse_cross_section_payload(payload, self._blocks_by_section())

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].reason, "conflicting")
        self.assertIsNone(findings[0].section_name)
        self.assertEqual(findings[0].level, "not_met")

    def test_only_rubric_sections_are_citable(self) -> None:
        recorded: dict[str, list[str]] = {}

        class Client:
            def call_structured(self, _system, _message, *_args, schema, **_kwargs):
                recorded["ids"] = schema["properties"]["findings"]["items"]["properties"][
                    "block_ids"
                ]["items"]["enum"]
                return {"findings": []}

        blocks = [
            _block("document:b1", "Profile", 1),
            _block("document:b2", "Timeline", 2),
            _block("document:b3", "Other", 3),
            _block("document:b4", "Document Metadata", 4),
        ]
        check_cross_section(blocks, _config(), Client(), max_tokens=4000)

        self.assertEqual(recorded["ids"], ["document:b1", "document:b2"])

    def test_one_mapped_section_makes_the_pass_not_applicable(self) -> None:
        blocks = [_block("document:b1", "Profile", 1), _block("document:b3", "Other", 3)]

        findings, status = check_cross_section(blocks, _config(), _EmptyClient(), max_tokens=4000)

        self.assertEqual((findings, status), ([], "not_applicable"))

    def test_a_failed_pass_is_reported_rather_than_read_as_clean(self) -> None:
        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]

        findings, status = check_cross_section(blocks, _config(), _EmptyClient(), max_tokens=4000)

        self.assertEqual((findings, status), ([], "failed"))


if __name__ == "__main__":
    unittest.main()


class CrossSectionBoundaryTest(unittest.TestCase):
    """The consistency pass may not reach a verdict Inspector has no authority for.

    The structural gate cannot catch this one. It accepts any finding citing two real
    blocks in two real sections, so "both of these targets are clinically unrealistic"
    passes every check while being Scout's judgment made with no evidence behind it. The
    prompt is the only place it can be ruled out, and the per-unit prompt already rules it
    out - so this asserts the two agree rather than that one of them says something.
    """

    def test_both_prompts_refuse_to_assume_absent_external_evidence(self) -> None:
        from services.inspector.stages.assessor import (
            build_assessment_prompt,
            build_cross_section_prompt,
        )

        for name, text in (
            (
                "per-unit",
                build_assessment_prompt(
                    SectionSpec(name="Introduction", description="Framing.")
                ),
            ),
            ("cross-section", build_cross_section_prompt(_config())),
        ):
            with self.subTest(prompt=name):
                self.assertIn("external facts or evidence that are absent", text)

    def test_the_consistency_prompt_anchors_a_conflict_on_the_document_itself(self) -> None:
        from services.inspector.stages.assessor import build_cross_section_prompt

        text = build_cross_section_prompt(_config())
        self.assertIn("the document disagreeing with itself", text)
        self.assertIn("clinically plausible", text)
