"""What Aligner guarantees while it has no analysis.

Every test here covers the surface a new design will build on: config that keeps
document types and document counts out of code, the comparisons a set of
documents resolves, the result envelope, and the structural contract. Nothing
tests a finding, because Aligner makes none - the extract-and-link stages were
removed along with their symmetric relation vocabulary.
"""

from __future__ import annotations

import tempfile
import unittest

from services.aligner import describe_document, describe_edges, load_config, resolve_edges
from services.aligner.contract import validate_result_contract
from services.aligner.models import (
    AlignmentConfig,
    AlignmentDocument,
    AlignmentEdge,
    AlignmentResult,
    EdgeSpec,
)
from services.aligner.prompt_catalog import PROMPT_CATALOG
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
) -> AlignmentResult:
    documents = documents if documents is not None else [doc("itpp"), doc("ctpp")]
    return AlignmentResult(
        documents=documents,
        edges=edges
        if edges is not None
        else [AlignmentEdge("itpp_file", "ctpp_file", "Does the candidate meet the bar?")],
        org="bmgf",
        intervention_class="vaccine",
        indication="malaria",
        blocks=blocks
        if blocks is not None
        else [block(f"{document.doc_id}:b1", document.doc_id) for document in documents],
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
                result(edges=[AlignmentEdge("itpp_file", "absent", "?")]), self.config
            )

    def test_a_comparison_must_state_what_it_asks(self) -> None:
        with self.assertRaisesRegex(ValueError, "must state what it asks"):
            validate_result_contract(
                result(edges=[AlignmentEdge("itpp_file", "ctpp_file", "  ")]), self.config
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
    def test_aligner_declares_no_prompts(self) -> None:
        """The slot stays so the reference generator needs no special case."""
        self.assertEqual(PROMPT_CATALOG, ())


if __name__ == "__main__":
    unittest.main()
