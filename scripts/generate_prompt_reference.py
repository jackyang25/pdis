"""Generate the published prompt reference from every tool's prompt catalog.

The catalogs and the stage builders are the authority. This script only renders
them into a file the documentation page and Assistant can read, because the web
layer cannot import a service. Run it after changing any prompt; a test asserts
the committed file matches this output.

    .venv/bin/python scripts/generate_prompt_reference.py
"""

from __future__ import annotations

import json
from pathlib import Path

from services.aligner.prompt_catalog import PROMPT_CATALOG as ALIGNER_CATALOG
from services.chunker.prompt_catalog import PROMPT_CATALOG as CHUNKER_CATALOG
from services.inspector.prompt_catalog import PROMPT_CATALOG as INSPECTOR_CATALOG
from services.scout import available_configs as scout_configs
from services.scout.prompt_catalog import PROMPT_CATALOG as SCOUT_CATALOG

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "shared" / "prompt_reference.json"

VERSION = 2

# Publication order, matching the order a document moves through the suite.
CATALOGS = (
    CHUNKER_CATALOG,
    INSPECTOR_CATALOG,
    ALIGNER_CATALOG,
    SCOUT_CATALOG,
)

# Per-configuration domain content a prompt inserts at run time. Listed once here
# rather than inlined into every prompt that carries the slot. Only Scout varies
# its instructions by configuration today.
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
            "tool": entry.tool,
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
        for catalog in CATALOGS
        for entry in catalog
    ]

    framings = []
    # Which files are configs is Scout's fact, asked for rather than inferred
    # from the shape of a filename.
    for config in scout_configs():
        for key in CONFIG_TEXT_FIELDS:
            text = (getattr(config, key, "") or "").strip()
            if not text:
                continue
            framings.append(
                {
                    "tool": "scout",
                    "key": key,
                    "org": config.org,
                    "source_type": config.source_type,
                    "intervention_class": config.intervention_class,
                    "text": text,
                }
            )
    framings.sort(
        key=lambda item: (
            item["tool"],
            item["org"],
            item["source_type"],
            item["intervention_class"],
            item["key"],
        )
    )

    return {"version": VERSION, "prompts": prompts, "framings": framings}


def main() -> None:
    reference = build_reference()
    REFERENCE.write_text(json.dumps(reference, indent=2, sort_keys=True) + "\n")
    by_tool: dict[str, int] = {}
    for prompt in reference["prompts"]:
        by_tool[prompt["tool"]] = by_tool.get(prompt["tool"], 0) + 1
    summary = ", ".join(f"{tool} {count}" for tool, count in by_tool.items())
    print(
        f"wrote {REFERENCE.relative_to(ROOT)}: "
        f"{len(reference['prompts'])} prompts ({summary}), "
        f"{len(reference['framings'])} configuration texts"
    )


if __name__ == "__main__":
    main()
