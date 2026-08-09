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
    build_user_message,
)
from services.aligner.stages.requirements import extract_requirements
from services.chunker import ContentBlock

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

        It reaches the model in the user message, as Expert's questions do, so the
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


def requirement(text: str = "Annual dosing.", blocks: tuple[str, ...] = ("itpp_file:b1",)):
    return Requirement(id=requirement_id(EDGE, 1), text=text, cited_block_ids=blocks)


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
                {"text": "Annual dosing.", "block_ids": ["itpp_file:b1"]},
                {"text": "Shelf life of 36 months.", "block_ids": ["itpp_file:b2"]},
            ]
        })
        self.assertEqual(
            [item.id for item in found],
            ["itpp-to-ctpp/r-001", "itpp-to-ctpp/r-002"],
        )
        self.assertEqual(found[1].cited_block_ids, ("itpp_file:b2",))

    def test_the_same_requirement_stated_twice_is_one_requirement(self) -> None:
        """A duplicate would double-count in every total computed from the list."""
        found = self.extract({
            "requirements": [
                {"text": "Annual dosing.", "block_ids": ["itpp_file:b1"]},
                {"text": "annual   dosing.", "block_ids": ["itpp_file:b2"]},
            ]
        })
        self.assertEqual(len(found), 1)

    def test_an_uncited_requirement_is_refused(self) -> None:
        """A bar nobody can check is worse than a bar nobody wrote down."""
        with self.assertRaises(ValueError):
            self.extract({"requirements": [{"text": "Annual dosing.", "block_ids": []}]})

    def test_a_requirement_citing_an_unknown_block_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.extract({
                "requirements": [
                    {"text": "Annual dosing.", "block_ids": ["ctpp_file:b1"]}
                ]
            })

    def test_an_empty_extraction_is_a_failure_not_an_answer(self) -> None:
        """No requirements means the read failed; it does not mean nothing is asked."""
        with self.assertRaises(ValueError):
            self.extract({"requirements": []})

    def test_the_schema_offers_only_the_reference_document_blocks(self) -> None:
        client = FakeClient({
            "requirements": [{"text": "Annual dosing.", "block_ids": ["itpp_file:b1"]}]
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
            offered["block_ids"]["items"]["enum"], ["itpp_file:b1", "itpp_file:b2"]
        )


class VerdictTests(unittest.TestCase):
    def test_meeting_the_bar_cites_the_document_that_was_measured(self) -> None:
        finding = judge({
            "verdict": "meets",
            "statement": "The candidate states annual dosing.",
            "gap": "",
            "block_ids": ["ctpp_file:b1"],
        })
        self.assertEqual(finding.verdict, "meets")
        self.assertEqual(finding.comparison_block_ids, ["ctpp_file:b1"])
        # Carried from the requirement, so the bar stays checkable beside the verdict.
        self.assertEqual(finding.reference_block_ids, ["itpp_file:b1"])
        self.assertEqual(finding.requirement, "Annual dosing.")
        self.assertEqual(finding.edge_id, EDGE)

    def test_exceeding_and_falling_short_are_different_verdicts(self) -> None:
        """The whole reason the old vocabulary went: one label for both directions."""
        better = judge({
            "verdict": "exceeds",
            "statement": "The candidate states dosing every two years.",
            "gap": "",
            "block_ids": ["ctpp_file:b1"],
        })
        worse = judge({
            "verdict": "falls_short",
            "statement": "The candidate states dosing every six months.",
            "gap": "Annual dosing against six-monthly dosing offered.",
            "block_ids": ["ctpp_file:b1"],
        })
        self.assertNotEqual(better.verdict, worse.verdict)
        self.assertEqual(worse.gap, "Annual dosing against six-monthly dosing offered.")

    def test_falling_short_without_naming_the_shortfall_is_refused(self) -> None:
        """"Worse" with no content is not something a reader can act on."""
        with self.assertRaises(ValueError):
            judge({
                "verdict": "falls_short",
                "statement": "The candidate states less.",
                "gap": "",
                "block_ids": ["ctpp_file:b1"],
            })

    def test_not_comparable_must_say_what_would_make_it_comparable(self) -> None:
        finding = judge({
            "verdict": "not_comparable",
            "statement": "The candidate states convenient dosing.",
            "gap": "A dosing interval in months.",
            "block_ids": ["ctpp_file:b1"],
        })
        self.assertEqual(finding.gap, "A dosing interval in months.")
        with self.assertRaises(ValueError):
            judge({
                "verdict": "not_comparable",
                "statement": "The candidate states convenient dosing.",
                "gap": "",
                "block_ids": ["ctpp_file:b1"],
            })

    def test_a_satisfied_requirement_cannot_carry_a_gap(self) -> None:
        """Otherwise a gap sentence could sit under a verdict that has none."""
        for verdict in ("meets", "exceeds"):
            with self.assertRaises(ValueError):
                judge({
                    "verdict": verdict,
                    "statement": "The candidate states annual dosing.",
                    "gap": "Something.",
                    "block_ids": ["ctpp_file:b1"],
                })

    def test_silence_cites_nothing_and_explains_nothing_further(self) -> None:
        finding = judge({
            "verdict": "not_addressed",
            "statement": "The candidate states nothing about dosing interval.",
            "gap": "",
            "block_ids": [],
        })
        self.assertEqual(finding.comparison_block_ids, [])
        for payload in (
            {"gap": "Something.", "block_ids": []},
            {"gap": "", "block_ids": ["ctpp_file:b1"]},
        ):
            with self.assertRaises(ValueError):
                judge({
                    "verdict": "not_addressed",
                    "statement": "Nothing.",
                    **payload,
                })

    def test_a_verdict_must_carry_a_statement(self) -> None:
        with self.assertRaises(ValueError):
            judge({
                "verdict": "meets",
                "statement": "  ",
                "gap": "",
                "block_ids": ["ctpp_file:b1"],
            })

    def test_an_unknown_verdict_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            judge({
                "verdict": "modified",
                "statement": "The candidate differs.",
                "gap": "",
                "block_ids": ["ctpp_file:b1"],
            })

    def test_the_schema_offers_only_the_measured_document_blocks(self) -> None:
        """A verdict cannot be justified by citing the document that set the bar."""
        schema = assessment_schema([block("ctpp_file:b1", "ctpp_file")])
        self.assertEqual(schema["properties"]["block_ids"]["items"]["enum"], ["ctpp_file:b1"])
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
            reference_block_ids=["itpp_file:b1"],
            verdict="meets",
            statement="The candidate states annual dosing.",
            gap="",
            comparison_block_ids=["ctpp_file:b1"],
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
            self.validate(self.finding(comparison_block_ids=["itpp_file:b1"]))

    def test_a_requirement_citing_the_measured_document_is_refused(self) -> None:
        """The mirror image: the bar has to be stated where the bar is stated."""
        with self.assertRaises(ValueError):
            self.validate(self.finding(reference_block_ids=["ctpp_file:b1"]))

    def test_a_requirement_with_no_citation_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(reference_block_ids=[]))

    def test_one_requirement_cannot_have_two_verdicts(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(), self.finding(verdict="falls_short", gap="x"))

    def test_a_finding_must_belong_to_a_comparison_this_run_made(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(edge_id="ctpp-to-ipdp"))

    def test_the_gap_rule_is_enforced_in_both_directions(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(verdict="falls_short", gap=""))
        with self.assertRaises(ValueError):
            self.validate(self.finding(verdict="meets", gap="Something."))

    def test_the_citation_rule_is_enforced_in_both_directions(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(verdict="meets", comparison_block_ids=[]))
        with self.assertRaises(ValueError):
            self.validate(
                self.finding(
                    verdict="not_addressed",
                    statement="Nothing.",
                    comparison_block_ids=["ctpp_file:b1"],
                )
            )

    def test_a_finding_must_state_what_the_document_says(self) -> None:
        with self.assertRaises(ValueError):
            self.validate(self.finding(statement=" "))
