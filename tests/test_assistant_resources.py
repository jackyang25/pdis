"""Everything the agent can reach is declared once and derived everywhere.

A capability used to live in three unconnected places: a hand-written tool schema,
a sentence in the system prompt listing tool names, and nothing at all for what a
reader is shown. The prompt had already drifted — it named `get` and `find` after
those verbs were meant to be siblings of the document and knowledge ones.

These pin that the derivation holds, so a capability cannot be half-added.
"""

from __future__ import annotations

import unittest

from services.assistant import resources, skills
from services.assistant.agent import _system_prompt
from services.assistant.registry import REGISTRY, TOOLS, ToolContext, held_result_types


class RegistryDerivationTests(unittest.TestCase):
    def test_every_declared_verb_is_offered_to_the_model(self) -> None:
        declared = {verb.name for item in REGISTRY for verb in item.verbs}
        offered = {tool["function"]["name"] for tool in TOOLS}
        self.assertEqual(declared, offered)

    def test_every_verb_states_what_a_reader_is_shown(self) -> None:
        # The label ships with the schema, so a new capability cannot arrive
        # with a tool and a blank status line.
        for item in REGISTRY:
            for verb in item.verbs:
                with self.subTest(verb=verb.name):
                    self.assertTrue(verb.activity.strip(), f"{verb.name} has no activity")
                    self.assertTrue(verb.description.strip())

    def test_the_system_prompt_names_exactly_the_verbs_that_exist(self) -> None:
        prompt = _system_prompt({}, "workspace")
        for tool in TOOLS:
            self.assertIn(tool["function"]["name"], prompt)
        # The names the prompt used to hand-list, which no longer exist.
        for stale in ("get(path)", "find(keyword)"):
            self.assertNotIn(stale, prompt)

    def test_two_resources_cannot_claim_one_verb(self) -> None:
        duplicate = (*REGISTRY, REGISTRY[0])
        with self.assertRaisesRegex(ValueError, "two resources declare"):
            resources.verbs_by_name(duplicate)

    def test_a_resource_without_verbs_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "no verbs"):
            resources.Resource(key="empty", summary="", kind="evidence")

    def test_procedure_is_marked_apart_from_evidence(self) -> None:
        # Same access shape, different meaning: a workflow read like a finding
        # would be quoted to the user as though it were one.
        inventory = resources.inventory(REGISTRY)
        self.assertIn("never evidence to cite", inventory)
        kinds = {item.key: item.kind for item in REGISTRY}
        self.assertEqual(kinds["skill"], "procedure")
        self.assertEqual(kinds["result"], "evidence")


class HeldResultTests(unittest.TestCase):
    def test_what_the_workspace_holds_is_read_from_the_bundle(self) -> None:
        bundle = {"results": [{"result_type": "aligner"}, {"result_type": "scout"}]}
        self.assertEqual(held_result_types(bundle), frozenset({"aligner", "scout"}))

    def test_a_single_result_context_holds_nothing_to_combine(self) -> None:
        self.assertEqual(held_result_types({"matches": []}), frozenset())


class SkillContractTests(unittest.TestCase):
    def test_a_skill_declares_what_it_needs(self) -> None:
        for skill in skills.available_skills():
            with self.subTest(skill=skill.name):
                self.assertTrue(
                    skill.requires or skill.requires_any,
                    f"{skill.name} declares nothing it needs",
                )
                for required in (*skill.requires, *skill.requires_any):
                    self.assertIn(required, skills.KNOWN_RESULT_TYPES)

    def test_a_skill_needing_nothing_at_all_fails_at_load(self) -> None:
        """A workflow offered against a workspace it cannot read is a dead end."""
        with self.assertRaisesRegex(ValueError, "declares nothing it needs"):
            skills.Skill(name="x", description="d", requires=(), body="do it")

    def test_requires_is_every_one_and_requires_any_is_one_of(self) -> None:
        """Two kinds of workflow: a specific combination, and whatever is held.

        A pairing says something neither result says alone, so it needs both. A workflow
        that turns a result into a paragraph applies to any of them, and declaring that
        with `requires` would mean naming one tool arbitrarily or writing near-identical
        files per tool, each costing a line of the always-resident index.
        """
        pairing = skills.Skill(
            name="pairing", description="d", requires=("aligner", "scout"), body="b"
        )
        self.assertEqual(pairing.missing_from(frozenset({"aligner"})), ["scout"])
        self.assertEqual(pairing.missing_from(frozenset({"aligner", "scout"})), [])

        general = skills.Skill(
            name="general",
            description="d",
            requires=(),
            body="b",
            requires_any=("inspector", "expert"),
        )
        self.assertEqual(general.missing_from(frozenset({"expert"})), [])
        self.assertEqual(
            general.missing_from(frozenset({"scout"})), ["inspector or expert"]
        )

    def test_an_unknown_result_type_fails_at_load(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown result type"):
            skills.Skill(
                name="x", description="d", requires=("nosuchtool",), body="do it"
            )

    def test_no_skill_names_a_vocabulary_that_was_retired(self) -> None:
        """A skill is prose, so a moved contract does not break it — it misleads.

        `compare-drift-against-evidence` went on instructing the model to read Aligner's
        `links` and filter for `modified` relations for a whole redesign after both were
        deleted. Nothing failed: no import, no type, no test touched it, and every other
        dependency of that redesign was caught because code referenced it.

        Only backticked words are checked. In a skill body those are identifiers, where
        the same words in a sentence are ordinary English — `missing` and `conflict` are
        live Inspector reasons and are deliberately absent from this list.
        """
        retired = {
            "links": "Aligner returns `findings`, one per requirement",
            "aligned": "Aligner's verdicts are meets/exceeds/falls_short/"
            "not_comparable/not_addressed",
            "modified": "a symmetric relation; the verdicts replaced it",
            "introduced": "a symmetric relation; the verdicts replaced it",
            "not_answerable": "Expert's states are answered/partly_answered/"
            "not_found/not_applicable",
            "not_assessable": "Expert's states are answered/partly_answered/"
            "not_found/not_applicable",
        }
        for skill in skills.available_skills():
            for token, replacement in retired.items():
                with self.subTest(skill=skill.name, token=token):
                    self.assertNotIn(
                        f"`{token}`",
                        skill.body,
                        f"{skill.name} names retired `{token}`: {replacement}",
                    )

    def test_the_catalog_says_which_run_is_missing(self) -> None:
        # A user asking for a workflow they cannot run should be told what to
        # run, not that the workflow does not exist.
        listing = skills.catalog({"aligner"})
        self.assertIn("compare-drift-against-evidence", listing)
        self.assertIn("needs a scout result", listing)

    def test_the_catalog_marks_a_workflow_ready(self) -> None:
        self.assertIn("ready", skills.catalog({"aligner", "scout"}))

    def test_the_catalog_offers_a_general_workflow_on_one_result(self) -> None:
        listing = skills.catalog({"inspector"})
        self.assertIn("write-the-review-summary: ", listing)
        self.assertNotIn("write-the-review-summary: <", listing)
        for line in listing.splitlines():
            if line.startswith("- write-the-review-summary"):
                self.assertIn("ready", line)

    def test_reading_an_unknown_workflow_names_the_real_ones(self) -> None:
        message = skills.read_skill("no-such-workflow")
        self.assertIn("compare-drift-against-evidence", message)



class SystemPromptTests(unittest.TestCase):
    """The prompt is assembled from sections, and two of them are conditional.

    Both import bugs found while splitting this module were in the branch that
    only runs when a document is present, and no test passed one — so the prompt
    built fine in every test and would have raised in front of a user.
    """

    DOCUMENT = [
        {
            "id": "d/b1",
            "doc_id": "d",
            "ordinal": 1,
            "block_type": "paragraph",
            "content": "Efficacy >= 80%",
            "heading_stack": [],
            "structural_meta": {},
            "style_hint": {},
            "section_label": "Profile",
        }
    ]

    def test_the_prompt_builds_with_a_document(self) -> None:
        prompt = _system_prompt({"matches": []}, "scout", self.DOCUMENT)
        self.assertIn("SOURCE DOCUMENT MAP", prompt)
        self.assertIn("DOCUMENT ACCESS", prompt)

    def test_the_prompt_builds_without_one(self) -> None:
        prompt = _system_prompt({"results": []}, "workspace")
        # An absent section drops out rather than leaving an empty heading.
        self.assertNotIn("SOURCE DOCUMENT MAP", prompt)
        self.assertNotIn("DOCUMENT ACCESS", prompt)
        self.assertNotIn("\n\n\n", prompt)

    def test_answering_rules_are_checkable_rather_than_vague(self) -> None:
        prompt = _system_prompt({"results": []}, "workspace")
        self.assertIn("Lead with the answer", prompt)
        # Only safe to ask for a table since the assistant renders GFM; before
        # that it arrived as raw pipes.
        self.assertIn("Use a table when comparing", prompt)
        # The citation rule governs backing a claim; a list of blocks backs
        # nothing, so naming one has to be its own instruction.
        self.assertIn("Any time you name a document block", prompt)
        self.assertNotIn("Be concise and specific", prompt)

    def test_every_citation_kind_is_expressed_one_way(self) -> None:
        # A markdown link for anything openable, so the renderer parses a link
        # rather than hunting for identifiers in prose. web/lib/citation.ts is
        # the other half of this contract.
        prompt = _system_prompt({"results": []}, "workspace")
        self.assertIn("always as a markdown link", prompt)
        self.assertIn("(https://the-source-url)", prompt)
        # Bracketed: a block ID carries the document name, and a name with
        # spaces is not a valid link destination without them.
        self.assertIn("(<block:EXACT-BLOCK-ID>)", prompt)
        # A result path is not openable, so it is quoted rather than linked.
        self.assertIn("in backticks, not a link", prompt)
        # The label is the readable part, the destination the exact one.
        self.assertIn("visible text is for the reader", prompt)


class EveryVerbRunsTests(unittest.TestCase):
    """Each declared handler is actually callable.

    Three broken references survived the split into registry/agent because the
    suite checked that verbs were *declared*, never that one could *run*. The
    schemas were right and the code behind two of them raised NameError.
    """

    def context(self) -> ToolContext:
        return ToolContext(
            result={"results": [], "matches": []},
            allowed_urls=set(),
            document=None,
            held_result_types=frozenset(),
        )

    MINIMAL_ARGS = {
        "keyword": "efficacy",
        "section_ids": ["overview"],
        "path": "",
        "block_ids": ["d/b1"],
        "doc_id": "d",
        "url": "https://example.org/paper",
        "name": "compare-drift-against-evidence",
    }

    def test_every_declared_verb_can_be_invoked(self) -> None:
        context = self.context()
        for item in REGISTRY:
            for verb in item.verbs:
                with self.subTest(verb=verb.name):
                    args = {
                        key: value
                        for key, value in self.MINIMAL_ARGS.items()
                        if key in verb.parameters.get("properties", {})
                    }
                    outcome = verb.handler(context, args)
                    self.assertIsInstance(
                        outcome, str, f"{verb.name} did not return text"
                    )

    def test_a_verb_handles_arguments_the_model_got_wrong(self) -> None:
        # Arguments are model output, so a list field can arrive as a string.
        context = self.context()
        read_docs = {v.name: v for i in REGISTRY for v in i.verbs}["read_product_docs"]
        self.assertIsInstance(read_docs.handler(context, {"section_ids": "oops"}), str)


class WorkflowVisibilityTests(unittest.TestCase):
    """The index is resident; only the bodies are fetched.

    A workflow behind a tool call is one the agent has no reason to look for —
    it would have to speculatively list them on the chance something applies.
    The names and descriptions are cheap, so they are always present; the
    procedures are not, so they are not.
    """

    def test_the_prompt_names_every_available_workflow(self) -> None:
        prompt = _system_prompt({"results": []}, "workspace")
        for skill in skills.available_skills():
            with self.subTest(skill=skill.name):
                self.assertIn(skill.name, prompt)
                self.assertIn(skill.description, prompt)

    def test_the_prompt_says_which_run_a_workflow_still_needs(self) -> None:
        prompt = _system_prompt(
            {"results": [{"result_type": "aligner"}]}, "workspace"
        )
        self.assertIn("needs a scout result", prompt)

    def test_a_workflow_the_workspace_can_run_is_marked_ready(self) -> None:
        prompt = _system_prompt(
            {"results": [{"result_type": "aligner"}, {"result_type": "scout"}]},
            "workspace",
        )
        self.assertIn("ready", prompt)

    def test_the_procedure_itself_stays_out_of_the_prompt(self) -> None:
        # The body is bespoke and long; paying for it on every message is what
        # reading it on demand avoids.
        prompt = _system_prompt({"results": []}, "workspace")
        for skill in skills.available_skills():
            with self.subTest(skill=skill.name):
                self.assertNotIn(skill.body, prompt)


class SkillPrecedenceTests(unittest.TestCase):
    """A skill may contradict the general shape rules, and one of them has to win.

    `write-the-review-summary` forbids citations because its output is a passage
    meant to be pasted into someone else's document; ANSWERING requires block IDs
    to be links. Both are right for their scope, so leaving precedence unstated
    left the agent holding two instructions and picking by weight.
    """

    def test_a_skill_governs_the_answer_it_produces(self) -> None:
        prompt = _system_prompt({"results": []}, "workspace")
        self.assertIn("the skill wins for the answer it governs", prompt)

    def test_grounding_is_never_overridable(self) -> None:
        # The one rule a workflow must not be able to relax: a skill that
        # licensed stating what the context does not support would be a way to
        # write invention into a file and have it obeyed.
        prompt = _system_prompt({"results": []}, "workspace")
        self.assertIn("never overrides GROUNDING", prompt)

    def test_the_conflict_this_exists_for_is_real(self) -> None:
        # Not hypothetical: a shipped skill contradicts a shipped rule.
        summary = next(
            (item for item in skills.available_skills()
             if item.name == "write-the-review-summary"),
            None,
        )
        if summary is None:
            self.skipTest("the summary workflow is no longer shipped")
        self.assertIn("no citations", summary.body.casefold())
        self.assertIn("write it as a link", _system_prompt({"results": []}, "workspace"))

if __name__ == "__main__":
    unittest.main()
