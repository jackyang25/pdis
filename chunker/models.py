from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


class LLMClientProtocol(Protocol):
    """Contract chunker requires from any injected LLM client.

    Library code depends only on this Protocol — the concrete client
    (Anthropic, OpenAI, mock, anything) is passed in by the caller.
    """
    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        ...


@dataclass
class PipelineResult:
    """Per-document result of run_pipeline_batch / map_blocks_batch.

    `blocks` may be populated even when `mapping_error` is set (parse
    succeeded but the mapper failed). When `parse_error` is set, `blocks`
    is empty.
    """
    file_path: str
    doc_id: str
    blocks: list["ContentBlock"] = field(default_factory=list)
    parse_error: str | None = None
    mapping_error: str | None = None


@dataclass
class ContentBlock:
    # --- Set by Phase 1 (parser) ---
    id: str
    doc_id: str
    ordinal: int
    source_type: str
    content: str
    heading_stack: list[str]
    structural_meta: dict[str, Any]
    style_hint: dict[str, Any]

    # --- Reserved for Phase 2 (mapper) - always None after parsing ---
    section_label: str | None = None
    label_confidence: str | None = None


@dataclass
class DocumentTypeConfig:
    type_key: str
    display_name: str
    section_taxonomy: list[dict[str, str]]
    preamble: str
    disambiguation: list[str]
    include_metadata_label: bool = True
    include_other_label: bool = True


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
    }
    missing_fields = required_fields - data.keys()
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"Config missing required fields: {missing}")

    _validate_section_taxonomy(data["section_taxonomy"])
    _validate_string_field(data, "type_key")
    _validate_string_field(data, "display_name")
    _validate_string_field(data, "preamble")
    _validate_string_list(data["disambiguation"], "disambiguation")
    _validate_bool_field(data, "include_metadata_label")
    _validate_bool_field(data, "include_other_label")

    return DocumentTypeConfig(
        type_key=data["type_key"],
        display_name=data["display_name"],
        section_taxonomy=data["section_taxonomy"],
        preamble=data["preamble"],
        disambiguation=data["disambiguation"],
        include_metadata_label=data.get("include_metadata_label", True),
        include_other_label=data.get("include_other_label", True),
    )


def _validate_section_taxonomy(section_taxonomy: list[dict[str, str]]) -> None:
    if not isinstance(section_taxonomy, list):
        raise ValueError("section_taxonomy must be a list")

    for index, section in enumerate(section_taxonomy):
        if not isinstance(section, dict):
            raise ValueError(f"section_taxonomy[{index}] must be a mapping")
        missing_fields = {"name", "description"} - section.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"section_taxonomy[{index}] missing required fields: {missing}"
            )
        _validate_string_field(section, "name", f"section_taxonomy[{index}]")
        _validate_string_field(section, "description", f"section_taxonomy[{index}]")


def _validate_string_field(
    data: dict[str, Any],
    field_name: str,
    context: str = "Config",
) -> None:
    if not isinstance(data[field_name], str):
        raise ValueError(f"{context} field '{field_name}' must be a string")


def _validate_string_list(value: Any, field_name: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{index}] must be a string")


def _validate_bool_field(data: dict[str, Any], field_name: str) -> None:
    if field_name in data and not isinstance(data[field_name], bool):
        raise ValueError(f"Config field '{field_name}' must be a boolean")
