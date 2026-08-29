"""What Aligner guarantees.

Two halves. The first is the surface every tool shares: config that keeps document types
and document counts out of code, the comparisons a set of documents resolves, the result
envelope, the structural contract.

The second is the comparison itself, and what it must never do. A comparison here runs
one way — the reference document's requirements are the bar, the other document is
measured against them — so the tests that matter most are the ones that would catch it
becoming symmetric again: a verdict citing the document that set the bar, a
`falls_short` with no account of the shortfall, an `exceeds` treated as interchangeable
with it.
"""

from __future__ import annotations

import tempfile
import unittest

from services.aligner import describe_document, describe_edges, load_config, resolve_edges
from services.aligner.contract import validate_result_contract
from services.aligner.models import (
    ALIGNMENT_VERDICTS,
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentFinding,
    AlignmentResult,
    EdgeSpec,
    Requirement,
    edge_id,
    requirement_id,
)
from services.aligner.prompt_catalog import PROMPT_CATALOG
from services.aligner.stages.assessor import (
    assess_requirement,
    assessment_schema,
    build_assessment_prompt,
    build_user_message,
)
from services.aligner.stages.requirements import extract_requirements
from services.chunker import ContentBlock
from shared.spans import DocumentSpan

CONFIG = """
document_roles:
  itpp: A profile.
  ctpp: A candidate.
  ipdp: A plan.
  default: A document.
edges:
  - reference: itpp
    comparison: ctpp
    question: Does the candidate meet the bar?
  - reference: ctpp
    comparison: ipdp
    question: Does the plan deliver it?
"""


def write_config(body: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    with handle:
        handle.write(body)
    return handle.name


def doc(source_type: str, doc_id: str | None = None) -> AlignmentDocument:
    return AlignmentDocument(
        doc_id=doc_id or f"{source_type}_file",
        source_type=source_type,
        display_name=source_type.upper(),
    )


def block(block_id: str, doc_id: str, ordinal: int = 0) -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id=doc_id,
        ordinal=ordinal,
        block_type="paragraph",
        content=f"Content of {block_id}.",
        heading_stack=[],
        structural_meta={},
        style_hint={},
    )


def result(
    documents: list[AlignmentDocument] | None = None,
    edges: list[AlignmentEdge] | None = None,
    blocks: list[ContentBlock] | None = None,
    findings: list["AlignmentFinding"] | None = None,
) -> AlignmentResult:
    documents = documents if documents is not None else [doc("itpp"), doc("ctpp")]
    return AlignmentResult(
        documents=documents,
        edges=edges
        if edges is not None
        else [
            AlignmentEdge(
                "itpp-to-ctpp",
                "itpp_file",
                "ctpp_file",
                "Does the candidate meet the bar?",
            )
        ],
        org="bmgf",
        intervention_class="vaccine",
        indication="malaria",
        blocks=blocks
        if blocks is not None
        else [block(f"{document.doc_id}:b1", document.doc_id) for document in documents],
        findings=findings or [],
    )


class ConfigTests(unittest.TestCase):
    def test_the_config_carries_no_analysis_vocabulary(self) -> None:
        """Roles and pairings only, so nothing constrains what the next design says."""
        self.assertEqual(list(vars(load_config())), ["document_roles", "edges"])

    def test_a_source_type_the_config_never_names_still_resolves(self) -> None:
        """A document the chunker learns to parse is describable before anyone names it."""
        config = load_config()
        self.assertNotIn("launch_plan", config.document_roles)
        self.assertEqual(
            describe_document(config, "launch_plan"), config.document_roles["default"]
        )

    def test_a_named_source_type_gets_its_own_description(self) -> None:
        config = load_config()
        self.assertNotEqual(
            describe_document(config, "itpp"), describe_document(config, "ipdp")
        )

    def test_the_shipped_config_declares_the_two_comparisons(self) -> None:
        """The chain, not a mesh: there is deliberately no itpp/ipdp pair."""
        self.assertEqual(
            [(spec.reference, spec.comparison) for spec in load_config().edges],
            [("itpp", "ctpp"), ("ctpp", "ipdp")],
        )

    def test_a_config_without_a_default_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "must define `default`"):
            load_config(write_config("document_roles:\n  itpp: A profile.\nedges: []\n"))

    def test_an_empty_role_description_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty strings"):
            load_config(write_config("document_roles:\n  default: '   '\nedges: []\n"))

    def test_a_config_with_no_comparison_is_refused(self) -> None:
        """A tool that compares nothing would parse two documents and stop."""
        with self.assertRaisesRegex(ValueError, "edges must be a non-empty list"):
            load_config(write_config("document_roles:\n  default: A document.\nedges: []\n"))

    def test_an_edge_naming_an_undeclared_type_is_refused(self) -> None:
        """A typo here would resolve to nothing at run time rather than fail."""
        body = CONFIG.replace("comparison: ipdp", "comparison: idpp")
        with self.assertRaisesRegex(ValueError, "document_roles does not declare"):
            load_config(write_config(body))

    def test_an_edge_comparing_a_type_with_itself_is_refused(self) -> None:
        """Two revisions of one document is a different question, not this one."""
        body = CONFIG.replace("comparison: ctpp\n    question: Does the candidate meet the bar?",
                              "comparison: itpp\n    question: Did it change?")
        with self.assertRaisesRegex(ValueError, "compares itpp with itself"):
            load_config(write_config(body))

    def test_a_repeated_pair_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "more than once"):
            load_config(write_config(CONFIG + """  - reference: itpp
    comparison: ctpp
    question: Asked twice.
"""))


class ResolveEdgeTests(unittest.TestCase):
    """The one place a document count exists, and it is derived rather than set."""

    def setUp(self) -> None:
        self.config = load_config(write_config(CONFIG))

    def test_two_documents_resolve_one_comparison(self) -> None:
        edges = resolve_edges(self.config, [doc("itpp"), doc("ctpp")])
        self.assertEqual(
            [(edge.reference_doc_id, edge.comparison_doc_id) for edge in edges],
            [("itpp_file", "ctpp_file")],
        )

    def test_three_documents_resolve_two_comparisons(self) -> None:
        """Adding the third document adds a comparison with no code change."""
        edges = resolve_edges(self.config, [doc("itpp"), doc("ctpp"), doc("ipdp")])
        self.assertEqual(
            [(edge.reference_doc_id, edge.comparison_doc_id) for edge in edges],
            [("itpp_file", "ctpp_file"), ("ctpp_file", "ipdp_file")],
        )

    def test_upload_order_does_not_change_the_comparisons(self) -> None:
        """Direction comes from the config, never from which file arrived first."""
        forwards = resolve_edges(self.config, [doc("itpp"), doc("ctpp")])
        backwards = resolve_edges(self.config, [doc("ctpp"), doc("itpp")])
        self.assertEqual(forwards, backwards)

    def test_an_edge_carries_the_question_its_config_declared(self) -> None:
        edge = resolve_edges(self.config, [doc("ctpp"), doc("ipdp")])[0]
        self.assertEqual(edge.question, "Does the plan deliver it?")

    def test_documents_forming_no_declared_pair_are_refused(self) -> None:
        """iTPP with IPDP skips the candidate, so the config declares no pair."""
        with self.assertRaisesRegex(ValueError, "no comparison declared"):
            resolve_edges(self.config, [doc("itpp"), doc("ipdp")])

    def test_the_refusal_names_what_it_would_have_compared(self) -> None:
        with self.assertRaisesRegex(ValueError, "itpp to ctpp, ctpp to ipdp"):
            resolve_edges(self.config, [doc("itpp"), doc("ipdp")])

    def test_two_documents_of_one_type_are_refused(self) -> None:
        """Screening several candidates at once is a different tool, not this one."""
        with self.assertRaisesRegex(ValueError, "two documents of the same type"):
            resolve_edges(self.config, [doc("ctpp", "a"), doc("ctpp", "b")])

    def test_describe_edges_reads_the_config(self) -> None:
        self.assertEqual(describe_edges(self.config), "itpp to ctpp, ctpp to ipdp")


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()

    def test_a_valid_result_is_returned_rather_than_dropped(self) -> None:
        """The validator this replaced returned None, so `run_pipeline` did too."""
        original = result()
        self.assertIs(validate_result_contract(original, self.config), original)

    def test_one_document_cannot_be_a_comparison(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one comparison"):
            validate_result_contract(result(edges=[]), self.config)

    def test_duplicate_document_ids_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "document IDs must be distinct"):
            validate_result_contract(
                result(documents=[doc("itpp", "same"), doc("ctpp", "same")]), self.config
            )

    def test_two_documents_of_one_type_are_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "two documents of the same type"):
            validate_result_contract(
                result(documents=[doc("ctpp", "a"), doc("ctpp", "b")]), self.config
            )

    def test_a_comparison_naming_an_absent_document_is_refused(self) -> None:
        """It would render as a blank side rather than as the error it is."""
        with self.assertRaisesRegex(ValueError, "not in this result"):
            validate_result_contract(
                result(edges=[AlignmentEdge("itpp-to-absent", "itpp_file", "absent", "?")]),
                self.config,
            )

    def test_a_comparison_must_state_what_it_asks(self) -> None:
        with self.assertRaisesRegex(ValueError, "must state what it asks"):
            validate_result_contract(
                result(edges=[AlignmentEdge("itpp-to-ctpp", "itpp_file", "ctpp_file", "  ")]),
                self.config,
            )

    def test_duplicate_block_ids_are_refused(self) -> None:
        """Two blocks under one ID would make a citation ambiguous."""
        with self.assertRaisesRegex(ValueError, "block IDs must be unique"):
            validate_result_contract(
                result(blocks=[block("b1", "itpp_file"), block("b1", "ctpp_file", 1)]),
                self.config,
            )

    def test_a_block_from_no_document_in_the_run_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown document"):
            validate_result_contract(result(blocks=[block("x:b1", "other")]), self.config)

    def test_a_result_with_no_blocks_is_accepted(self) -> None:
        """An empty document is a parse outcome, not a contract violation."""
        empty = result(blocks=[])
        self.assertIs(validate_result_contract(empty, self.config), empty)

    def test_a_config_missing_its_default_cannot_validate(self) -> None:
        broken = AlignmentConfig(
            document_roles={"itpp": "A profile."},
            edges=[EdgeSpec("itpp", "ctpp", "?")],
        )
        with self.assertRaises(KeyError):
            validate_result_contract(result(), broken)


class PromptCatalogTests(unittest.TestCase):
    def test_both_stages_declare_their_prompt(self) -> None:
        """A prompt nothing publishes is a prompt nobody can review."""
        self.assertEqual(
            [entry.stage for entry in PROMPT_CATALOG],
            ["requirements", "compare"],
        )

    def test_every_declared_prompt_renders(self) -> None:
        for entry in PROMPT_CATALOG:
            self.assertTrue(entry.render().strip(), entry.id)

    def test_neither_prompt_declares_a_framing_slot(self) -> None:
        """The edge's question is per-requirement material, not prompt framing.

        It reaches the model in the user message, as Screener's questions do, so the
        published system prompt is the whole of what every edge is told.
        """
        for entry in PROMPT_CATALOG:
            self.assertIsNone(entry.framing_slot, entry.id)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# The comparison
# ---------------------------------------------------------------------------

EDGE = edge_id("itpp", "ctpp")


class FakeClient:
    """Answers every call the same way, recording what it was asked."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        self.calls.append({
            "system": system_prompt,
            "user": user_message,
            "schema": schema,
            "schema_name": schema_name,
        })
        return dict(self.payload)


def picked(block_id: str, start: int = 1, end: int = 1) -> dict:
    """One selected line range, as a model returns it: an address, never text."""
    return {"block_id": block_id, "start_line": start, "end_line": end}


def cited(block_id: str) -> DocumentSpan:
    """The span `picked` resolves to, given `block`'s single-line content."""
    return DocumentSpan(quote=f"Content of {block_id}.", block_ids=[block_id])


def requirement(text: str = "Annual dosing.", blocks: tuple[str, ...] = ("itpp_file:b1",)):
    return Requirement(
        id=requirement_id(EDGE, 1),
        text=text,
        cited_spans=tuple(cited(block_id) for block_id in blocks),
    )


def judge(payload: dict, blocks: list[ContentBlock] | None = None) -> AlignmentFinding:
    return assess_requirement(
        requirement(),
        edge_id=EDGE,
        role="A candidate.",
        question="Does the candidate meet the bar?",
        blocks=blocks if blocks is not None else [block("ctpp_file:b1", "ctpp_file")],
        llm_client=FakeClient(payload),
        max_tokens=1000,
    )


class RequirementExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.blocks = [
            block("itpp_file:b1", "itpp_file"),
            block("itpp_file:b2", "itpp_file", ordinal=1),
        ]

    def extract(self, payload: dict) -> list[Requirement]:
        return extract_requirements(
            edge_id=EDGE,
            role="A profile.",
            question="Does the candidate meet the bar?",
            blocks=self.blocks,
            llm_client=FakeClient(payload),
            max_tokens=1000,
        )

    def test_requirements_are_numbered_within_their_comparison(self) -> None:
        """The ID says which comparison it belongs to without resolving a document."""
        found = self.extract({
            "requirements": [
                {"text": "Annual dosing.", "spans": [picked("itpp_file:b1")]},
                {"text": "Shelf life of 36 months.", "spans": [picked("itpp_file:b2")]},
            ]
        })
        self.assertEqual(
            [item.id for item in found],
            ["itpp-to-ctpp/r-001", "itpp-to-ctpp/r-002"],
        )
        self.assertEqual(found[1].cited_spans, (cited("itpp_file:b2"),))

    def test_the_same_requirement_stated_twice_is_one_requirement(self) -> None:
        """A duplicate would double-count in every total computed from the list."""
        found = self.extract({
            "requirements": [
                {"text": "Annual dosing.", "spans": [picked("itpp_file:b1")]},
                {"text": "annual   dosing.", "spans": [picked("itpp_file:b2")]},
            ]
        })
        self.assertEqual(len(found), 1)

    def test_an_uncited_requirement_is_refused(self) -> None:
        """A bar nobody can check is worse than a bar nobody wrote down."""
        with self.assertRaises(ValueError):
            self.extract({"requirements": [{"text": "Annual dosing.", "spans": []}]})

    def test_a_requirement_citing_an_unknown_block_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.extract({
                "requirements": [
                    {"text": "Annual dosing.", "spans": [picked("ctpp_file:b1")]}
                ]
            })

    def test_an_empty_extraction_is_a_failure_not_an_answer(self) -> None:
        """No requirements means the read failed; it does not mean nothing is asked."""
        with self.assertRaises(ValueError):
            self.extract({"requirements": []})

    def test_the_schema_offers_only_the_reference_document_blocks(self) -> None:
        client = FakeClient({
            "requirements": [{"text": "Annual dosing.", "spans": [picked("itpp_file:b1")]}]
        })
        extract_requirements(
            edge_id=EDGE,
            role="A profile.",
            question="?",
            blocks=self.blocks,
            llm_client=client,
            max_tokens=1000,
        )
        schema = client.calls[0]["schema"]
        offered = schema["properties"]["requirements"]["items"]["properties"]
        self.assertEqual(
            offered["spans"]["items"]["properties"]["block_id"]["enum"],
            ["itpp_file:b1", "itpp_file:b2"],
        )


class VerdictTests(unittest.TestCase):
    def test_meeting_the_bar_cites_the_document_that_was_measured(self) -> None:
        finding = judge({
            "verdict": "meets",
            "statement": "The candidate states annual dosing.",
            "spans": [picked("ctpp_file:b1")],
        })
        self.assertEqual(finding.verdict, "meets")
        self.assertEqual(finding.comparison_spans, [cited("ctpp_file:b1")])
        # Carried from the requirement, so the bar stays checkable beside the verdict.
        self.assertEqual(finding.reference_spans, [cited("itpp_file:b1")])
        self.assertEqual(finding.requirement, "Annual dosing.")
        self.assertEqual(finding.edge_id, EDGE)

    def test_exceeding_and_falling_short_are_different_verdicts(self) -> None:
        """The whole reason the old vocabulary went: one label for both directions."""
        better = judge({
            "verdict": "exceeds",
            "statement": "The candidate states dosing every two years.",
            "spans": [picked("ctpp_file:b1")],
        })
        worse = judge({
            "verdict": "falls_short",
            "statement": "The candidate states dosing every six months.",
            "spans": [picked("ctpp_file:b1")],
        })
        self.assertNotEqual(better.verdict, worse.verdict)

    def test_a_finding_carries_one_sentence_and_no_second(self) -> None:
        """`gap` restated the requirement, which the row already shows.

        It was asked to name the distance from the bar, and the distance is not a third
        fact - it is the requirement and the statement, both of which a reader has. What
        came back said so: "Pregnant women 24-36 weeks required versus at least 28 weeks
        offered", under a heading reading "the minimum target is pregnant women 24-36
        weeks" and a statement reading "the candidate sets at least 28 weeks".
        """
        self.assertNotIn("gap", AlignmentFinding.__dataclass_fields__)
        finding = judge({
            "verdict": "falls_short",
            "statement": "The candidate states dosing every six months.",
            "spans": [picked("ctpp_file:b1")],
        })
        self.assertEqual(finding.statement, "The candidate states dosing every six months.")

    def test_the_prompt_asks_for_one_sentence_and_says_why(self) -> None:
        """A model told only "do not restate" restated anyway, sixty-nine times."""
        prompt = build_assessment_prompt()

        self.assertIn("the only sentence you write", prompt)
        self.assertIn("do not name the distance between the two", prompt)

    def test_silence_cites_nothing(self) -> None:
        """The one verdict about the absence of text, so there is no passage to point at."""
        finding = judge({
            "verdict": "not_addressed",
            "statement": "The candidate states nothing about dosing interval.",
            "spans": [],
        })
        self.assertEqual(finding.comparison_spans, [])
        with self.assertRaises(ValueError):
            judge({
                "verdict": "not_addressed",
                "statement": "Nothing.",
                "spans": [picked("ctpp_file:b1")],
            })

    def test_a_verdict_must_carry_a_statement(self) -> None:
        with self.assertRaises(ValueError):
            judge({
                "verdict": "meets",
                "statement": "  ",
                "spans": [picked("ctpp_file:b1")],
            })

    def test_an_unknown_verdict_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge({
                "verdict": "modified",
                "statement": "The candidate differs.",
                "spans": [picked("ctpp_file:b1")],
            })

    def test_the_schema_offers_only_the_measured_document_blocks(self) -> None:
        """A verdict cannot be justified by citing the document that set the bar."""
        schema = assessment_schema([block("ctpp_file:b1", "ctpp_file")])
        self.assertEqual(
            schema["properties"]["spans"]["items"]["properties"]["block_id"]["enum"],
            ["ctpp_file:b1"],
        )
        self.assertEqual(schema["properties"]["verdict"]["enum"], list(ALIGNMENT_VERDICTS))

    def test_the_document_comes_before_the_requirement_in_the_message(self) -> None:
        """Every requirement on an edge sees the same document, so it is a cacheable
        prefix only when it comes first."""
        message = build_user_message(
            requirement(),
            "A candidate.",
            "Does the candidate meet the bar?",
            [block("ctpp_file:b1", "ctpp_file")],
        )
        self.assertLess(message.index("ctpp_file:b1"), message.index("Annual dosing."))

    def test_the_reference_document_is_not_in_the_message(self) -> None:
        """Only the one requirement crosses over; the bar's own text is its citation."""
        message = build_user_message(
            requirement(),
            "A candidate.",
            "?",
            [block("ctpp_file:b1", "ctpp_file")],
        )
        self.assertNotIn("itpp_file:b1", message)


class FindingContractTests(unittest.TestCase):
    """The contract is the last place a comparison's direction can be enforced."""

    def setUp(self) -> None:
        self.config = load_config(write_config(CONFIG))

    def finding(self, **overrides) -> AlignmentFinding:
        defaults = dict(
            requirement_id=requirement_id(EDGE, 1),
            edge_id=EDGE,
            requirement="Annual dosing.",
            reference_spans=[cited("itpp_file:b1")],
            verdict="meets",
            statement="The candidate states annual dosing.",
            comparison_spans=[cited("ctpp_file:b1")],
        )
        defaults.update(overrides)
        return AlignmentFinding(**defaults)

    def validate(self, *findings: AlignmentFinding) -> AlignmentResult:
        return validate_result_contract(
            result(findings=list(findings)), self.config
        )

    def test_a_well_formed_finding_passes(self) -> None:
        self.assertEqual(len(self.validate(self.finding()).findings), 1)

    def test_a_verdict_citing_the_document_that_set_the_bar_is_refused(self) -> None:
        """The direction of the comparison, enforced on the way out."""
        with self.assertRaises(ValueError):
            self.validate(self.finding(comparison_spans=[cited("itpp_file:b1")]))

    def test_a_requirement_citing_the_measured_document_is_refused(self) -> None:
        """The mirror image: the bar has to be stated where the bar is stated."""
        with self.assertRaises(ValueError):
            self.validate(self.finding(reference_spans=[cited("ctpp_file:b1")]))

    def test_a_requirement_with_no_citation_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(reference_spans=[]))

    def test_one_requirement_cannot_have_two_verdicts(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(), self.finding(verdict="falls_short"))

    def test_a_finding_must_belong_to_a_comparison_this_run_made(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(edge_id="ctpp-to-ipdp"))

    def test_the_citation_rule_is_enforced_in_both_directions(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(verdict="meets", comparison_spans=[]))
        with self.assertRaises(ValueError):
            self.validate(
                self.finding(
                    verdict="not_addressed",
                    statement="Nothing.",
                    comparison_spans=[cited("ctpp_file:b1")],
                )
            )

    def test_a_finding_must_state_what_the_document_says(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(statement=" "))


class HonouringTests(unittest.TestCase):
    """What satisfying a requirement means depends on the kind of document.

    The verdicts were worded for value-against-value: "this document states something
    that satisfies the requirement". Run a plan through that and it fails by
    construction - a plan honours a stability commitment by scheduling a stability
    study, not by stating a temperature - so an IPDP with the work for a commitment was
    filed as saying nothing about it.

    The config already describes each document type and that description already reached
    the prompt; it just was not allowed to change what the verdicts meant.
    """

    def test_the_prompt_says_a_plan_honours_by_carrying_the_work(self) -> None:
        prompt = build_assessment_prompt()

        self.assertIn("CONTAINING THE WORK", prompt)
        self.assertIn("STATING A VALUE", prompt)
        self.assertIn("states no value of its own", prompt)

    def test_the_prompt_refuses_sufficiency(self) -> None:
        """The one word that turns this into Scout's question."""
        prompt = build_assessment_prompt()

        self.assertIn("Judge presence, never sufficiency", prompt)
        self.assertIn("is not what you are being asked", prompt)

    def test_the_document_kind_reaches_the_model(self) -> None:
        """The role is the only thing that says which test applies."""
        message = build_user_message(
            Requirement(id="r-1", text="Stability at 4C.", cited_spans=(cited("itpp_file:b1"),)),
            "Integrated product development plan describing execution and decision pathways.",
            "Does the plan deliver what the candidate profile commits to?",
            [ContentBlock(
                id="ctpp_file:b1", doc_id="ctpp_file", ordinal=1, block_type="paragraph",
                content="A 24-month stability study runs from Q3.", heading_stack=[],
                structural_meta={}, style_hint={}, section_label=None,
            )],
        )

        self.assertIn("Integrated product development plan", message)

    def test_silence_states_nothing(self) -> None:
        """The sentence was the verdict again, under a heading naming the requirement."""
        finding = judge({
            "verdict": "not_addressed",
            "statement": "The candidate states nothing about dosing interval.",
            "spans": [],
        })

        self.assertEqual(finding.statement, "")

    def test_every_other_verdict_must_still_say_what_the_document_does(self) -> None:
        with self.assertRaises(ValueError):
            judge({"verdict": "meets", "statement": "", "spans": [picked("ctpp_file:b1")]})


class ExactQuotationTests(unittest.TestCase):
    """A citation carries the sentence, and the model never types it.

    Aligner used to cite blocks only, so the trace shaded whole passages: on a target
    table that is three hundred words highlighted to show where one row was read. Scout
    had solved this and Aligner had not, which is the whole reason `shared.spans` exists.

    The rule that makes a quote worth trusting is that it is never typed. The model
    selects a `block_id` and a line range out of the line-labelled view, and code copies
    those lines. Asked to quote, a model paraphrases, normalises a unit, or silently fixes
    a typo, and what comes back appears in no document; it cannot do that with a range,
    because a range is not text.
    """

    def multiline(self) -> ContentBlock:
        return ContentBlock(
            id="itpp_file:table",
            doc_id="itpp_file",
            ordinal=0,
            block_type="table",
            content=(
                "Shelf life | 36 months\n"
                "Storage | 2-8C\n"
                "Presentation | single-dose vial"
            ),
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )

    def extract(self, payload: dict, blocks: list[ContentBlock]):
        return extract_requirements(
            edge_id=EDGE,
            role="A profile.",
            question="?",
            blocks=blocks,
            llm_client=FakeClient(payload),
            max_tokens=1000,
        )

    def test_a_selected_range_quotes_only_those_lines(self) -> None:
        """The point of the change: one row of a table, not the table."""
        block = self.multiline()
        found = self.extract(
            {
                "requirements": [
                    {"text": "Storage at 2-8C.", "spans": [picked(block.id, 2, 2)]}
                ]
            },
            [block],
        )
        self.assertEqual(found[0].cited_spans[0].quote, "Storage | 2-8C")
        self.assertEqual(found[0].cited_spans[0].block_ids, [block.id])

    def test_the_model_cannot_supply_the_text_of_its_own_citation(self) -> None:
        """A quote sent beside the range is ignored; the block decides what was said.

        The schema forbids the extra key, but a schema is a request and this is the
        guarantee. Delete the copying and this is the test that notices: the quote here
        would become the model's sentence, which the document does not contain.
        """
        block = self.multiline()
        found = self.extract(
            {
                "requirements": [
                    {
                        "text": "Shelf life of 36 months.",
                        "spans": [
                            {
                                "block_id": block.id,
                                "start_line": 1,
                                "end_line": 1,
                                "quote": "Shelf life of at least 48 months",
                            }
                        ],
                    }
                ]
            },
            [block],
        )
        self.assertEqual(found[0].cited_spans[0].quote, "Shelf life | 36 months")

    def test_a_range_running_past_the_block_is_not_a_citation(self) -> None:
        """An unresolvable range is dropped, and a requirement with none is refused.

        Not repaired down to the last line. A model that miscounted lines does not
        reliably mean the last one, and a citation that lands somewhere plausible is
        worse than a run that stops - a reader checking it would find text that reads
        fine and was never selected.
        """
        block = self.multiline()
        with self.assertRaises(ValueError) as caught:
            self.extract(
                {
                    "requirements": [
                        {"text": "Shelf life.", "spans": [picked(block.id, 1, 40)]}
                    ]
                },
                [block],
            )
        self.assertIn("no readable source lines", str(caught.exception))

    def test_the_document_is_shown_addressed_by_block_and_by_line(self) -> None:
        """Both addresses, or a range means nothing."""
        block = self.multiline()
        client = FakeClient({
            "requirements": [{"text": "Storage.", "spans": [picked(block.id, 2, 2)]}]
        })
        extract_requirements(
            edge_id=EDGE,
            role="A profile.",
            question="?",
            blocks=[block],
            llm_client=client,
            max_tokens=1000,
        )
        message = client.calls[0]["user"]
        self.assertIn(f"[block:{block.id}]", message)
        self.assertIn("[line:2] Storage | 2-8C", message)

    def test_a_verdict_quotes_the_measured_document_the_same_way(self) -> None:
        """One rule, both stages. The assessor had the same block-only citation."""
        block = ContentBlock(
            id="ctpp_file:table",
            doc_id="ctpp_file",
            ordinal=0,
            block_type="table",
            content="Dosing | annual\nRoute | intramuscular",
            heading_stack=[],
            structural_meta={},
            style_hint={},
        )
        finding = judge(
            {
                "verdict": "meets",
                "statement": "Dosing is annual.",
                "spans": [picked(block.id, 1, 1)],
            },
            [block],
        )
        self.assertEqual(finding.comparison_spans[0].quote, "Dosing | annual")

    def test_a_quote_that_is_not_in_its_block_is_refused(self) -> None:
        """The contract checks the text, not just the block it names.

        Unreachable from the pipeline, which copies its quotes out of the block. That is
        the point: this is the check for a result assembled some other way - replayed,
        hand-edited, or written by a future stage - and those are exactly the results a
        reader has no other way to audit.
        """
        config = load_config(write_config(CONFIG))
        invented = AlignmentFinding(
            requirement_id=requirement_id(EDGE, 1),
            edge_id=EDGE,
            requirement="Annual dosing.",
            reference_spans=[
                DocumentSpan(quote="Dosing every six months", block_ids=["itpp_file:b1"])
            ],
            verdict="meets",
            statement="The candidate states annual dosing.",
            comparison_spans=[cited("ctpp_file:b1")],
        )
        with self.assertRaises(ValueError) as caught:
            validate_result_contract(result(findings=[invented]), config)
        self.assertIn("does not appear in the passage it cites", str(caught.exception))


class StatementVoiceTests(unittest.TestCase):
    """The sentence describes the product, not the file it came out of.

    The model did this unevenly on its own - "The candidate states a minimum WHO
    prequalification date of 2030" on one row and "The optimistic dosing schedule is a
    single IM dose" on the next, for the same kind of finding. The interface now names the
    document on the same line as the sentence, so the prefix is chrome; worse, it reads as
    a claim about the document when the fact is about the product.
    """

    def test_the_prompt_says_not_to_name_the_document(self) -> None:
        prompt = build_assessment_prompt()
        self.assertIn("Do not name the document", prompt)
        # The instruction carries the example, because "do not name the document" alone
        # reads as a ban on the subject rather than on the prefix.
        self.assertIn("never \"The candidate states", prompt)

    def test_the_prompt_still_bans_the_other_two_things_it_kept_doing(self) -> None:
        """Restating the requirement and naming the distance. One paragraph, three bans."""
        prompt = build_assessment_prompt()
        self.assertIn("do not restate the requirement", prompt)
        self.assertIn("do not name the distance between the two", prompt)
