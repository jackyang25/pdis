"""The priority reading points at findings; it never copies or decides them.

The tests that matter keep it a pointer: every point names findings by the result's own
IDs, offered as a closed list, and a reply naming anything else is refused whole. The rest
keep the prompt tool-agnostic and every part of a finding labelled for who wrote it.
"""

from __future__ import annotations

import unittest

from services.assistant import (
    PriorityFinding,
    PriorityRequest,
    PriorityRequestTooLarge,
    read_priorities,
)
from services.assistant.priorities import (
    MAX_FINDINGS_CHARACTERS,
    MAX_POINTS,
    build_system_prompt,
    build_user_message,
    reading_schema,
)


class FakeClient:
    def __init__(self, payload: dict | None) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        self.calls.append({"system": system_prompt, "user": user_message, "schema": schema})
        return None if self.payload is None else dict(self.payload)


def finding(id: str = "u-1", **overrides) -> PriorityFinding:
    defaults = dict(
        id=id,
        subject="Primary user groups",
        group="Medical need",
        verdicts=("Insufficient",),
        statements=("The document does not identify them.",),
        notes=("An earlier comparison flagged this passage.",),
        quote="adults at risk",
    )
    defaults.update(overrides)
    return PriorityFinding(**defaults)


def request(**overrides) -> PriorityRequest:
    defaults = dict(
        authority="Reads one document against its authored rubric.",
        focus="Units the rubric requires that the document leaves missing or unclear.",
        findings=(finding("u-1"), finding("u-2", subject="Dosing")),
        org="bmgf",
        intervention_class="monoclonal_antibody",
        indication="tuberculosis",
    )
    defaults.update(overrides)
    return PriorityRequest(**defaults)


def point(**overrides) -> dict:
    return {"title": "Who it is for", "statement": "Two units are open.", "finding_ids": ["u-1"], **overrides}


class ReadingTests(unittest.TestCase):
    def read(self, body: dict | None, **overrides):
        client = FakeClient(body)
        return read_priorities(request(**overrides), llm_client=client), client

    def test_a_reading_returns_its_summary_and_points(self) -> None:
        result, _ = self.read({"summary": "  Most gaps sit\n in one section. ", "points": [point()]})
        self.assertEqual(result.summary, "Most gaps sit in one section.")
        self.assertEqual(result.points[0].finding_ids, ["u-1"])

    def test_paragraph_breaks_survive(self) -> None:
        result, _ = self.read({"summary": "One.\n\n\nTwo.", "points": []})
        self.assertEqual(result.summary, "One.\n\nTwo.")

    def test_no_points_is_a_valid_reading(self) -> None:
        result, _ = self.read({"summary": "Nothing needs attention.", "points": []})
        self.assertEqual(result.points, [])

    def test_repeated_ids_in_a_point_are_kept_once(self) -> None:
        result, _ = self.read({"summary": "S", "points": [point(finding_ids=["u-1", "u-1", "u-2"])]})
        self.assertEqual(result.points[0].finding_ids, ["u-1", "u-2"])

    def test_a_point_naming_an_unknown_finding_refuses_the_reply(self) -> None:
        """A point that opens nothing is a broken reply, not a smaller one."""
        with self.assertRaises(ValueError):
            self.read({"summary": "S", "points": [point(finding_ids=["u-9"])]})

    def test_a_point_without_findings_refuses_the_reply(self) -> None:
        with self.assertRaises(ValueError):
            self.read({"summary": "S", "points": [point(finding_ids=[])]})

    def test_an_empty_summary_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.read({"summary": "  ", "points": []})

    def test_no_structured_answer_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.read(None)

    def test_a_result_with_no_findings_is_not_read(self) -> None:
        with self.assertRaises(ValueError):
            self.read({"summary": "S", "points": []}, findings=())

    def test_an_oversized_result_is_refused_rather_than_truncated(self) -> None:
        big = finding("u-1", statements=("x" * (MAX_FINDINGS_CHARACTERS + 1),))
        with self.assertRaises(PriorityRequestTooLarge):
            build_user_message(request(findings=(big,)))


class SchemaTests(unittest.TestCase):
    def test_points_may_name_only_the_results_findings(self) -> None:
        ids = reading_schema(["u-1", "u-2"])["properties"]["points"]["items"]["properties"]["finding_ids"]
        self.assertEqual(ids["items"]["enum"], ["u-1", "u-2"])
        self.assertEqual(ids["minItems"], 1)

    def test_the_schema_states_what_the_parser_enforces(self) -> None:
        schema = reading_schema(["u-1"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["summary"]["minLength"], 1)
        points = schema["properties"]["points"]
        self.assertEqual(points["maxItems"], MAX_POINTS)
        item = points["items"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(item["properties"]["title"]["minLength"], 1)
        self.assertEqual(item["properties"]["statement"]["minLength"], 1)


class PromptTests(unittest.TestCase):
    def test_the_prompt_names_no_tool_and_no_domain(self) -> None:
        """One prompt serves every tool; a fifth is served by it unchanged."""
        prompt = build_system_prompt().lower()
        for word in (
            "inspector", "aligner", "scout", "screener",
            "itpp", "ctpp", "ipdp", "vaccine", "tuberculosis",
        ):
            self.assertNotIn(word, prompt, word)

    def test_the_prompt_asks_for_no_plain_text_json(self) -> None:
        """The reply is schema-bound; format instructions in prose are a second contract."""
        self.assertNotIn("json", build_system_prompt().lower())

    def test_the_prompt_forbids_overturning_and_scoring(self) -> None:
        prompt = build_system_prompt().lower()
        self.assertIn("never overturn", prompt)
        self.assertIn("do not score", prompt)

    def test_each_part_of_a_finding_is_labelled_for_who_wrote_it(self) -> None:
        message = build_user_message(request())
        self.assertIn("[u-1] Primary user groups", message)
        self.assertIn("  in: Medical need", message)
        self.assertIn("  verdict: Insufficient", message)
        self.assertIn("  document: adults at risk", message)
        self.assertIn("  says: The document does not identify them.", message)
        self.assertIn("  note: An earlier comparison flagged this passage.", message)

    def test_the_prompt_explains_every_label_the_message_uses(self) -> None:
        prompt = build_system_prompt()
        for label in ("`verdict`", "`says`", "`note`", "`document`"):
            self.assertIn(label, prompt)

    def test_the_message_carries_authority_focus_and_domain_in_words(self) -> None:
        message = build_user_message(request())
        self.assertIn("against its authored rubric", message)
        self.assertIn("What to raise first: Units the rubric requires", message)
        # De-underscored, like every other place a context tag becomes text.
        self.assertIn("monoclonal antibody", message)
        self.assertNotIn("monoclonal_antibody", message)


if __name__ == "__main__":
    unittest.main()
