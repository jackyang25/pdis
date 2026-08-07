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
from services.chunker import available_configs as chunker_configs
from services.chunker.prompt_catalog import PROMPT_CATALOG as CHUNKER_CATALOG
from services.expert.prompt_catalog import PROMPT_CATALOG as EXPERT_CATALOG
from services.inspector.prompt_catalog import PROMPT_CATALOG as INSPECTOR_CATALOG
from services.inspector import available_configs as inspector_configs
from services.scout import available_configs as scout_configs
from services.scout.prompt_catalog import PROMPT_CATALOG as SCOUT_CATALOG

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "shared" / "prompt_reference.json"

VERSION = 3

# Publication order, matching the order a document moves through the suite.
CATALOGS = (
    CHUNKER_CATALOG,
    INSPECTOR_CATALOG,
    ALIGNER_CATALOG,
    SCOUT_CATALOG,
    EXPERT_CATALOG,
)

# Where each tool's configurations come from.
#
# Aligner is deliberately absent: its `document_roles` slot is a mapping keyed by
# source type rather than one text, and the package exposes no config enumerator to
# read it from. `test_prompt_reference` names that gap explicitly, so registering
# Aligner later is a change the test asks for rather than one nobody notices.
#
# Expert is absent for a different reason and permanently: its prompt has no framing
# slot at all. The question bank supplies each question's whole text, so there is no
# configuration field interpolated into the prompt for a reader to be shown.
CONFIG_SOURCES = {
    "chunker": chunker_configs,
    "inspector": inspector_configs,
    "scout": scout_configs,
}

# Provenance a configuration may declare: the authored source its structure comes
# from. Optional, because not every configuration mirrors one.
PROVENANCE_FIELD = "mirrors"


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

    # Which text a prompt inserts at run time is declared by the catalog entry that
    # inserts it, so the slots are read from there rather than listed again here. A
    # declared slot that publishes nothing was previously possible - and Inspector's
    # went unpublished for exactly that reason.
    slots_by_tool: dict[str, list[str]] = {}
    for catalog in CATALOGS:
        for entry in catalog:
            if not entry.framing_slot:
                continue
            slots = slots_by_tool.setdefault(entry.tool, [])
            if entry.framing_slot not in slots:
                slots.append(entry.framing_slot)

    configurations = []
    # Which files are configurations is each service's own fact, asked for rather
    # than inferred from the shape of a filename.
    for tool, load in CONFIG_SOURCES.items():
        for config in load():
            texts = {
                slot: text
                for slot in slots_by_tool.get(tool, ())
                if (text := (getattr(config, slot, "") or "").strip())
            }
            mirrors = (getattr(config, PROVENANCE_FIELD, "") or "").strip()
            if not texts and not mirrors:
                continue
            configurations.append(
                {
                    "tool": tool,
                    "org": config.org,
                    "source_type": config.source_type,
                    "intervention_class": config.intervention_class,
                    "display_name": getattr(config, "display_name", "") or "",
                    "mirrors": mirrors,
                    "texts": texts,
                }
            )
    configurations.sort(
        key=lambda item: (
            item["tool"],
            item["org"],
            item["source_type"],
            item["intervention_class"],
        )
    )

    return {"version": VERSION, "prompts": prompts, "configurations": configurations}


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
        f"{len(reference['configurations'])} configurations"
    )


if __name__ == "__main__":
    main()
