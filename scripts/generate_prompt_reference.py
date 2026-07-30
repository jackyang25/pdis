"""Generate the published prompt reference from Scout's prompt catalog.

The catalog and the stage builders are the authority. This script only renders
them into a file the documentation page and Assistant can read, because the web
layer cannot import a service. Run it after changing any prompt; a test asserts
the committed file matches this output.

    .venv/bin/python scripts/generate_prompt_reference.py
"""

from __future__ import annotations

import json
from pathlib import Path

from services.scout.models import load_config
from services.scout.prompt_catalog import PROMPT_CATALOG

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "shared" / "prompt_reference.json"
CONFIG_DIR = ROOT / "services" / "scout" / "configs"

VERSION = 1

# Per configuration domain content a prompt inserts at run time. Listed once
# here rather than inlined into every prompt that carries the slot.
CONFIG_TEXT_FIELDS = (
    "drift_framing",
    "evidence_framing",
    "precedent_framing",
    "quantitative_target_framing",
    "query_extraction_guidance",
)


def build_reference() -> dict:
    """Render every catalogued prompt plus the configuration text they insert."""
    prompts = [
        {
            "id": entry.id,
            "stage": entry.stage,
            "title": entry.title,
            "builder": entry.builder_name,
            "framing_slot": entry.framing_slot,
            "produces": {
                "result_fields": list(entry.result_fields),
                "ui_labels": list(entry.ui_labels),
            },
            "text": entry.render(),
        }
        for entry in PROMPT_CATALOG
    ]

    framings = []
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        # A product config is named {org}_{source_type}_{intervention_class}.yaml,
        # matching find_config. The template and the shared evidence methodology
        # live in the same directory and are not configs.
        if len(path.stem.split("_")) != 3 or path.stem != path.stem.lower():
            continue
        config = load_config(str(path))
        for key in CONFIG_TEXT_FIELDS:
            text = (getattr(config, key, "") or "").strip()
            if not text:
                continue
            framings.append(
                {
                    "key": key,
                    "org": config.org,
                    "source_type": config.source_type,
                    "intervention_class": config.intervention_class,
                    "text": text,
                }
            )

    return {"version": VERSION, "prompts": prompts, "framings": framings}


def main() -> None:
    reference = build_reference()
    REFERENCE.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n")
    print(
        f"wrote {REFERENCE.relative_to(ROOT)}: "
        f"{len(reference['prompts'])} prompts, {len(reference['framings'])} configuration texts"
    )


if __name__ == "__main__":
    main()
