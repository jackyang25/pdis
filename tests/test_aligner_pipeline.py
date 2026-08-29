"""Aligner end to end: real DOCX files in, a complete set of one-way comparisons out.

The stages are unit-tested in `test_aligner.py`. What this covers is the wiring, which
is where the direction of a comparison is decided and where it would be lost: which
document's requirements are extracted, which document each verdict reads, and whether a
three-document run really produces two comparisons without anything in code knowing how
many documents there are.

The model client is a fake. What is being tested is the pipeline, not the provider.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from services.aligner import DocumentInput, load_config, run_pipeline
from shared.spans import span_block_ids


def write_docx(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(str(path))


class ScriptedClient:
    """Extracts a fixed number of requirements, then judges each one.

    Reads the block IDs it is allowed to cite out of the schema it was handed, so the
    citations it returns are always valid for whichever document it was actually given —
    which is what lets the assertions below prove the pipeline handed over the right one.
    """

    def __init__(self, requirements_per_document: int = 2) -> None:
        self.requirements_per_document = requirements_per_document
        self.extractions: list[dict] = []
        self.verdicts: list[dict] = []

    def call_structured(
        self, system_prompt, user_message, max_tokens, *, schema_name, schema, **_
    ):
        if schema_name == "aligner_requirements":
            offered = schema["properties"]["requirements"]["items"]["properties"][
                "spans"
            ]["items"]["properties"]["block_id"]["enum"]
            self.extractions.append({"message": user_message, "offered": offered})
            return {
                "requirements": [
                    {
                        "text": f"Requirement {index} from {offered[0].split('/')[0]}.",
                        "spans": [
                            {
                                "block_id": offered[0],
                                "start_line": 1,
                                "end_line": 1,
                            }
                        ],
                    }
                    for index in range(1, self.requirements_per_document + 1)
                ]
            }
        if schema_name == "aligner_requirement_verdict":
            offered = schema["properties"]["spans"]["items"]["properties"]["block_id"][
                "enum"
            ]
            self.verdicts.append({"message": user_message, "offered": offered})
            return {
                "verdict": "meets",
                "statement": "The document states it.",
                "spans": [
                    {"block_id": offered[0], "start_line": 1, "end_line": 1}
                ],
            }
        if schema_name == "chunker_section_labels":
            ids = schema["properties"]["labels"]["items"]["properties"]["id"]["enum"]
            taxonomy = schema["properties"]["labels"]["items"]["properties"][
                "section_label"
            ]["enum"]
            return {
                "labels": [
                    {"id": block_id, "section_label": taxonomy[0], "confidence": "high"}
                    for block_id in ids
                ]
            }
        return {}


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.paths = {
            "itpp": root / "profile.docx",
            "ctpp": root / "candidate.docx",
            "ipdp": root / "plan.docx",
        }
        write_docx(self.paths["itpp"], [
            "Target Product Profile",
            "Dosing regimen: one dose, annually.",
        ])
        write_docx(self.paths["ctpp"], [
            "Candidate Profile",
            "Dosing regimen: one dose, every two years.",
        ])
        write_docx(self.paths["ipdp"], [
            "Development Plan",
            "Phase 2 begins in Q3 and reads out in Q4.",
        ])

    def align(self, *source_types: str):
        client = ScriptedClient()
        result = run_pipeline(
            [
                DocumentInput(
                    file_path=str(self.paths[source_type]),
                    source_type=source_type,
                    doc_id=self.paths[source_type].stem,
                )
                for source_type in source_types
            ],
            org="bmgf",
            intervention_class="vaccine",
            indication="malaria",
            config=load_config(),
            llm_client=client,
        )
        return result, client

    def test_two_documents_produce_one_comparison_and_judge_every_requirement(self) -> None:
        result, client = self.align("itpp", "ctpp")

        self.assertEqual([edge.edge_id for edge in result.edges], ["itpp-to-ctpp"])
        self.assertEqual(len(client.extractions), 1)
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(
            [finding.requirement_id for finding in result.findings],
            ["itpp-to-ctpp/r-001", "itpp-to-ctpp/r-002"],
        )
        self.assertEqual(len(client.verdicts), len(result.findings))

    def test_requirements_come_from_the_reference_and_verdicts_read_the_other(self) -> None:
        """The direction, proved by which document each call was actually given."""
        _, client = self.align("itpp", "ctpp")

        extraction_docs = {
            block_id.split("/")[0] for block_id in client.extractions[0]["offered"]
        }
        self.assertEqual(extraction_docs, {"profile"})
        for call in client.verdicts:
            self.assertEqual(
                {block_id.split("/")[0] for block_id in call["offered"]}, {"candidate"}
            )

    def test_a_third_document_adds_a_comparison_without_being_counted_anywhere(self) -> None:
        """Two documents resolve one edge, three resolve two, and no code says so."""
        result, client = self.align("itpp", "ctpp", "ipdp")

        self.assertEqual(
            [edge.edge_id for edge in result.edges],
            ["itpp-to-ctpp", "ctpp-to-ipdp"],
        )
        self.assertEqual(len(client.extractions), 2)
        self.assertEqual(len(result.findings), 4)
        # Requirement IDs are namespaced by comparison, so the two sets cannot collide.
        self.assertEqual(
            sorted({finding.edge_id for finding in result.findings}),
            ["ctpp-to-ipdp", "itpp-to-ctpp"],
        )

    def test_the_cTPP_is_a_comparison_and_a_reference_in_one_run(self) -> None:
        """A side belongs to the comparison, never to the document."""
        _, client = self.align("itpp", "ctpp", "ipdp")

        read_for_extraction = [
            {block_id.split("/")[0] for block_id in call["offered"]}
            for call in client.extractions
        ]
        self.assertEqual(read_for_extraction, [{"profile"}, {"candidate"}])

    def test_every_finding_carries_both_sides_of_its_lineage(self) -> None:
        result, _ = self.align("itpp", "ctpp")
        blocks_by_doc: dict[str, set[str]] = {}
        for block in result.blocks:
            blocks_by_doc.setdefault(block.doc_id, set()).add(block.id)

        for finding in result.findings:
            self.assertTrue(finding.reference_spans)
            self.assertTrue(finding.comparison_spans)
            self.assertTrue(
                set(span_block_ids(finding.reference_spans))
                <= blocks_by_doc["profile"]
            )
            self.assertTrue(
                set(span_block_ids(finding.comparison_spans))
                <= blocks_by_doc["candidate"]
            )
            # The quote is the document's own text, not the model's: the fake client
            # only ever returns a line range, and every quote here came out of a block.
            for span in finding.reference_spans + finding.comparison_spans:
                self.assertTrue(span.quote)

    def test_progress_reports_both_analysis_steps(self) -> None:
        """A run that only reported parsing would look finished halfway through."""
        seen: list[str] = []

        def progress(stage, **_):
            if stage not in seen:
                seen.append(stage)

        run_pipeline(
            [
                DocumentInput(
                    file_path=str(self.paths[source_type]),
                    source_type=source_type,
                    doc_id=self.paths[source_type].stem,
                )
                for source_type in ("itpp", "ctpp")
            ],
            org="bmgf",
            intervention_class="vaccine",
            indication="malaria",
            config=load_config(),
            llm_client=ScriptedClient(),
            progress_callback=progress,
        )
        self.assertEqual(seen, ["parse", "requirements", "compare"])


if __name__ == "__main__":
    unittest.main()
