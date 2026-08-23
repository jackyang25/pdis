"""The manifest, and the build that reads it.

Everything checkable is checked before a single model call. A build that fails on its
fortieth document because one manifest row named a document type chunker cannot parse has
spent real money to learn what a file read would have said, so `load_manifest` refuses
early and says which row and why.

The manifest is also where the line between declared and extracted sits. A row carries
exactly the fields a person reads off a cover page and whose error would otherwise be
invisible - most of all `source_type`, because mislabelling a cTPP as an iTPP silently
turns one candidate's commitment into a class-level ambition in every row below it, and no
downstream check would notice. Everything else about a document is extracted from its
prose and checked against a quote.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_archivist_corpus import _classify, _parse, _report, main
from services.archivist import (
    Corpus,
    CorpusRecord,
    ManifestEntry,
    load_manifest,
    resolve_source,
)
from services.archivist.stages.classifier import ClassificationReport
from services.archivist.stages.extractor import ExtractionReport
from services.chunker import available_configs

GOOD = """
documents:
  - id: mal-itpp-v3
    file: malaria_itpp_v3.docx
    title: Malaria Vaccine iTPP v3
    org: bmgf
    source_type: itpp
    intervention_class: vaccine
    indication: malaria
"""


def written(body: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "manifest.yaml"
    path.write_text(body, encoding="utf-8")
    return path


class ManifestTest(unittest.TestCase):
    def test_a_good_row_becomes_a_corpus_document(self) -> None:
        entries = load_manifest(written(GOOD))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].document().source_type, "itpp")

    def test_the_build_time_path_never_reaches_the_corpus(self) -> None:
        """It names a path on the machine that ran the build, not a fact about the document.

        A committed artifact carrying it would describe someone's laptop.
        """
        document = load_manifest(written(GOOD))[0].document()
        self.assertNotIn("file", document.__dataclass_fields__)

    def test_a_document_type_chunker_cannot_parse_is_refused(self) -> None:
        """WHO PPCs are a real gap: there is no parsing config for them.

        Refused at manifest load rather than discovered mid-build.
        """
        with self.assertRaises(ValueError) as caught:
            load_manifest(written(GOOD.replace("source_type: itpp", "source_type: ppc")))
        self.assertIn("cannot be parsed", str(caught.exception))

    def test_every_source_type_the_manifest_accepts_is_one_a_config_declares(self) -> None:
        """The manifest keeps no second list of document types.

        Which types exist is chunker's fact, asked for rather than mirrored - a mirror
        would be a second answer free to disagree the day a config is added.
        """
        declared = {(c.org, c.source_type, c.intervention_class) for c in available_configs()}
        self.assertIn(("bmgf", "itpp", "vaccine"), declared)
        entry = load_manifest(written(GOOD))[0]
        self.assertIn(
            (entry.org, entry.source_type, entry.intervention_class), declared
        )

    def test_a_class_with_no_columns_is_refused_with_the_reason(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load_manifest(
                written(GOOD.replace("intervention_class: vaccine", "intervention_class: drug"))
            )
        self.assertIn("no corpus columns declared", str(caught.exception))

    def test_an_indication_outside_the_vocabulary_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load_manifest(written(GOOD.replace("indication: malaria", "indication: ebola")))

    def test_a_missing_field_is_named(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load_manifest(written(GOOD.replace("    title: Malaria Vaccine iTPP v3\n", "")))
        self.assertIn("title", str(caught.exception))

    def test_a_field_the_manifest_does_not_support_is_refused_not_ignored(self) -> None:
        """Someone declaring something expects it to be honoured."""
        with self.assertRaises(ValueError) as caught:
            load_manifest(written(GOOD + "    notes: check this one\n"))
        self.assertIn("does not support", str(caught.exception))

    def test_a_duplicate_id_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            load_manifest(written(GOOD + GOOD.split("documents:")[1]))
        self.assertIn("same id", str(caught.exception))

    def test_a_duplicate_file_is_refused(self) -> None:
        """Two ids over one file would double every count the archive reports."""
        second = GOOD.split("documents:")[1].replace("mal-itpp-v3", "mal-itpp-v3-copy")
        with self.assertRaises(ValueError) as caught:
            load_manifest(written(GOOD + second))
        self.assertIn("same file", str(caught.exception))

    def test_an_empty_manifest_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            load_manifest(written("documents: []\n"))

    def test_an_absent_manifest_says_where_it_looked(self) -> None:
        with self.assertRaises(LookupError):
            load_manifest(Path(tempfile.mkdtemp()) / "nope.yaml")


class SourceResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.entry = ManifestEntry(
            id="d1",
            file="profile.docx",
            title="T",
            org="bmgf",
            source_type="itpp",
            intervention_class="vaccine",
            indication="malaria",
        )

    def test_a_file_inside_the_folder_resolves(self) -> None:
        (self.root / "profile.docx").write_bytes(b"")
        self.assertEqual(resolve_source(self.entry, self.root).name, "profile.docx")

    def test_an_absent_file_says_which_document(self) -> None:
        with self.assertRaises(LookupError) as caught:
            resolve_source(self.entry, self.root)
        self.assertIn("d1", str(caught.exception))

    def test_a_path_escaping_the_folder_is_refused(self) -> None:
        """A manifest is reviewed content, and it is still a file that names paths."""
        import dataclasses

        escaping = dataclasses.replace(self.entry, file="../outside.docx")
        with self.assertRaises(ValueError) as caught:
            resolve_source(escaping, self.root)
        self.assertIn("points outside", str(caught.exception))


class BuildPhaseTest(unittest.TestCase):
    def test_parsing_groups_by_document_type_and_indication(self) -> None:
        """Chunker's batch entry point takes one parsing config and one indication.

        The grouping is not a parallelism decision: the pool stays flat inside each group,
        and the groups run in sequence.
        """
        entries = (
            ManifestEntry("a", "a.docx", "A", "bmgf", "itpp", "vaccine", "malaria"),
            ManifestEntry("b", "b.docx", "B", "bmgf", "itpp", "vaccine", "malaria"),
            ManifestEntry("c", "c.docx", "C", "bmgf", "ctpp", "vaccine", "rsv"),
        )
        root = Path(tempfile.mkdtemp())
        sources = {}
        for entry in entries:
            (root / entry.file).write_bytes(b"")
            sources[entry.id] = root / entry.file

        batches: list[tuple] = []

        class Result:
            def __init__(self, doc_id):
                self.parse_error = ""
                self.mapping_error = ""
                self.blocks = [f"block for {doc_id}"]

        import scripts.build_archivist_corpus as build

        original = build.run_pipeline_batch
        try:
            def fake_batch(jobs, *, config, llm_client_factory, max_workers, indication):
                batches.append((config.type_key, indication, tuple(j[1] for j in jobs)))
                return [Result(job[1]) for job in jobs]

            build.run_pipeline_batch = fake_batch
            blocks, failures = _parse(entries, sources, lambda: None)
        finally:
            build.run_pipeline_batch = original

        self.assertEqual(failures, [])
        self.assertEqual(sorted(blocks), ["a", "b", "c"])
        self.assertEqual(
            batches,
            [
                ("bmgf_itpp_vaccine", "malaria", ("a", "b")),
                ("bmgf_ctpp_vaccine", "rsv", ("c",)),
            ],
        )

    def test_a_document_whose_labels_failed_is_still_read(self) -> None:
        """Unlabelled blocks still carry their text and heading path.

        Only `section_label` is poorer, so dropping the document would lose more than it
        protects. The failure is recorded so a reviewer knows why.
        """
        entry = ManifestEntry("a", "a.docx", "A", "bmgf", "itpp", "vaccine", "malaria")
        root = Path(tempfile.mkdtemp())
        (root / "a.docx").write_bytes(b"")

        class Result:
            parse_error = ""
            mapping_error = "the mapper timed out"
            blocks = ["a block"]

        import scripts.build_archivist_corpus as build

        original = build.run_pipeline_batch
        try:
            build.run_pipeline_batch = lambda jobs, **kwargs: [Result()]
            blocks, failures = _parse((entry,), {"a": root / "a.docx"}, lambda: None)
        finally:
            build.run_pipeline_batch = original

        self.assertIn("a", blocks)
        self.assertTrue(any("section labels unavailable" in note for note in failures))

    def test_a_document_that_failed_to_parse_is_dropped(self) -> None:
        """There is nothing to read, so a grid for it would be silence it never gave."""
        entry = ManifestEntry("a", "a.docx", "A", "bmgf", "itpp", "vaccine", "malaria")
        root = Path(tempfile.mkdtemp())
        (root / "a.docx").write_bytes(b"")

        class Result:
            parse_error = "not a DOCX"
            mapping_error = ""
            blocks: list = []

        import scripts.build_archivist_corpus as build

        original = build.run_pipeline_batch
        try:
            build.run_pipeline_batch = lambda jobs, **kwargs: [Result()]
            blocks, failures = _parse((entry,), {"a": root / "a.docx"}, lambda: None)
        finally:
            build.run_pipeline_batch = original

        self.assertEqual(blocks, {})
        self.assertTrue(any("parse failed" in note for note in failures))

    def test_classification_only_touches_the_class_it_was_asked_about(self) -> None:
        entries = (
            ManifestEntry("a", "a.docx", "A", "bmgf", "itpp", "vaccine", "malaria"),
        )
        records = [
            CorpusRecord(
                document_id="a",
                attribute="vaccine.target_population",
                status="stated",
                stated="infants",
                quote="infants aged 6-14 weeks",
                block_text="Target: infants aged 6-14 weeks.",
                block_id="b1",
                section_label="s",
            )
        ]

        class Tagger:
            def call_structured(self, *args, **kwargs):
                return {"tags": ["infants"], "reason": ""}

        out, report = _classify(records, entries, Tagger())
        self.assertEqual(out[0].tags, ("infants",))
        self.assertEqual(report.tagged, 1)


class BuildReportTest(unittest.TestCase):
    def test_the_report_carries_what_the_corpus_cannot(self) -> None:
        """Discarded readings leave no row, so only the report can count them.

        These two numbers decide whether the artifact is usable at all, and neither is
        visible in the archive.
        """
        extraction = ExtractionReport(calls=8, silent=7, unverified=2, paraphrased=1)
        report = _report(
            Corpus(built_at="2026-08-23T00:00:00+00:00"),
            ["d1: parse failed - not a DOCX"],
            extraction,
            ClassificationReport(calls=1, tagged=1),
        )
        self.assertEqual(report["extraction"]["discarded_unverified_quote"], 2)
        self.assertEqual(report["extraction"]["discarded_paraphrase"], 1)
        self.assertEqual(report["parse_failures"], ["d1: parse failed - not a DOCX"])

    def test_the_report_is_not_part_of_the_corpus(self) -> None:
        """It is a fact about the build, not about the archive."""
        self.assertNotIn("extraction", Corpus.__dataclass_fields__)
        self.assertNotIn("parse_failures", Corpus.__dataclass_fields__)


class PartialCorpusTest(unittest.TestCase):
    """One rule for one question: is this every document the manifest declared?

    `--only` and a document that would not parse both mean no. They used to be handled
    differently - the first refused to write, the second wrote a short corpus to the
    canonical path - which is a partial corpus committed as a complete one. Every count
    this tool reports would then be wrong by the documents it never saw, silently.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        (self.root / "malaria_itpp_v3.docx").write_bytes(b"")
        self.manifest = written(GOOD)
        self.out = Path(tempfile.mkdtemp()) / "corpus.json"
        self.report = Path(tempfile.mkdtemp()) / "report.json"

    def _run(self, *extra: str) -> int:
        import scripts.build_archivist_corpus as build

        class Result:
            parse_error = "not a DOCX"
            mapping_error = ""
            blocks: list = []

        original_batch = build.run_pipeline_batch
        original_client = build.OpenAIClient
        try:
            build.run_pipeline_batch = lambda jobs, **kwargs: [Result() for _ in jobs]
            build.OpenAIClient = lambda *a, **k: None
            return build.main(
                [
                    "--documents", str(self.root),
                    "--manifest", str(self.manifest),
                    "--out", str(self.out),
                    "--report", str(self.report),
                    *extra,
                ]
            )
        finally:
            build.run_pipeline_batch = original_batch
            build.OpenAIClient = original_client

    def test_a_document_that_would_not_parse_stops_the_write(self) -> None:
        self.assertEqual(self._run(), 1)
        self.assertFalse(self.out.exists(), "a partial corpus was written to --out")

    def test_the_report_is_still_written_so_the_failure_is_readable(self) -> None:
        """The whole point of the report: say why, even when there is nothing to commit."""
        self._run()
        self.assertTrue(self.report.exists())
        import json

        self.assertTrue(json.loads(self.report.read_text())["parse_failures"])

    def test_allow_partial_writes_it_anyway(self) -> None:
        self.assertEqual(self._run("--allow-partial"), 1)
        self.assertTrue(self.out.exists())


class DryRunTest(unittest.TestCase):
    def test_a_dry_run_validates_the_inputs_and_stops(self) -> None:
        """The cheap half of the build, runnable without an API key."""
        root = Path(tempfile.mkdtemp())
        (root / "malaria_itpp_v3.docx").write_bytes(b"")
        code = main(
            [
                "--documents",
                str(root),
                "--manifest",
                str(written(GOOD)),
                "--dry-run",
            ]
        )
        self.assertEqual(code, 0)

    def test_a_dry_run_over_a_bad_manifest_fails_before_any_call(self) -> None:
        root = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            main(
                [
                    "--documents",
                    str(root),
                    "--manifest",
                    str(written(GOOD.replace("source_type: itpp", "source_type: ppc"))),
                    "--dry-run",
                ]
            )


if __name__ == "__main__":
    unittest.main()
