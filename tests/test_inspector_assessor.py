"""What Inspector asks the model, and what it accepts back.

One call per rubric unit, one closed vocabulary, one verdict back, and lineage
required for every claim except absence.

Two shapes preceded it. The first asked three questions per unit and merged their
answers, so the same defect arrived three times and code decided which axis won.
The second asked once but accepted a list, so a unit could come back with several
answers to one question and every layer above had to reconcile them.
"""

from __future__ import annotations

import unittest
import threading

from services.chunker import ContentBlock
from services.inspector.models import (
    UNIT_VERDICTS,
    InspectionConfig,
    SectionSpec,
    VariableSpec,
)
from services.inspector.stages.assessor import (
    _parse_cross_section_payload,
    _parse_unit_payload,
    assess_rubrics,
    assessment_schema,
    build_assessment_prompt,
    check_cross_section,
    cross_section_schema,
    unit_request,
)
from shared.ai import ResponseTruncatedError


def assess_document(blocks, config, llm_client, *, progress=None):
    return assess_rubrics(blocks, [config], llm_client, progress=progress)[0]


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


def _answer(verdict: str, block_ids: list[str]) -> dict:
    sound = verdict in ("specified", "not_applicable")
    return {
        "verdict": verdict,
        "statement": "" if sound else f"A {verdict} problem.",
        "block_ids": block_ids,
    }


def _assess_single_section(*, section_spec, section_blocks, llm_client):
    findings, _ = assess_document(
        section_blocks, _config([section_spec]), llm_client,
    )
    return findings


class _UnitClient:
    """Answers each unit call with a fixed verdict, recording the schema."""

    def __init__(self, answers_by_subject: dict[str, dict]) -> None:
        self.answers_by_subject = answers_by_subject
        self.calls = 0
        self.verdict_enum: list[str] | None = None

    def call_structured(self, _system, _message, *_args, schema, trailing_text, **_kwargs):
        self.calls += 1
        self.verdict_enum = schema["properties"]["verdict"]["enum"]
        subject = trailing_text.split("Assess: ", 1)[1].splitlines()[0]
        return self.answers_by_subject.get(
            subject, _answer("specified", ["document:b1"])
        )


class _EmptyClient:
    def call_structured(self, *_args, **_kwargs):
        return None


class PromptAndSchemaTests(unittest.TestCase):
    def test_the_model_is_offered_every_verdict_a_unit_can_carry(self) -> None:
        """Absence has one name per unit, and the rubric's `optional` flag picks it."""
        blocks = [_block("document:b1", "Profile")]
        required = assessment_schema(blocks)["properties"]["verdict"]["enum"]
        optional = assessment_schema(blocks, optional=True)["properties"]["verdict"]["enum"]

        self.assertEqual(required, [v for v in UNIT_VERDICTS if v != "not_applicable"])
        self.assertEqual(optional, [v for v in UNIT_VERDICTS if v != "not_present"])
        for verdicts in (required, optional):
            self.assertNotIn("section_conflict", verdicts, "a conflict belongs to no single unit")

    def test_one_question_gets_one_answer(self) -> None:
        """The schema returns an object, not an array of them. An array let a unit
        come back with several answers and every layer above had to pick one."""
        schema = assessment_schema([_block("document:b1", "Profile")])

        self.assertEqual(schema["type"], "object")
        self.assertEqual(sorted(schema["required"]), ["block_ids", "statement", "verdict"])
        self.assertNotIn("findings", schema["properties"])

    def test_the_boundary_between_the_two_soft_verdicts_is_stated(self) -> None:
        """`insufficient` and `vague` are the pair a model most often confuses.

        Two adjectives on their own left the split to be inferred, and the same
        content could land either side depending on how the requirement was read.
        The prompt states the test instead: coverage first, then usability.
        """
        prompt = build_assessment_prompt()

        self.assertIn("not degrees of each other", prompt)
        self.assertIn("Ask coverage first", prompt)

    def test_layout_alone_is_not_a_verdict(self) -> None:
        prompt = build_assessment_prompt()

        self.assertIn("Do not judge structure or naming on its own", prompt)
        self.assertNotIn("off_template", prompt)

    def test_no_recommendation_is_asked_for(self) -> None:
        """It restated the statement as an imperative, at the cost of tokens."""
        schema = assessment_schema([_block("document:b1", "Profile")])
        self.assertNotIn("recommendation", schema["properties"])
        self.assertNotIn(
            "recommendation",
            cross_section_schema({"Profile": [_block("document:b1", "Profile")]})[
                "properties"
            ]["findings"]["items"]["properties"],
        )

    def test_wire_schemas_do_not_use_unsupported_unique_items(self) -> None:
        blocks = [_block("document:b1", "Profile")]
        self.assertNotIn("uniqueItems", assessment_schema(blocks)["properties"]["block_ids"])
        conflict = cross_section_schema({"Profile": blocks})["properties"]["findings"][
            "items"
        ]["properties"]
        self.assertNotIn("uniqueItems", conflict["block_ids"])

    def test_the_request_names_the_one_unit_being_assessed(self) -> None:
        section = _section()
        request = unit_request(section, section.variables[0])

        self.assertIn("Efficacy, within the Profile section.", request)
        self.assertNotIn("Safety", request, "an unrelated unit must not sit in this request")

    def test_the_system_prompt_is_fixed_for_a_rubric_whatever_the_unit(self) -> None:
        """The unit travels after the section's content, so every request for one
        rubric shares the system prompt and the section's prefix."""
        prompt = build_assessment_prompt("Stage bar.")

        self.assertIn("Stage bar.", prompt)
        self.assertNotIn("THE UNIT YOU ARE ASSESSING", prompt)
        self.assertNotIn("Return ONLY valid JSON", prompt)

    def test_the_unit_follows_the_section_content_and_its_images(self) -> None:
        sent: list[dict] = []

        class Client:
            def call_structured(self, system, message, *_args, **kwargs):
                sent.append({"system": system, "message": message, **kwargs})
                return _answer("specified", ["document:b1"])

        assess_document([_block("document:b1", "Profile")], _config([_section()]),
                        Client())

        self.assertEqual(len({call["system"] for call in sent}), 1)
        self.assertEqual(len({call["message"] for call in sent}), 1)
        # Units fan out, so their calls arrive in either order.
        self.assertCountEqual(
            [call["trailing_text"].splitlines()[0] for call in sent],
            ["Assess: Efficacy", "Assess: Safety"],
        )

    def test_the_review_context_leads_the_shared_prefix(self) -> None:
        """A unit about the target population is read against the disease it is for."""
        sent: list[dict] = []

        class Client:
            def call_structured(self, system, message, *_args, **kwargs):
                sent.append({"message": message, **kwargs})
                return _answer("specified", ["document:b1"])

        assess_rubrics([_block("document:b1", "Profile")], [_config([_section()])], Client(),
                       indication="respiratory_syncytial_virus")
        message = sent[0]["message"]
        self.assertTrue(message.startswith("Review context (user-selected, not evidence):"))
        self.assertIn("Disease / condition: respiratory syncytial virus", message)
        self.assertIn("Intervention class: vaccine", message)
        self.assertEqual((sent[0]["task"], sent[0]["effort"]), ("reasoning", "low"))

    def test_a_section_too_large_for_one_request_stops_the_run_before_any_call(self) -> None:
        from shared.request_budget import RequestTooLargeError

        huge = _block("document:b1", "Profile")
        huge.content = "x" * 700_000

        with self.assertRaises(RequestTooLargeError):
            assess_document([huge], _config([_section()]), _EmptyClient())

    def test_a_prose_section_is_assessed_as_itself(self) -> None:
        request = unit_request(SectionSpec(name="Introduction", description="Framing."))
        self.assertIn("The Introduction section as a whole.", request)

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

        self.assertIn("Expectations: Unit rule.", unit_request(section, section.variables[0]))
        self.assertIn("Expectations: Section default.", unit_request(section, section.variables[1]))


class OneCallPerUnitTests(unittest.TestCase):
    def test_reversed_completion_keeps_authored_unit_order(self) -> None:
        second_completed = threading.Event()

        class ReverseClient(_UnitClient):
            def call_structured(self, system, message, *args, **kwargs):
                if kwargs["trailing_text"].startswith("Assess: Efficacy\n"):
                    if not second_completed.wait(timeout=3):
                        raise AssertionError("Second unit never completed concurrently")
                return super().call_structured(system, message, *args, **kwargs)

        def progress(_stage, *, completed, total):
            if completed == 1:
                second_completed.set()

        findings, _ = assess_document(
            [_block("document:b1", "Profile")], _config([_section()]),
            ReverseClient({}), progress=progress,
        )
        self.assertEqual([finding.id for finding in findings],
                         ["Profile|Efficacy", "Profile|Safety"])

    def test_each_unit_costs_exactly_one_request(self) -> None:
        """Three questions per unit meant three requests for one answer."""
        client = _UnitClient({})

        _assess_single_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=client,
        )

        self.assertEqual(client.calls, 2, "two units, two calls")

    def test_a_sound_unit_still_reports_a_verdict(self) -> None:
        """Silence used to mean "nothing wrong", which is the same shape as "not
        assessed". Every unit answers, and `specified` is the answer."""
        assessed = _assess_single_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=_UnitClient({}),
        )

        self.assertEqual([item.verdict for item in assessed], ["specified", "specified"])

    def test_a_verdict_carries_its_unit_and_a_stable_id(self) -> None:
        client = _UnitClient(
            {
                "Efficacy": _answer("vague", ["document:b1"]),
                "Safety": _answer("not_present", []),
            }
        )

        assessed = _assess_single_section(
            section_spec=_section(),
            section_blocks=[_block("document:b1", "Profile")],
            llm_client=client,
        )

        self.assertEqual(
            [(a.section_name, a.variable_name, a.verdict, a.id) for a in assessed],
            [
                ("Profile", "Efficacy", "vague", "Profile|Efficacy"),
                ("Profile", "Safety", "not_present", "Profile|Safety"),
            ],
        )

    def test_a_failed_unit_stops_the_run_rather_than_publishing_a_hole(self) -> None:
        from shared.errors import ModelResponseError

        # Both units fail and they run concurrently, so either may be the one named.
        with self.assertRaisesRegex(ModelResponseError, "could not assess (Efficacy|Safety) in Profile"):
            _assess_single_section(
                section_spec=_section(),
                section_blocks=[_block("document:b1", "Profile")],
                llm_client=_EmptyClient(),
            )

    def test_an_unwritten_section_reports_every_unit_absent(self) -> None:
        """The denominator stays honest instead of collapsing to one line."""
        config = _config([_section(), SectionSpec(name="Timeline", description="Dates")])

        findings, mapped = assess_document(
            [_block("document:b1", "Timeline")],
            config,
            _UnitClient({}),
        )

        # Presence is the mapping: Profile got no blocks, so it is absent.
        self.assertEqual(mapped["Profile"], [])
        self.assertEqual(mapped["Timeline"], ["document:b1"])
        self.assertEqual(
            [(a.variable_name, a.verdict) for a in findings if a.section_name == "Profile"],
            [("Efficacy", "not_present"), ("Safety", "not_present")],
        )


class ParseTests(unittest.TestCase):
    def _parse(self, answer: dict):
        return _parse_unit_payload(
            answer,
            section_name="Profile",
            variable_name="Efficacy",
            optional=False,
            section_blocks=[_block("document:b1", "Profile")],
        )

    def test_a_reported_problem_must_say_where_it_was_read(self) -> None:
        for verdict in ("placeholder", "insufficient", "vague"):
            with self.assertRaisesRegex(ValueError, "without citing a block"):
                self._parse(_answer(verdict, []))

    def test_a_sound_unit_must_say_where_it_read_that(self) -> None:
        """`specified` is a claim about content, so it cites the content."""
        with self.assertRaisesRegex(ValueError, "without citing a block"):
            self._parse(_answer("specified", []))

    def test_absence_cites_nothing_even_when_the_model_offers_a_block(self) -> None:
        self.assertEqual(self._parse(_answer("not_present", ["document:b1"])).cited_block_ids, [])

    def test_an_unknown_block_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown block ID"):
            self._parse(_answer("vague", ["document:b9"]))

    def test_a_shortfall_with_no_statement_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no statement"):
            self._parse(
                {"verdict": "vague", "statement": "", "block_ids": ["document:b1"]}
            )

    def test_a_sound_unit_saying_something_is_quietly_silenced(self) -> None:
        """A model adding "Looks fine." is not a contract failure worth a retry, but
        the sentence is a claim with no defect behind it, so it does not survive."""
        parsed = self._parse(
            {"verdict": "specified", "statement": "Looks fine.", "block_ids": ["document:b1"]}
        )

        self.assertEqual(parsed.statement, "")

    def test_an_unknown_verdict_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self._parse(_answer("unmet", ["document:b1"]))


class CrossSectionTests(unittest.TestCase):
    def _blocks_by_section(self) -> dict[str, list[ContentBlock]]:
        return {
            "Profile": [_block("document:b1", "Profile", 1)],
            "Timeline": [_block("document:b2", "Timeline", 2)],
        }

    def test_a_conflict_must_cite_two_different_sections(self) -> None:
        payload = {"findings": [{"statement": "Conflict.", "block_ids": ["document:b1"]}]}
        with self.assertRaisesRegex(ValueError, "two different sections"):
            _parse_cross_section_payload(payload, self._blocks_by_section())

    def test_the_schema_states_what_the_parser_enforces(self) -> None:
        item = cross_section_schema(self._blocks_by_section())["properties"]["findings"][
            "items"
        ]["properties"]
        self.assertEqual(item["statement"]["minLength"], 1)
        self.assertEqual(item["block_ids"]["minItems"], 2)

    def test_a_spanning_conflict_becomes_a_document_finding(self) -> None:
        payload = {
            "findings": [
                {
                    "statement": "Values conflict.",
                    "block_ids": ["document:b1", "document:b2"],
                }
            ]
        }

        findings = _parse_cross_section_payload(payload, self._blocks_by_section())

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].verdict, "section_conflict")
        self.assertIsNone(findings[0].section_name)
        self.assertTrue(findings[0].needs_work)

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
        check_cross_section(blocks, _config(), Client())

        self.assertEqual(recorded["ids"], ["document:b1", "document:b2"])

    def test_one_mapped_section_makes_the_pass_not_applicable(self) -> None:
        blocks = [_block("document:b1", "Profile", 1), _block("document:b3", "Other", 3)]

        check = check_cross_section(blocks, _config(), _EmptyClient())

        self.assertEqual(tuple(check), ([], "not_applicable", None))

    def test_a_failed_pass_is_reported_rather_than_read_as_clean(self) -> None:
        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]

        check = check_cross_section(blocks, _config(), _EmptyClient())

        self.assertEqual(tuple(check), ([], "failed", "invalid_model_response"))

    def test_a_failed_consistency_answer_is_repaired_with_its_reason(self) -> None:
        sent: list[str] = []

        class OnceWrong:
            def call_structured(self, _system, message, *_args, **_kwargs):
                sent.append(message)
                ids = ["document:b1"] if len(sent) == 1 else ["document:b1", "document:b2"]
                return {"findings": [{"statement": "Efficacy differs.", "block_ids": ids}]}

        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]
        check = check_cross_section(blocks, _config(), OnceWrong())

        self.assertEqual(check.status, "complete")
        self.assertIn("two different sections", sent[1].rsplit("failed the consistency contract", 1)[1])

    def test_a_cut_off_pass_is_recorded_not_raised(self) -> None:
        """The pass runs after every unit is assessed; losing it must not lose them."""
        class Truncating:
            calls = 0

            def call_structured(self, *_args, **_kwargs):
                Truncating.calls += 1
                raise ResponseTruncatedError("cut off")

        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]
        check = check_cross_section(blocks, _config(), Truncating())

        self.assertEqual(tuple(check), ([], "failed", "response_truncated"))
        self.assertEqual(Truncating.calls, 2, "a cut-off answer is retried once")

    def test_a_provider_failure_in_the_pass_is_recorded_not_raised(self) -> None:
        import httpx
        import openai

        class Unreachable:
            def call_structured(self, *_args, **_kwargs):
                raise openai.APIConnectionError(request=httpx.Request("POST", "https://x"))

        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]
        check = check_cross_section(blocks, _config(), Unreachable())

        self.assertEqual(tuple(check), ([], "failed", "provider_error"))

    def test_a_programming_error_in_the_pass_still_raises(self) -> None:
        class Broken:
            def call_structured(self, *_args, **_kwargs):
                raise TypeError("bug")

        blocks = [_block("document:b1", "Profile", 1), _block("document:b2", "Timeline", 2)]
        with self.assertRaises(TypeError):
            check_cross_section(blocks, _config(), Broken())


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
                build_assessment_prompt(),
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


class AbsenceNormalisationTests(unittest.TestCase):
    def _parse(self, answer: dict, *, optional: bool):
        return _parse_unit_payload(
            answer,
            section_name="Profile",
            variable_name="Efficacy",
            optional=optional,
            section_blocks=[_block("document:b1", "Profile")],
        )

    def test_an_optional_absence_has_one_name(self) -> None:
        """The schema never offers `not_present` for an optional unit, so the parser
        refuses it rather than correcting a word the model could not have chosen."""
        with self.assertRaisesRegex(ValueError, "closed vocabulary"):
            self._parse(_answer("not_present", []), optional=True)
        self.assertEqual(self._parse(_answer("not_applicable", []), optional=True).verdict,
                         "not_applicable")

    def test_a_required_unit_cannot_be_called_not_applicable(self) -> None:
        with self.assertRaisesRegex(ValueError, "closed vocabulary"):
            self._parse(_answer("not_applicable", []), optional=False)

    def test_a_required_absence_stays_a_shortfall(self) -> None:
        parsed = self._parse(_answer("not_present", []), optional=False)

        self.assertEqual(parsed.verdict, "not_present")

    def test_the_prompt_says_which_of_the_two_absences_applies(self) -> None:
        prompt = build_assessment_prompt()

        self.assertIn("where the rubric marks the unit optional", prompt)
