from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class ContentBlock:
    # --- Set by Phase 1 (parser) ---
    id: str
    doc_id: str
    ordinal: int
    source_type: str
    content: str
    heading_stack: list[str]
    structural_meta: dict
    style_hint: dict

    # --- Reserved for Phase 2 (mapper) - always None after parsing ---
    section_label: str | None = None
    label_confidence: str | None = None


@dataclass
class DocumentTypeConfig:
    type_key: str
    display_name: str
    section_taxonomy: list[str]
    preamble: str
    disambiguation: list[str]
    allow_other: bool


def blocks_to_dicts(blocks: list[ContentBlock]) -> list[dict]:
    """Convert ContentBlock objects to plain dictionaries."""
    return [asdict(block) for block in blocks]


def load_config(config_path: str) -> DocumentTypeConfig:
    """Load a DocumentTypeConfig from a YAML file."""
    import yaml

    with open(config_path, "r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping")

    required_fields = {
        "type_key",
        "display_name",
        "section_taxonomy",
        "preamble",
        "disambiguation",
        "allow_other",
    }
    missing_fields = required_fields - data.keys()
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"Config missing required fields: {missing}")

    return DocumentTypeConfig(
        type_key=data["type_key"],
        display_name=data["display_name"],
        section_taxonomy=data["section_taxonomy"],
        preamble=data["preamble"],
        disambiguation=data["disambiguation"],
        allow_other=data["allow_other"],
    )
