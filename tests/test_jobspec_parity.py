"""The acceptance jobspec differs from production only in the ways it is meant to.

Two near-identical deployment files drift the way two copies of anything drift:
someone raises a memory limit in production after an incident and the change
never reaches acceptance, so the environment that exists to catch the next one
no longer resembles the thing it is standing in for. Capacity is exactly what
failed here before - a 512 MB instance was OOM-killed mid-analysis - so a
smaller acceptance environment would validate correctness and miss that class of
failure entirely.

The check is textual on purpose. Parsing HCL would need a dependency the suite
does not otherwise have, and the property being defended is that the two files
say the same thing, which is a property of the text.

`ACCEPTANCE_RENAMES` is the whole list of permitted differences. Adding to it is
how you declare a new intentional divergence, and it should be hard to do by
accident.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "jobspec.nomad"
ACCEPTANCE = ROOT / "jobspec_acc.nomad"

# Applied to the acceptance file to bring it back to production's vocabulary.
ACCEPTANCE_RENAMES = (
    ("__REPO__NAME__-acc-", "__REPO__NAME__-"),
    ("__REPO__NAME___acc_", "__REPO__NAME___"),
    ("__REPO__NAME__-acc", "__REPO__NAME__"),
    ("nomad/jobs/__REPO__NAME__-acc", "nomad/jobs/__REPO__NAME__"),
    ("domain_acc", "domain_prod"),
    ("acceptance domain", "production domain"),
    ("# PDIS acceptance job.", "# PDIS production job."),
)


def _normalized_acceptance() -> list[str]:
    text = ACCEPTANCE.read_text()
    for acc_form, prod_form in ACCEPTANCE_RENAMES:
        text = text.replace(acc_form, prod_form)
    # The acceptance file carries one extra comment block explaining why it is a
    # copy. Comments cannot change behaviour, so they are not part of the check.
    return [line for line in text.splitlines() if not line.strip().startswith("#")]


def _production_lines() -> list[str]:
    return [
        line
        for line in PRODUCTION.read_text().splitlines()
        if not line.strip().startswith("#")
    ]


class JobspecParityTests(unittest.TestCase):
    def test_the_two_jobspecs_differ_only_by_environment_naming(self) -> None:
        self.assertEqual(
            _normalized_acceptance(),
            _production_lines(),
            "jobspec_acc.nomad and jobspec.nomad have diverged beyond the renames in "
            "ACCEPTANCE_RENAMES; add the difference there if it is deliberate",
        )

    def test_the_connector_is_never_exposed_through_the_ingress(self) -> None:
        """The connector holds SEMANTIC_SCHOLAR_API_KEY and authenticates with a
        bearer token only. Nothing but the absence of a routing tag keeps it off
        the public internet, and an absence is not visible in review the way a
        rule is - so it is asserted here instead."""
        for path in (PRODUCTION, ACCEPTANCE):
            with self.subTest(jobspec=path.name):
                text = path.read_text()
                start = text.index('group "tooluniverse"')
                group = text[start:]
                self.assertNotIn(
                    "traefik.enable=true",
                    group,
                    f"{path.name} exposes the ToolUniverse connector through Traefik",
                )

    def test_no_image_floats_on_a_mutable_tag(self) -> None:
        """Nomad re-pulls on reschedule. A moving tag means an allocation can
        change build without anyone deploying.

        The pipeline pushes a `latest` tag as well, following the platform
        template, but nothing here may reference it: `latest` is for a human
        pulling the newest image by hand, not for a scheduler deciding what to
        restart at three in the morning.
        """
        for path in (PRODUCTION, ACCEPTANCE):
            with self.subTest(jobspec=path.name):
                images = re.findall(r'image\s*=\s*"([^"]+)"', path.read_text())
                self.assertTrue(images, f"{path.name} declares no images")
                for image in images:
                    self.assertNotIn(":latest", image)
                    self.assertIn("__BUILD__NUMBER__", image)

    def test_every_jobspec_placeholder_is_substituted_by_the_pipeline(self) -> None:
        """A `__PLACEHOLDER__` the deploy step never fills reaches Nomad verbatim.

        The platform's pattern fills these with sed rather than Nomad variables,
        so nothing validates them: an unsubstituted name is accepted as a literal
        job name and the deploy silently produces the wrong thing. The declared
        `domain_*` variable is checked too, since that one does come through
        `NOMAD_VAR_`.
        """
        import yaml

        drone = yaml.safe_load_all((ROOT / ".drone.yml").read_text())
        pipelines = {p["name"]: p for p in drone if p}

        for jobspec, pipeline_name, domain_var in (
            (PRODUCTION, "Deploy to Production", "domain_prod"),
            (ACCEPTANCE, "Deploy to Acceptance", "domain_acc"),
        ):
            text = jobspec.read_text()
            step = pipelines[pipeline_name]["steps"][0]
            commands = " ".join(step["commands"])
            environment = step.get("environment", {})

            # Comments excluded: the header explains the mechanism and names a
            # placeholder generically, which is not a substitution anything is
            # expected to perform.
            directives = "\n".join(
                line for line in text.splitlines() if not line.strip().startswith("#")
            )

            # Apply the pipeline's own substitutions, then look for survivors.
            # Discovering placeholders by pattern cannot work: the platform's
            # names contain internal double underscores (`__REPO__NAME__`) and
            # are concatenated with suffixes (`__REPO__NAME___api`), so no
            # regex separates a placeholder from its neighbour reliably. What
            # can be checked is the property that matters - run the real seds,
            # and nothing placeholder-shaped is left.
            substituted = directives
            # Delimiter-agnostic: the repo and namespace seds use `/`, and the
            # credential seds use `|` because a base64 secret can contain a
            # slash. Capture whichever character follows `s` and match to it.
            for _, pattern in re.findall(r'sed -i "s(.)(.+?)\1', commands):
                substituted = substituted.replace(pattern, "substituted")

            leftover = sorted(set(re.findall(r"__\w*?__", substituted)))
            with self.subTest(jobspec=jobspec.name):
                self.assertEqual(
                    leftover,
                    [],
                    f"{pipeline_name} leaves {leftover} unsubstituted in "
                    f"{jobspec.name}; Nomad accepts them as literals",
                )

            with self.subTest(jobspec=jobspec.name, variable=domain_var):
                self.assertIn(f'variable "{domain_var}"', text)
                self.assertIn(f"NOMAD_VAR_{domain_var}", environment)

    def test_no_image_is_pushed_before_the_suite_passes(self) -> None:
        """Drone runs top-level pipelines concurrently unless a dependency says
        otherwise, so a verification pipeline sitting above a build pipeline in
        the file gates nothing. The first real build pushed an image while the
        suite was still failing, which is what this asserts against.

        The promote pipelines are exempt on purpose: `Verify` does not run on a
        promote event, and depending on a pipeline that did not run skips the
        dependent one. They deploy an image a push build already verified.
        """
        import yaml

        pipelines = [p for p in yaml.safe_load_all((ROOT / ".drone.yml").read_text()) if p]
        by_name = {p["name"]: p for p in pipelines}

        for name, pipeline in by_name.items():
            events = set(pipeline.get("trigger", {}).get("event") or [])
            builds_or_deploys = any(
                "docker" in step.get("image", "") or "nomad" in step.get("image", "")
                for step in pipeline["steps"]
            )
            if not builds_or_deploys or not events & {"push", "pull_request"}:
                continue
            with self.subTest(pipeline=name):
                self.assertIn(
                    "Verify",
                    pipeline.get("depends_on", []),
                    f"{name} can build or deploy while the suite is still failing",
                )

    def test_the_gateway_memory_and_run_cap_are_stated_together(self) -> None:
        """They are one decision: the cap is what the memory limit was sized for.
        Finding one without the other means the pair can be changed singly."""
        for path in (PRODUCTION, ACCEPTANCE):
            with self.subTest(jobspec=path.name):
                text = path.read_text()
                self.assertIn("MAX_CONCURRENT_RUNS", text)
                self.assertRegex(text, r"memory\s*=\s*2048")


if __name__ == "__main__":
    unittest.main()
