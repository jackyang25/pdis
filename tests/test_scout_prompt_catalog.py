"""The catalog must cover every stage prompt and must not change any of them.

The snapshot is the proof that the seam work — renaming builders, extracting
inline prompts — never altered a string a provider receives. Regenerate it only
when a prompt is deliberately reworded.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from services.scout.prompt_catalog import PROMPT_CATALOG

SNAPSHOT = Path(__file__).parent / "data" / "prompt_snapshot.json"
STAGES = Path(__file__).resolve().parents[1] / "services" / "scout" / "stages"
BUILDER = re.compile(r"^def (_?[a-z_]*system_prompt[a-z_]*)\(", re.MULTILINE)


def rendered_prompts() -> dict[str, str]:
    return {entry.id: entry.render() for entry in PROMPT_CATALOG}


class PromptCatalogTest(unittest.TestCase):
    def test_prompt_text_matches_snapshot(self) -> None:
        self.assertTrue(SNAPSHOT.exists(), "prompt snapshot has not been recorded")
        self.assertEqual(rendered_prompts(), json.loads(SNAPSHOT.read_text()))

    def test_prompt_ids_are_unique(self) -> None:
        ids = [entry.id for entry in PROMPT_CATALOG]
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_every_stage_prompt_builder_is_catalogued(self) -> None:
        exposed = {
            f"{path.stem}.{name}"
            for path in sorted(STAGES.glob("*.py"))
            for name in BUILDER.findall(path.read_text())
        }
        catalogued = {
            f"{entry.stage}.{entry.builder_name}"
            for entry in PROMPT_CATALOG
        }
        self.assertEqual(
            exposed - catalogued,
            set(),
            "a stage exposes a prompt builder that the catalog does not declare",
        )


if __name__ == "__main__":
    unittest.main()
