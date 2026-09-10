from __future__ import annotations

import unittest
import io
import tempfile
import threading
import yaml
from pathlib import Path
from dataclasses import asdict
from fastapi.testclient import TestClient
from unittest.mock import patch
from api.main import app

from services.inspector.configuration import (
    PRODUCT_FACT_KEYS,
    find_profile,
    resolve_profile,
    load_profiles,
    load_rubric,
)
from services.chunker import ContentBlock, ImageAsset
from services.inspector.pipeline import inspect_blocks_with_profile, run_profile_pipeline
from services.inspector.contract import validate_aggregate_result_contract
from services.inspector import available_configs, find_config, has_config


class ProfileResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = find_profile("bmgf", "ctpp", "drug")

    def test_template_library_is_metadata_not_requirement_lineage(self) -> None:
        from services.inspector.pipeline import _rubric_snapshot

        rubric = resolve_profile(self.profile, {})[0].rubric
        self.assertEqual(rubric.display_name, "PDID template: cTPP")
        snapshot = _rubric_snapshot(rubric, [])
        self.assertEqual(snapshot.reference_url, rubric.reference_url)
        self.assertTrue(snapshot.reference_url.startswith("https://bmgf.sharepoint.com/"))
        self.assertEqual(snapshot.sources, [])
        self.assertTrue(all(not unit.source_refs for section in rubric.config.sections
                            for unit in section.variables or [section]))

    def test_document_lookup_follows_profile_reference_not_filename(self) -> None:
        from services.inspector.configuration import CONFIGS_DIR, PROFILES_PATH

        catalog = yaml.safe_load(PROFILES_PATH.read_text())
        profile = next(item for item in catalog["profiles"] if (
            item["org"], item["source_type"], item["intervention_class"]
        ) == ("bmgf", "ctpp", "drug"))
        content = yaml.safe_load((CONFIGS_DIR / profile["document_config"]).read_text())
        content["display_name"] = "Explicitly referenced PDID rubric"
        with tempfile.TemporaryDirectory() as directory:
            rubric_path = Path(directory) / "independently-named-rubric.yaml"
            rubric_path.write_text(yaml.safe_dump(content))
            profile["document_config"] = str(rubric_path)
            catalog_path = Path(directory) / "catalog.yaml"
            catalog_path.write_text(yaml.safe_dump(catalog))
            with patch("services.inspector.configuration.PROFILES_PATH", catalog_path):
                self.assertEqual(find_config("bmgf", "ctpp", "drug").display_name,
                                 "Explicitly referenced PDID rubric")
                self.assertTrue(has_config("bmgf", "ctpp", "drug"))
                self.assertFalse(has_config("absent", "ctpp", "drug"))
                self.assertIn("Explicitly referenced PDID rubric",
                              [config.display_name for config in available_configs()])
                with self.assertRaises(LookupError):
                    find_config("absent", "ctpp", "drug")

    def test_missing_e14_facts_require_context(self) -> None:
        resolutions = resolve_profile(self.profile, {})
        e14 = next(item for item in resolutions if item.rubric_id.startswith("ich-e14"))
        self.assertEqual(e14.status, "needs_context")
        self.assertEqual(set(e14.required_facts), set(PRODUCT_FACT_KEYS))

    def test_any_disqualifying_e14_fact_is_outside_scope(self) -> None:
        resolutions = resolve_profile(
            self.profile,
            {"small_molecule": "no", "systemic_exposure": "yes", "antiarrhythmic": "no"},
        )
        e14 = next(item for item in resolutions if item.rubric_id.startswith("ich-e14"))
        self.assertEqual(e14.status, "outside_review_scope")

    def test_confirmed_e14_scope_is_included(self) -> None:
        resolutions = resolve_profile(
            self.profile,
            {"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"},
        )
        e14 = next(item for item in resolutions if item.rubric_id.startswith("ich-e14"))
        self.assertEqual(e14.status, "included")

    def test_unknown_or_invalid_fact_never_silently_includes(self) -> None:
        resolutions = resolve_profile(
            self.profile,
            {"small_molecule": "unknown", "systemic_exposure": "yes", "antiarrhythmic": "no"},
        )
        e14 = next(item for item in resolutions if item.rubric_id.startswith("ich-e14"))
        self.assertEqual(e14.status, "needs_context")
        with self.assertRaisesRegex(ValueError, "small_molecule"):
            resolve_profile(self.profile, {"small_molecule": "maybe"})

    def test_unexpected_fact_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unexpected"):
            resolve_profile(self.profile, {"dosage_form": "tablet"})

    def test_profile_preserves_the_existing_bmgf_rubric_content(self) -> None:
        bmgf = resolve_profile(self.profile, {})[0].rubric
        self.assertIsNotNone(bmgf)
        self.assertEqual(asdict(bmgf.config), asdict(find_config("bmgf", "ctpp", "drug")))

    def test_neutral_guideline_definition_is_bound_to_profile_context(self) -> None:
        mab = find_profile("bmgf", "ctpp", "monoclonal_antibody")
        guideline = resolve_profile(mab, {})[1].rubric
        self.assertEqual(guideline.config.intervention_class, "monoclonal_antibody")

    def test_duplicate_rubric_references_fail_catalog_loading(self) -> None:
        catalog = {
            "fact_definitions": [
                {"key": key, "label": key, "description": key}
                for key in PRODUCT_FACT_KEYS
            ],
            "profiles": [{
                "org": "bmgf", "source_type": "ctpp", "intervention_class": "drug",
                "document_config": "rubrics/pdid/pdid-ctpp-drug.yaml",
                "rubrics": [
                    {"id": "bmgf", "revision": "1.0", "definition": "pdid/pdid.yaml"},
                    {"id": "bmgf", "revision": "1.0", "definition": "pdid/pdid.yaml"},
                ],
            }],
        }
        with patch("services.inspector.configuration._load_yaml", return_value=catalog):
            with self.assertRaisesRegex(ValueError, "duplicate IDs"):
                load_profiles()

    def test_whole_document_rubric_cannot_omit_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsourced.yaml"
            path.write_text(
                """id: unsourced
revision: '1'
org: bmgf
source_type: ctpp
intervention_class: drug
display_name: Unsourced
authority: Test
scope: Test scope
evidence_scope: whole_document
sources: []
sections:
  - name: Requirement
    description: A requirement
    source_refs: [missing-source]
"""
            )
            with self.assertRaisesRegex(ValueError, "must declare sources"):
                load_rubric(path)

    def test_empty_source_catalog_does_not_allow_dangling_refs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dangling.yaml"
            path.write_text(
                """id: dangling
revision: '1'
org: bmgf
source_type: ctpp
intervention_class: drug
display_name: Dangling
authority: Test
scope: Test scope
evidence_scope: mapped_section
sources: []
sections:
  - name: Requirement
    description: A requirement
    source_refs: [missing-source]
"""
            )
            with self.assertRaisesRegex(ValueError, "invalid source_refs"):
                load_rubric(path)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = find_profile("bmgf", "ctpp", "drug")

    def test_profile_publishes_fact_controls_without_frontend_policy(self) -> None:
        controls = self.profile.fact_definitions
        self.assertEqual([item.key for item in controls], list(PRODUCT_FACT_KEYS))
        self.assertTrue(all(item.options == ["yes", "no", "unknown"] for item in controls))
        self.assertTrue(all(item.required is False for item in controls))

    def test_http_catalog_returns_profile_owned_controls(self) -> None:
        response = TestClient(app).get(
            "/api/configs/inspector",
            params={"org": "bmgf", "source_type": "ctpp", "intervention_class": "drug"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["key"] for item in response.json()["applicability_facts"]],
            list(PRODUCT_FACT_KEYS),
        )

    def test_http_catalog_has_no_e14_controls_for_unrelated_profile(self) -> None:
        response = TestClient(app).get(
            "/api/configs/inspector",
            params={"org": "bmgf", "source_type": "itpp", "intervention_class": "vaccine"},
        )
        self.assertEqual(response.json()["applicability_facts"], [])

    def test_run_rejects_malformed_facts_before_provider_composition(self) -> None:
        response = TestClient(app).post(
            "/api/inspector/run",
            files={"file": ("profile.docx", io.BytesIO(b"x"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={
                "org": "bmgf", "source_type": "ctpp", "intervention_class": "drug",
                "indication": "malaria", "applicability_facts": '{"small_molecule":"maybe"}',
            },
        )
        self.assertEqual(response.status_code, 422)


class _SpecifiedClient:
    def __init__(self) -> None:
        self.schema_names: list[str] = []

    def call_structured(self, _system, _message, *_args, schema_name, schema, **_kwargs):
        self.schema_names.append(schema_name)
        if schema_name == "inspector_cross_section_consistency":
            return {"findings": []}
        block_id = schema["properties"]["block_ids"]["items"]["enum"][0]
        return {"verdict": "specified", "statement": "", "block_ids": [block_id]}


class AggregateRunTests(unittest.TestCase):
    def test_rubrics_share_one_bounded_queue_and_monotonic_progress(self) -> None:
        profile = find_profile("bmgf", "ctpp", "drug")
        facts = {"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"}
        template = find_config("bmgf", "ctpp", "drug")
        blocks = [ContentBlock(
            id=f"candidate:b{index}", doc_id="candidate", ordinal=index,
            block_type="paragraph", content=f"Evidence for {section.name}",
            heading_stack=[], structural_meta={}, style_hint={}, section_label=section.name,
        ) for index, section in enumerate(template.sections)]
        lock = threading.Lock()
        guideline_started = threading.Event()
        active = peak = calls = 0
        consistency_calls = 0
        progress = []

        class ConcurrentClient:
            def call_structured(self, _system, _message, *_args, schema_name, schema, **_kwargs):
                nonlocal active, peak, calls, consistency_calls
                if schema_name == "inspector_cross_section_consistency":
                    consistency_calls += 1
                    if active:
                        raise AssertionError("Consistency overlapped unfinished assessments")
                    return {"findings": []}
                ids = schema["properties"]["block_ids"]["items"]["enum"]
                with lock:
                    active += 1
                    peak = max(peak, active)
                    calls += 1
                try:
                    if len(ids) == len(blocks):
                        guideline_started.set()
                    elif not guideline_started.wait(timeout=3):
                        raise AssertionError("Guideline work waited for the template to finish")
                    return {"verdict": "specified", "statement": "", "block_ids": [ids[0]]}
                finally:
                    with lock:
                        active -= 1

        with patch("services.inspector.stages.assessor.MAX_PARALLEL_UNIT_CALLS", 2):
            result = inspect_blocks_with_profile(
                blocks, profile=profile, applicability_facts=facts, llm_client=ConcurrentClient(),
                progress_callback=lambda stage, **counts: progress.append((stage, counts)),
            )
        self.assertEqual(peak, 2)
        self.assertEqual(consistency_calls, 1)
        self.assertEqual([review.rubric.id for review in result.reviews],
                         ["bmgf", "ich-e4-ctpp", "ich-e14-ctpp", "ich-e9-ctpp",
                          "ich-e10-ctpp", "ich-q8-ctpp"])
        units = [unit for review in result.reviews for section in review.sections for unit in section.units]
        self.assertEqual(calls, len(units))
        assessment_progress = [counts for stage, counts in progress if stage == "assess"]
        self.assertEqual(assessment_progress,
                         [{"completed": n, "total": len(units)} for n in range(len(units) + 1)])
        self.assertEqual(progress[-1][0], "consistency")

    def test_failed_rubric_never_publishes_a_partial_run_or_runs_consistency(self) -> None:
        profile = find_profile("bmgf", "ctpp", "drug")
        block = ContentBlock(id="candidate:other", doc_id="candidate", ordinal=1,
                             block_type="paragraph", content="Evidence", heading_stack=[],
                             structural_meta={}, style_hint={}, section_label="Other")
        template = find_config("bmgf", "ctpp", "drug")
        mapped = [ContentBlock(
            id=f"candidate:mapped{index}", doc_id="candidate", ordinal=index + 2,
            block_type="paragraph", content="Mapped evidence", heading_stack=[],
            structural_meta={}, style_hint={}, section_label=section.name,
        ) for index, section in enumerate(template.sections[:2])]
        class FailedClient:
            def call_structured(self, *_args, schema_name, **_kwargs):
                if schema_name == "inspector_cross_section_consistency":
                    raise AssertionError("Consistency must not run after an assessment failure")
                return None
        with self.assertRaisesRegex(ValueError, "could not assess"):
            inspect_blocks_with_profile([block, *mapped], profile=profile, applicability_facts={},
                                        llm_client=FailedClient())

    def test_guidelines_read_other_blocks_and_ids_match_snapshots(self) -> None:
        profile = find_profile("bmgf", "ctpp", "drug")
        block = ContentBlock(
            id="candidate:other", doc_id="candidate", ordinal=1,
            block_type="paragraph", content="Dose selection uses exposure-response evidence.",
            heading_stack=[], structural_meta={}, style_hint={}, section_label="Other",
        )
        result = inspect_blocks_with_profile(
            [block], profile=profile,
            applicability_facts={"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"},
            llm_client=_SpecifiedClient(),
        )
        self.assertEqual(len(result.reviews), 6)
        for guideline in result.reviews[1:]:
            with self.subTest(rubric=guideline.rubric.id):
                self.assertTrue(all(section.mapped_block_ids == [] for section in guideline.sections))
                self.assertTrue(all(unit.cited_block_ids == [block.id] for section in guideline.sections for unit in section.units))
                self.assertEqual(
                    [unit.id for section in guideline.sections for unit in section.units],
                    [item.id for item in guideline.rubric.requirements],
                )
                self.assertTrue(all(item.id.startswith(guideline.rubric.id + "::") for item in guideline.rubric.requirements))

    def test_parse_and_consistency_run_once_and_images_are_retained(self) -> None:
        profile = find_profile("bmgf", "ctpp", "drug")
        block = ContentBlock(
            id="candidate:image", doc_id="candidate", ordinal=1, block_type="image",
            content="Dose-response figure", heading_stack=[], structural_meta={}, style_hint={},
            section_label="Other",
            image=ImageAsset("image/png", "AA==", "sha", "image/png", 1, 1),
        )
        mapped = [
            ContentBlock(id="candidate:intro", doc_id="candidate", ordinal=2, block_type="paragraph", content="Introduction.", heading_stack=[], structural_meta={}, style_hint={}, section_label="Introduction"),
            ContentBlock(id="candidate:instructions", doc_id="candidate", ordinal=3, block_type="paragraph", content="Instructions.", heading_stack=[], structural_meta={}, style_hint={}, section_label="Instructions for Use"),
        ]
        client = _SpecifiedClient()
        with patch("services.inspector.pipeline.chunker_run_pipeline", return_value=[block, *mapped]) as parse:
            result = run_profile_pipeline(
                "/tmp/candidate.docx", profile=profile,
                applicability_facts={"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"},
                llm_client=client, doc_id="candidate",
            )
        self.assertEqual(parse.call_count, 1)
        self.assertEqual(client.schema_names.count("inspector_cross_section_consistency"), 1)
        self.assertIs(result.blocks[0].image, block.image)

    def test_snapshot_freezes_authored_text_and_contract_rejects_bad_citation(self) -> None:
        profile = find_profile("bmgf", "ctpp", "drug")
        block = ContentBlock(
            id="candidate:other", doc_id="candidate", ordinal=1, block_type="paragraph",
            content="Dose selection evidence.", heading_stack=[], structural_meta={}, style_hint={}, section_label="Other",
        )
        facts = {"small_molecule": "yes", "systemic_exposure": "yes", "antiarrhythmic": "no"}
        result = inspect_blocks_with_profile([block], profile=profile, applicability_facts=facts, llm_client=_SpecifiedClient())
        resolutions = resolve_profile(profile, facts)
        configs = {item.rubric.id: item.rubric.config for item in resolutions if item.status == "included"}
        guideline = result.reviews[1]
        self.assertEqual(guideline.rubric.stage_guidance, configs[guideline.rubric.id].stage_guidance)
        spec = configs[guideline.rubric.id].sections[0]
        self.assertEqual(guideline.rubric.requirements[0].description, spec.description)
        guideline.sections[0].units[0].cited_block_ids = ["candidate:unknown"]
        with self.assertRaisesRegex(ValueError, "outside its scope"):
            validate_aggregate_result_contract(result, configs)


if __name__ == "__main__":
    unittest.main()
