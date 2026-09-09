"""Screener end to end: a real DOCX in, a complete gate review out.

Every other stage is unit-tested, but nothing exercised the wiring between them —
resolve's output feeding the assessor, blocks reaching the right questions, and the
contract running on what the pipeline actually assembles. Those lines fail at
runtime rather than at build time, so this is the test that would have caught it.

The model client is a fake. What is being tested is the pipeline, not the provider.
"""

from __future__ import annotations

import unittest
import io
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from PIL import Image

from services.screener import (
    DocumentInput,
    GateConfig,
    QuestionSpec,
    find_config,
    run_pipeline,
)
from services.screener.models import DisciplineSpec
from services.screener.stages.assessor import (
    DECISION_NOT_FOUND,
    DECISION_ANSWERED,
)


def write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))


class ScriptedClient:
    """Returns a queued decision per call, and records what it was asked.

    Also answers chunker's own model calls, which return a different shape; anything
    it does not recognise gets an empty object so the parse still completes.
    """

    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = list(decisions)
        self.triage_calls: list[str] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        if schema_name == "screener_question_triage":
            self.triage_calls.append(user_message)
            return self.decisions.pop(0) if self.decisions else {
                "decision": DECISION_NOT_FOUND,
                "statement": "Nothing supplied answers this.",
                "missing": "",
                "block_ids": [],
            }
        raise AssertionError(f"Unexpected model stage: {schema_name}")


def bank(*questions: QuestionSpec) -> GateConfig:
    return GateConfig(
        org="bmgf",
        gate_id="lcs",
        gate_label="Lead Chemical Series Selection",
        ordinal=1,
        intervention_classes=frozenset({"drug"}),
        mirrors="Stage Gate Questions - All Gates.docx, test fixture",
        disciplines=(
            DisciplineSpec(id="cp", label="Clinical Pharmacology", questions=questions),
        ),
    )


class PipelineTests(unittest.TestCase):
    def test_all_documents_and_embedded_images_share_one_citation_collection(self) -> None:
        report = self.root / "report.docx"
        document = Document()
        document.add_paragraph("Independent laboratory findings.")
        image = io.BytesIO()
        Image.new("RGB", (12, 12), "red").save(image, format="PNG")
        image.seek(0)
        document.add_picture(image)
        document.save(report)

        class CiteAllClient:
            calls = []

            def call_structured(self, system_prompt, user_message, max_tokens,
                                *, schema_name, schema, images=None, **kwargs):
                if schema_name != "screener_question_triage":
                    raise AssertionError("Parsing must not call a model")
                self.calls.append((user_message, images))
                return {
                    "decision": "answered", "statement": "The findings are documented.",
                    "missing": "", "block_ids": schema["properties"]["block_ids"]["items"]["enum"],
                }

        client = CiteAllClient()
        review = run_pipeline(
            [DocumentInput(str(self.itpp), "profile"), DocumentInput(str(report), "report")],
            org="bmgf", intervention_class="drug", indication="malaria",
            config=bank(QuestionSpec("Q1", "What was found?"), QuestionSpec("Q2", "What is planned?")),
            llm_client=client,
        )
        self.assertEqual([d.doc_id for d in review.documents], ["profile", "report"])
        self.assertEqual({b.doc_id for b in review.blocks}, {"profile", "report"})
        for assessment in review.assessments():
            self.assertEqual(assessment.cited_block_ids, [b.id for b in review.blocks])
        retained_images = [b for b in review.blocks if b.image]
        self.assertEqual(len(retained_images), 1)
        for message, images in client.calls:
            self.assertIn("Dosing regimen", message)
            self.assertIn("Independent laboratory findings", message)
            self.assertEqual(images, [{"block_id": retained_images[0].id,
                                       "data_url": retained_images[0].image.data_url()}])
        for block in review.blocks:
            self.assertEqual((block.org, block.intervention_class, block.indication),
                             ("bmgf", "drug", "malaria"))
            self.assertIsNone(block.source_type)

    def test_duplicate_document_ids_fail_before_parsing(self) -> None:
        with self.assertRaisesRegex(ValueError, "share a doc_id"):
            run_pipeline(
                [DocumentInput("missing.docx", "same"), DocumentInput("also-missing.docx", "same")],
                org="bmgf", intervention_class="drug", indication="malaria",
                config=bank(QuestionSpec("Q1", "What was found?")), llm_client=ScriptedClient([]),
            )

    def test_unsupported_formats_fail_before_parsing(self) -> None:
        for suffix in ("txt", "md", "png", "jpg"):
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "Unsupported"):
                run_pipeline(
                    [DocumentInput("missing." + suffix, "report")],
                    org="bmgf", intervention_class="drug", indication="malaria",
                    config=bank(QuestionSpec("Q1", "What was found?")), llm_client=ScriptedClient([]),
                )

    def test_an_empty_document_is_not_silently_lost_beside_a_readable_document(self) -> None:
        empty = self.root / "empty.docx"
        write_docx(empty, [])
        with self.assertRaisesRegex(ValueError, "empty.*no readable content"):
            run_pipeline(
                [DocumentInput(str(self.itpp), "profile"), DocumentInput(str(empty), "empty")],
                org="bmgf", intervention_class="drug", indication="malaria",
                config=bank(QuestionSpec("Q1", "What was found?")), llm_client=ScriptedClient([]),
            )

    def test_arbitrary_documents_need_no_type_configuration(self) -> None:
        report = self.root / "study-report.docx"
        write_docx(report, ["Clinical study findings."])
        client = ScriptedClient([])
        review = run_pipeline(
            [DocumentInput(file_path=str(report), doc_id="study-report")],
            org="bmgf", intervention_class="drug", indication="malaria",
            config=bank(QuestionSpec(id="Q1", text="What was found?")),
            llm_client=client,
        )
        self.assertEqual([d.doc_id for d in review.documents], ["study-report"])
        self.assertTrue(review.blocks)
        self.assertTrue(all(b.source_type is None for b in review.blocks))
        self.assertIn("Clinical study findings", client.triage_calls[0])

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.itpp = self.root / "profile.docx"
        write_docx(
            self.itpp,
            [
                "Target Product Profile",
                "Dosing regimen: one dose, annually.",
                "Procurement price: under USD 3.00 per dose.",
            ],
        )

    def run_screener(
        self,
        config: GateConfig,
        decisions: list[dict],
    ):
        client = ScriptedClient(decisions)
        review = run_pipeline(
            [
                DocumentInput(
                    file_path=str(self.itpp), doc_id="profile"
                )
            ],
            org="bmgf",
            intervention_class="drug",
            indication="malaria",
            config=config,
            llm_client=client,
        )
        return review, client

    def test_every_applicable_question_reaches_the_model(self) -> None:
        """Only a question whose own text restricts a class is withheld.

        Not whether the gate requires it now: an anticipatory question is read against
        the material exactly like a required one, because the distinction is about the
        review rather than about the documents.
        """
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?"),
            QuestionSpec(id="Q2", text="Is the plan costed?", requirement="anticipatory"),
            QuestionSpec(id="Q3", text="Has the procedure been tested?"),
            QuestionSpec(
                id="Q4",
                text="For biologics: are developability metrics stated?",
                applies_to=frozenset({"monoclonal_antibody"}),
            ),
        )
        review, client = self.run_screener(config, [])
        states = {item.id: item.state for item in review.assessments()}
        self.assertEqual(states["Q1"], "not_found")
        self.assertEqual(states["Q2"], "not_found")
        self.assertEqual(states["Q3"], "not_found")
        self.assertEqual(states["Q4"], "not_applicable")
        self.assertEqual(len(review.assessments()), 4)
        self.assertEqual(len(client.triage_calls), 3)

    def test_the_requirement_survives_onto_the_result(self) -> None:
        """Carried for the same reason as the text: a saved file has no bank to look it
        up in, and it is what separates a gate blocker from early warning."""
        config = bank(
            QuestionSpec(id="Q1", text="Is the plan costed?", requirement="anticipatory")
        )
        review, _ = self.run_screener(config, [])
        assessment = review.assessments()[0]
        self.assertEqual(assessment.state, "not_found")
        self.assertEqual(assessment.requirement, "anticipatory")

    def test_the_model_is_not_told_whether_a_question_is_required(self) -> None:
        """A model told a question is only anticipatory would read the material less
        carefully for it, and the same triage has to run either way."""
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?", requirement="anticipatory")
        )
        _, client = self.run_screener(config, [])
        self.assertNotIn("anticipatory", client.triage_calls[0].lower())

    def test_every_question_sees_the_same_material(self) -> None:
        """Identical context per call is what makes the prompt prefix cacheable."""
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?"),
            QuestionSpec(id="Q2", text="Is the plan costed?"),
        )
        _, client = self.run_screener(config, [])
        self.assertEqual(len(client.triage_calls), 2)
        prefixes = {call.split("Question (")[0] for call in client.triage_calls}
        self.assertEqual(len(prefixes), 1, "the material differed between questions")

    def test_the_uploaded_document_reaches_the_prompt(self) -> None:
        config = bank(QuestionSpec(id="Q1", text="Is dosing stated?"))
        _, client = self.run_screener(config, [])
        self.assertEqual(len(client.triage_calls), 1)
        self.assertIn("Dosing regimen", client.triage_calls[0])

    def test_an_answer_carries_the_blocks_the_document_produced(self) -> None:
        config = bank(
            QuestionSpec(id="Q1", text="Is dosing stated?")
        )
        # Discover the real block ids by running once, then answer citing one.
        first, _ = self.run_screener(config, [])
        self.assertTrue(first.blocks, "the document produced no blocks")
        block_id = first.blocks[0].id
        self.assertTrue(block_id.startswith("profile"), block_id)

        review, _ = self.run_screener(
            config,
            [
                {
                    "decision": DECISION_ANSWERED,
                    "statement": "The profile states one dose annually.",
                    "missing": "",
                    "block_ids": [block_id],
                }
            ],
        )
        answered = review.assessments()[0]
        self.assertEqual(answered.state, "answered")
        self.assertEqual(answered.cited_block_ids, [block_id])

    def test_operational_questions_are_assessed_rather_than_withheld(self) -> None:
        """No document holds these, but deciding that was a guess. Ask, and report."""
        config = bank(
            QuestionSpec(id="Q1", text="Has the procedure been tested?"),
            QuestionSpec(id="Q2", text="Would we fund this today?"),
        )
        review, client = self.run_screener(config, [])
        self.assertEqual(len(client.triage_calls), 2)
        self.assertEqual(
            [item.state for item in review.assessments()],
            ["not_found", "not_found"],
        )

    def test_a_bank_that_applies_to_nothing_fails_before_parsing(self) -> None:
        config = bank(
            QuestionSpec(
                id="Q1", text="Developability metrics?", applies_to=frozenset({"monoclonal_antibody"})
            )
        )
        with self.assertRaises(ValueError) as caught:
            self.run_screener(config, [])
        self.assertIn("drug", str(caught.exception))

    def test_a_run_without_documents_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            run_pipeline(
                [],
                org="bmgf",
                intervention_class="drug",
                indication="malaria",
                config=bank(QuestionSpec(id="Q1", text="t")),
                llm_client=ScriptedClient([]),
            )

    def test_the_shipped_bank_runs_end_to_end(self) -> None:
        """The real LCS bank, not a fixture: 80 questions, one document.

        Every question reaches the model, because no LCS question's text restricts
        itself to a class other than vaccine. That is the honest cost of not guessing.
        """
        config = find_config("bmgf", "lcs")
        review, client = self.run_screener(config, [])
        self.assertEqual(len(review.assessments()), len(config.questions()))
        self.assertEqual(
            [discipline.id for discipline in review.disciplines],
            [discipline.id for discipline in config.disciplines],
        )
        applicable = [q for _, q in config.questions() if q.applies("vaccine")]
        self.assertEqual(len(client.triage_calls), len(applicable))


if __name__ == "__main__":
    unittest.main()
