"""Expert: the bank loads, resolution is deterministic, and the contract holds.

Resolution is where four of the five states are decided with no model involved, so
it is the part worth testing hardest — a wrong state here is a wrong answer that no
later stage can detect.
"""

from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from services.chunker import ContentBlock
from services.expert import (
    ANSWER_SOURCES,
    MODEL_STATES,
    QUESTION_STATES,
    ContextItem,
    DisciplineReview,
    DisciplineSpec,
    GateConfig,
    GateReview,
    QuestionAssessment,
    QuestionSpec,
    ReviewDocument,
    available_gates,
    find_config,
    has_config,
    load_config,
    resolve_questions,
    validate_result_contract,
)
from services.expert.prompt_catalog import PROMPT_CATALOG
from services.expert.stages.assessor import (
    DECISION_NOT_FOUND,
    DECISION_FROM_CONTEXT,
    DECISION_FROM_DOCUMENT,
    assess_question,
    assessment_schema,
    build_assessment_prompt,
)

CONFIGS = Path(__file__).resolve().parents[1] / "services" / "expert" / "configs"


def block(block_id: str, doc_id: str, source_type: str, content: str = "text") -> ContentBlock:
    return ContentBlock(
        id=block_id,
        doc_id=doc_id,
        ordinal=1,
        block_type="paragraph",
        content=content,
        heading_stack=[],
        structural_meta={},
        style_hint="",
        source_type=source_type,
    )


def spec(
    question_id: str,
    *,
    applies_to: tuple[str, ...] = (),
    likely_in: tuple[str, ...] = (),
    pq: bool = False,
) -> QuestionSpec:
    return QuestionSpec(
        id=question_id,
        text=f"Question {question_id}?",
        applies_to=frozenset(applies_to),
        likely_in=likely_in,
        pq=pq,
    )


BANK_SOURCE = "Stage Gate Question Bank — SME Edition v5, test fixture"


def gate(*questions: QuestionSpec) -> GateConfig:
    return GateConfig(
        org="bmgf",
        gate_id="lcs",
        gate_label="Lead Candidate Selection",
        ordinal=1,
        mirrors=BANK_SOURCE,
        disciplines=(DisciplineSpec(id="cd", label="Clinical Development", questions=questions),),
    )


class BankTests(unittest.TestCase):
    def test_every_shipped_bank_loads(self) -> None:
        paths = sorted(CONFIGS.glob("*.yaml"))
        self.assertTrue(paths, "no question banks are shipped")
        for path in paths:
            config = load_config(str(path))
            self.assertTrue(config.disciplines, f"{path.name} declares no disciplines")
            self.assertTrue(config.questions(), f"{path.name} declares no questions")

    def test_every_shipped_bank_names_the_document_it_transcribes(self) -> None:
        """The whole tool is a transcription, so a bank must say what it transcribes.

        Version included: a bank taken from v5 is stale the moment v6 publishes, and
        this line is the only thing that says which one produced a saved review.
        """
        for path in sorted(CONFIGS.glob("*.yaml")):
            config = load_config(str(path))
            self.assertTrue(config.mirrors.strip(), f"{path.name} names no source")
            self.assertIn("v5", config.mirrors, path.name)
            self.assertIn("http", config.mirrors, f"{path.name} links nothing")

    def test_a_bank_without_a_source_is_refused(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "bank.yaml"
        path.write_text(
            "org: bmgf\ngate:\n  id: g\n  label: G\n  ordinal: 1\n"
            "disciplines:\n  - id: cd\n    label: CD\n    questions:\n"
            "      - id: Q1\n        text: t\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as caught:
            load_config(str(path))
        self.assertIn("mirrors", str(caught.exception))

    def test_a_shipped_bank_declares_ten_questions_per_discipline(self) -> None:
        """The matrix is 8 x 10 per gate. A short cell is a transcription slip."""
        for path in sorted(CONFIGS.glob("*.yaml")):
            config = load_config(str(path))
            for discipline in config.disciplines:
                self.assertEqual(
                    len(discipline.questions),
                    10,
                    f"{path.name}: {discipline.id} has {len(discipline.questions)}",
                )

    def test_question_ids_are_unique_across_a_bank(self) -> None:
        for path in sorted(CONFIGS.glob("*.yaml")):
            config = load_config(str(path))
            ids = [question.id for _, question in config.questions()]
            self.assertEqual(len(ids), len(set(ids)), path.name)

    def test_the_matrix_is_complete(self) -> None:
        """7 gates x 8 disciplines x 10 questions. A short cell is a lost question."""
        gates = available_gates("bmgf")
        self.assertEqual(len(gates), 7, [gate.id for gate in gates])
        total = sum(
            len(find_config("bmgf", gate.id).questions()) for gate in gates
        )
        self.assertEqual(total, 560)

    def test_every_gate_declares_the_same_eight_disciplines(self) -> None:
        """Routing depends on the owning discipline existing at every gate."""
        expected = None
        for gate in available_gates("bmgf"):
            ids = [d.id for d in find_config("bmgf", gate.id).disciplines]
            self.assertEqual(len(ids), 8, f"{gate.id}: {ids}")
            if expected is None:
                expected = ids
            self.assertEqual(ids, expected, f"{gate.id} orders disciplines differently")

    def test_prequalification_questions_appear_only_at_launch(self) -> None:
        """`[PQ]` questions are carried inside the DTL ten and nowhere else."""
        for gate in available_gates("bmgf"):
            config = find_config("bmgf", gate.id)
            marked = [q.id for _, q in config.questions() if q.pq]
            if gate.id == "dtl":
                self.assertTrue(marked, "DTL carries no prequalification question")
            else:
                self.assertEqual(marked, [], f"{gate.id} marks a question pq")

    def test_a_question_id_names_its_discipline_and_gate(self) -> None:
        """`CP.EOP1.6` — the id is how a reviewer finds it in the source bank."""
        for gate in available_gates("bmgf"):
            config = find_config("bmgf", gate.id)
            for discipline in config.disciplines:
                for question in discipline.questions:
                    prefix, _, rest = question.id.partition(".")
                    gate_part, _, _ = rest.partition(".")
                    self.assertEqual(
                        prefix.lower(),
                        discipline.id,
                        f"{question.id} sits under discipline {discipline.id}",
                    )
                    self.assertEqual(
                        gate_part.lower(),
                        config.gate_id,
                        f"{question.id} sits in gate {config.gate_id}",
                    )

    def test_no_question_id_is_reused_across_gates(self) -> None:
        seen: dict[str, str] = {}
        for gate in available_gates("bmgf"):
            for _, question in find_config("bmgf", gate.id).questions():
                self.assertNotIn(
                    question.id, seen, f"also in {seen.get(question.id)}"
                )
                seen[question.id] = gate.id

    def test_gates_are_listed_in_development_order(self) -> None:
        gates = available_gates("bmgf")
        self.assertEqual(
            [g.ordinal for g in gates],
            sorted(g.ordinal for g in gates),
        )

    def test_an_unknown_org_has_no_gates(self) -> None:
        self.assertEqual(available_gates("nobody"), [])

    def test_find_config_raises_rather_than_returning_none(self) -> None:
        with self.assertRaises(LookupError):
            find_config("bmgf", "no-such-gate")
        self.assertFalse(has_config("bmgf", "no-such-gate"))
        self.assertTrue(has_config("bmgf", "lcs"))


class BankValidationTests(unittest.TestCase):
    def write(self, body: str) -> str:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        path = Path(self.directory.name) / "bank.yaml"
        path.write_text(body, encoding="utf-8")
        return str(path)

    HEAD = "org: bmgf\ngate:\n  id: g\n  label: G\n  ordinal: 1\n"

    def test_an_unknown_intervention_class_is_refused(self) -> None:
        """`biologic` is prose, not vocabulary. It must be resolved at authoring."""
        path = self.write(
            self.HEAD
            + "disciplines:\n  - id: cd\n    label: CD\n    questions:\n"
            + "      - id: Q1\n        text: t\n        applies_to: [biologic]\n"
        )
        with self.assertRaises(ValueError) as caught:
            load_config(path)
        self.assertIn("biologic", str(caught.exception))

    def test_an_unparseable_document_type_is_refused(self) -> None:
        path = self.write(
            self.HEAD
            + "disciplines:\n  - id: cd\n    label: CD\n    questions:\n"
            + "      - id: Q1\n        text: t\n        likely_in: [pdss]\n"
        )
        with self.assertRaises(ValueError) as caught:
            load_config(path)
        self.assertIn("pdss", str(caught.exception))

    def test_a_repeated_question_id_is_refused(self) -> None:
        path = self.write(
            self.HEAD
            + "disciplines:\n  - id: cd\n    label: CD\n    questions:\n"
            + "      - id: Q1\n        text: a\n      - id: Q1\n        text: b\n"
        )
        with self.assertRaises(ValueError):
            load_config(path)

    def test_a_bank_without_disciplines_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load_config(self.write(self.HEAD + "disciplines: []\n"))

    def test_a_gate_without_an_ordinal_is_refused(self) -> None:
        path = self.write(
            "org: bmgf\ngate:\n  id: g\n  label: G\n"
            "disciplines:\n  - id: cd\n    label: CD\n    questions:\n"
            "      - id: Q1\n        text: t\n"
        )
        with self.assertRaises(ValueError):
            load_config(path)


class ResolveTests(unittest.TestCase):
    """The deterministic pass. It reads only what the question text states.

    Which documents were uploaded is deliberately not an input. Withholding a question
    because of a judgment about where its answer lives was the brittleness this
    replaced, so there is exactly one decision here and the source document states it.
    """

    def test_a_question_whose_text_names_another_class_is_not_applicable(self) -> None:
        config = gate(spec("Q1", applies_to=("mab",)), spec("Q2"))
        resolved = resolve_questions(config, intervention_class="vaccine")
        self.assertEqual(resolved[0].state, "not_applicable")
        self.assertIsNone(resolved[1].state)

    def test_an_unqualified_question_applies_to_every_class(self) -> None:
        config = gate(spec("Q1"))
        for intervention in ("vaccine", "drug", "device", "mab", "diagnostic"):
            resolved = resolve_questions(config, intervention_class=intervention)
            self.assertIsNone(resolved[0].state, intervention)

    def test_the_hint_never_withholds_a_question(self) -> None:
        """`likely_in` is a tag. A question with none is still assessed."""
        config = gate(spec("Q1"), spec("Q2", likely_in=("ipdp",)))
        resolved = resolve_questions(config, intervention_class="vaccine")
        self.assertEqual([item.state for item in resolved], [None, None])

    def test_resolution_does_not_depend_on_which_documents_were_uploaded(self) -> None:
        """The signature has no place for it, and that is the point."""
        config = find_config("bmgf", "lcs")
        resolved = resolve_questions(config, intervention_class="vaccine")
        self.assertEqual(
            sum(1 for item in resolved if item.queued),
            sum(1 for _, q in config.questions() if q.applies("vaccine")),
        )

    def test_a_bank_that_applies_to_nothing_fails_loudly(self) -> None:
        config = gate(spec("Q1", applies_to=("drug",)), spec("Q2", applies_to=("mab",)))
        with self.assertRaises(ValueError) as caught:
            resolve_questions(config, intervention_class="device")
        self.assertIn("device", str(caught.exception))

    def test_every_question_is_resolved_exactly_once_in_bank_order(self) -> None:
        config = find_config("bmgf", "lcs")
        resolved = resolve_questions(config, intervention_class="vaccine")
        self.assertEqual(len(resolved), len(config.questions()))
        self.assertEqual(
            [item.question.id for item in resolved],
            [question.id for _, question in config.questions()],
        )

    def test_almost_every_shipped_question_reaches_the_model(self) -> None:
        """Only the eleven questions whose own text restricts a class are withheld."""
        for gate_spec in available_gates("bmgf"):
            config = find_config("bmgf", gate_spec.id)
            resolved = resolve_questions(config, intervention_class="vaccine")
            withheld = [i.question.id for i in resolved if not i.queued]
            for question_id in withheld:
                question = next(q for _, q in config.questions() if q.id == question_id)
                self.assertTrue(
                    question.applies_to,
                    f"{question_id} was withheld with no stated restriction",
                )


class VocabularyTests(unittest.TestCase):
    def test_the_model_owns_every_state_but_the_one_the_question_text_owns(self) -> None:
        """Four states, three of them observations of the supplied material.

        There were five once, and the two removed rested on a guess about which document
        should hold an answer. `partly_answered` is not a return to that: it is an
        observation, and the reason it exists is that the bank's questions are compound,
        so a binary made a thorough plan and a blank page score identically.
        """
        self.assertEqual(
            set(QUESTION_STATES),
            {"not_applicable", "answered", "partly_answered", "not_found"},
        )
        self.assertEqual(
            set(MODEL_STATES), {"answered", "partly_answered", "not_found"}
        )
        self.assertNotIn("not_applicable", MODEL_STATES)

    def test_there_are_exactly_two_answer_sources(self) -> None:
        """A third would let something look cited without being checkable."""
        self.assertEqual(set(ANSWER_SOURCES), {"document", "context"})


def review(*questions: QuestionAssessment, blocks=None, labels=None) -> GateReview:
    return GateReview(
        gate_id="lcs",
        gate_label="Lead Candidate Selection",
        bank_source=BANK_SOURCE,
        documents=[ReviewDocument(doc_id="d", source_type="itpp")],
        disciplines=[DisciplineReview(id="cd", label="Clinical Development", questions=list(questions))],
        context_labels=list(labels or []),
        org="bmgf",
        intervention_class="vaccine",
        indication="malaria",
        blocks=list(blocks or []),
    )


class ContractTests(unittest.TestCase):
    CONFIG = gate(spec("Q1", likely_in=("itpp",)), spec("Q2"))

    def answered(self, **overrides) -> QuestionAssessment:
        defaults = dict(
            id="Q1",
            text="Question Q1?",
            state="answered",
            statement="The plan states it.",
            source="document",
            cited_block_ids=["d:1"],
        )
        defaults.update(overrides)
        return QuestionAssessment(**defaults)

    def excluded(self) -> QuestionAssessment:
        """A question its own text restricts to another class."""
        return QuestionAssessment(id="Q2", text="Question Q2?", state="not_applicable")

    def test_a_valid_review_is_returned_rather_than_dropped(self) -> None:
        result = review(self.answered(), self.excluded(), blocks=[block("d:1", "d", "itpp")])
        self.assertIs(validate_result_contract(result, self.CONFIG), result)

    def test_a_missing_question_is_refused(self) -> None:
        result = review(self.answered(), blocks=[block("d:1", "d", "itpp")])
        with self.assertRaises(ValueError) as caught:
            validate_result_contract(result, self.CONFIG)
        self.assertIn("denominator", str(caught.exception))

    def test_a_question_the_gate_does_not_ask_is_refused(self) -> None:
        extra = QuestionAssessment(id="Q9", text="x", state="not_answerable")
        result = review(
            self.answered(), self.excluded(), extra, blocks=[block("d:1", "d", "itpp")]
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_repeated_question_is_refused(self) -> None:
        result = review(
            self.answered(), self.answered(), self.excluded(), blocks=[block("d:1", "d", "itpp")]
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_an_answer_citing_an_unknown_block_is_refused(self) -> None:
        result = review(
            self.answered(cited_block_ids=["d:99"]),
            self.excluded(),
            blocks=[block("d:1", "d", "itpp")],
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_an_answer_from_a_document_must_cite_something(self) -> None:
        result = review(self.answered(cited_block_ids=[]), self.excluded())
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_context_answer_must_name_a_supplied_item(self) -> None:
        result = review(
            self.answered(source="context", cited_block_ids=[], context_label="Ghost"),
            self.excluded(),
            labels=["CMC Report"],
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_context_answer_cannot_cite_a_block(self) -> None:
        """Transient input is never chunked, so a block ID here is impossible."""
        result = review(
            self.answered(
                source="context", cited_block_ids=["d:1"], context_label="CMC Report"
            ),
            self.excluded(),
            blocks=[block("d:1", "d", "itpp")],
            labels=["CMC Report"],
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_context_answer_is_accepted_without_lineage(self) -> None:
        result = review(
            self.answered(source="context", cited_block_ids=[], context_label="CMC Report"),
            self.excluded(),
            labels=["CMC Report"],
        )
        self.assertIs(validate_result_contract(result, self.CONFIG), result)

    def test_a_non_answered_question_cannot_carry_evidence(self) -> None:
        result = review(
            QuestionAssessment(
                id="Q1", text="t", state="absent", statement="x", source="document"
            ),
            self.excluded(),
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_an_inapplicable_question_makes_no_statement(self) -> None:
        """No model read it, so there is nothing for it to have observed."""
        excluded = QuestionAssessment(
            id="Q2", text="t", state="not_applicable", statement="no document says"
        )
        result = review(self.answered(), excluded, blocks=[block("d:1", "d", "itpp")])
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_block_from_an_uncarried_document_is_refused(self) -> None:
        result = review(
            self.answered(cited_block_ids=["x:1"]),
            self.excluded(),
            blocks=[block("x:1", "other", "itpp")],
        )
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_review_for_another_gate_is_refused(self) -> None:
        result = review(self.answered(), self.excluded(), blocks=[block("d:1", "d", "itpp")])
        result.gate_id = "eop1"
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)

    def test_a_review_without_documents_is_refused(self) -> None:
        result = review(self.answered(), self.excluded(), blocks=[block("d:1", "d", "itpp")])
        result.documents = []
        with self.assertRaises(ValueError):
            validate_result_contract(result, self.CONFIG)


class FakeClient:
    """Answers every question the same way, recording what it was asked."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        self.calls.append(
            {
                "system": system_prompt,
                "user": user_message,
                "schema": schema,
                "schema_name": schema_name,
            }
        )
        return dict(self.payload)


class AssessorTests(unittest.TestCase):
    BLOCKS = [block("d:1", "d", "ipdp", "The plan states annual dosing.")]

    def test_a_document_answer_carries_its_lineage(self) -> None:
        client = FakeClient(
            {
                "decision": DECISION_FROM_DOCUMENT,
                "statement": "The plan states it.",
                "missing": "",
                "block_ids": ["d:1"],
                "context_label": "",
            }
        )
        result = assess_question(
            spec("Q1", likely_in=("ipdp",)),
            blocks=self.BLOCKS,
            context_items=[],
            llm_client=client,
            max_tokens=100,
        )
        self.assertEqual(result.state, "answered")
        self.assertEqual(result.source, "document")
        self.assertEqual(result.cited_block_ids, ["d:1"])
        self.assertEqual(result.context_label, "")

    def test_a_context_answer_carries_a_label_and_no_lineage(self) -> None:
        client = FakeClient(
            {
                "decision": DECISION_FROM_CONTEXT,
                "statement": "The report states it.",
                "missing": "",
                "block_ids": [],
                "context_label": "CMC Report",
            }
        )
        result = assess_question(
            spec("Q1", likely_in=("ipdp",)),
            blocks=self.BLOCKS,
            context_items=[ContextItem(label="CMC Report", text="COGS is $1.20")],
            llm_client=client,
            max_tokens=100,
        )
        self.assertEqual(result.source, "context")
        self.assertEqual(result.context_label, "CMC Report")
        self.assertEqual(result.cited_block_ids, [])

    def test_a_partial_answer_names_what_is_still_missing(self) -> None:
        from services.expert.stages.assessor import DECISION_PARTLY_FROM_DOCUMENT

        client = FakeClient(
            {
                "decision": DECISION_PARTLY_FROM_DOCUMENT,
                "statement": "The plan states annual dosing.",
                "missing": "Zone IVb stability data and the VVM category.",
                "block_ids": ["d:1"],
                "context_label": "",
            }
        )
        result = assess_question(
            spec("Q1", likely_in=("ipdp",)),
            blocks=self.BLOCKS,
            context_items=[],
            llm_client=client,
            max_tokens=100,
        )
        self.assertEqual(result.state, "partly_answered")
        self.assertEqual(result.source, "document")
        self.assertEqual(result.cited_block_ids, ["d:1"])
        self.assertIn("Zone IVb", result.missing)

    def test_a_partial_answer_with_no_account_is_refused(self) -> None:
        """That sentence is the only record of what the question leaves open."""
        from services.expert.stages.assessor import DECISION_PARTLY_FROM_DOCUMENT

        client = FakeClient(
            {
                "decision": DECISION_PARTLY_FROM_DOCUMENT,
                "statement": "The plan states annual dosing.",
                "missing": "",
                "block_ids": ["d:1"],
                "context_label": "",
            }
        )
        with self.assertRaises(ValueError):
            assess_question(
                spec("Q1"),
                blocks=self.BLOCKS,
                context_items=[],
                llm_client=client,
                max_tokens=100,
            )
        self.assertEqual(len(client.calls), 2, "the contract failure was not retried")

    def test_a_full_answer_cannot_carry_a_missing_note(self) -> None:
        """It is either fully answered or partly. A note on a full answer is a state
        the two disagree about."""
        client = FakeClient(
            {
                "decision": DECISION_FROM_DOCUMENT,
                "statement": "The plan states it.",
                "missing": "something",
                "block_ids": ["d:1"],
                "context_label": "",
            }
        )
        with self.assertRaises(ValueError):
            assess_question(
                spec("Q1"),
                blocks=self.BLOCKS,
                context_items=[],
                llm_client=client,
                max_tokens=100,
            )

    def test_a_partial_is_offered_even_without_context(self) -> None:
        """Completeness is independent of source, so it is never gated on context."""
        from services.expert.stages.assessor import DECISION_PARTLY_FROM_DOCUMENT

        schema = assessment_schema(self.BLOCKS, [])
        self.assertIn(
            DECISION_PARTLY_FROM_DOCUMENT, schema["properties"]["decision"]["enum"]
        )

    def test_a_not_found_answer_carries_nothing(self) -> None:
        client = FakeClient(
            {
                "decision": DECISION_NOT_FOUND,
                "statement": "No document states a dosing target.",
                "missing": "",
                "block_ids": [],
                "context_label": "",
            }
        )
        result = assess_question(
            spec("Q1", likely_in=("ipdp",)),
            blocks=self.BLOCKS,
            context_items=[],
            llm_client=client,
            max_tokens=100,
        )
        self.assertEqual(result.state, "not_found")
        self.assertIsNone(result.source)

    def test_a_fabricated_block_is_retried_then_refused(self) -> None:
        client = FakeClient(
            {
                "decision": DECISION_FROM_DOCUMENT,
                "statement": "The plan states it.",
                "missing": "",
                "block_ids": ["d:99"],
                "context_label": "",
            }
        )
        with self.assertRaises(ValueError):
            assess_question(
                spec("Q1", likely_in=("ipdp",)),
                blocks=self.BLOCKS,
                context_items=[],
                llm_client=client,
                max_tokens=100,
            )
        self.assertEqual(len(client.calls), 2, "the contract failure was not retried")

    def test_context_is_not_offered_when_none_was_supplied(self) -> None:
        """A model cannot attribute an answer to a source that does not exist."""
        schema = assessment_schema(self.BLOCKS, [])
        self.assertNotIn(
            DECISION_FROM_CONTEXT, schema["properties"]["decision"]["enum"]
        )
        self.assertEqual(schema["properties"]["context_label"]["enum"], [""])

    def test_block_ids_can_only_name_supplied_blocks(self) -> None:
        schema = assessment_schema(self.BLOCKS, [])
        self.assertEqual(schema["properties"]["block_ids"]["items"]["enum"], ["d:1"])

    def test_the_prompt_refuses_the_other_tools_jobs(self) -> None:
        prompt = build_assessment_prompt(True)
        self.assertIn("template", prompt)
        self.assertIn("realistic", prompt)

    def test_the_prompt_asks_for_a_clause_by_clause_judgment(self) -> None:
        """The bank's questions are compound, so rounding one either way loses it."""
        prompt = build_assessment_prompt(False)
        self.assertIn("clause by clause", prompt)
        self.assertIn("Do not round a partial", prompt)

    def test_the_material_precedes_the_question_so_it_can_be_cached(self) -> None:
        """Every question in a run shares the same material; only the question varies.

        Reversed — as this was — each call had a different first line and shared no
        cacheable prefix, so the documents were paid for once per question.
        """
        from services.expert.stages.assessor import build_user_message

        message = build_user_message(
            spec("Q1", likely_in=("ipdp",)),
            self.BLOCKS,
            [ContextItem(label="CMC Report", text="COGS is $1.20")],
        )
        self.assertLess(message.index("Supplied document blocks"), message.index("Question ("))
        self.assertLess(message.index("Supplied context"), message.index("Question ("))

    def test_the_hint_is_never_sent_to_the_model(self) -> None:
        """Telling it where the answer supposedly lives would let a guess steer it.

        The hint names a type no supplied block carries, so finding it in the prompt
        can only mean the hint leaked — a block header legitimately names its own
        document type, which is a fact about the material rather than a judgment.
        """
        from services.expert.stages.assessor import build_user_message

        message = build_user_message(
            spec("Q1", likely_in=("ctpp",)),
            [block("d:1", "d", "ipdp", "The plan states annual dosing.")],
            [],
        )
        self.assertIn("ipdp", message, "the block should name its own document")
        self.assertNotIn("ctpp", message, "the hint leaked into the prompt")


class PromptCatalogTests(unittest.TestCase):
    def test_expert_publishes_its_single_prompt(self) -> None:
        self.assertEqual(len(PROMPT_CATALOG), 1)
        entry = PROMPT_CATALOG[0]
        self.assertEqual(entry.tool, "expert")
        self.assertTrue(entry.render().strip())

    def test_the_published_prompt_is_the_variant_with_context(self) -> None:
        """The larger variant, so publication does not understate what is sent."""
        self.assertIn(DECISION_FROM_CONTEXT, PROMPT_CATALOG[0].render())


if __name__ == "__main__":
    unittest.main()
