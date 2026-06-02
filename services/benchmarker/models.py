from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from pathlib import Path

from services.chunker import ContentBlock

# Attribute taxonomy is shared domain vocabulary (like shared/indications.yaml),
# not benchmarker-private. It lives in shared/attributes.yaml and is read by
# benchmarker (binds claims to it) and referenced by reviewer (attribute_ref).
# Benchmarker owns the consumption logic below, not the vocabulary.
ATTRIBUTES_FILE = Path(__file__).resolve().parents[2] / "shared" / "attributes.yaml"
CONFIGS_DIR = Path(__file__).resolve().parent / "configs"


def find_config(intervention_class: str) -> "AttributeConfig":
    """Load the evidence config for the given intervention (filename = {intervention}.yaml)."""
    extraction_path = CONFIGS_DIR / f"{intervention_class}.yaml"
    if not ATTRIBUTES_FILE.exists():
        raise LookupError(f"Shared attribute vocabulary missing: {ATTRIBUTES_FILE}")
    if not extraction_path.exists():
        raise LookupError(
            f"No benchmarker extraction config for {intervention_class!r}. "
            f"Expected: {extraction_path}"
        )
    return load_config(intervention_class, str(extraction_path))


class LLMClientProtocol(Protocol):
    """Contract evidence requires from any injected LLM client."""
    def call(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        ...


@dataclass
class BatchResult:
    """Per-document result of run_pipeline_batch."""
    file_path: str
    source_id: str
    blocks: list[ContentBlock] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    error: str | None = None


# --- Controlled vocabularies ---
# These are the canonical enum values the substrate accepts.
# AttributeConfig can further restrict which values are valid for a given config.

CLAIM_TYPES = (
    "performance",
    "feasibility",
    "user_need",
    "workflow",
    "access",
    "market",
    "regulatory",
    "modelled_impact",
    "expert_judgment",
)

SOURCE_KINDS = (
    "paper",
    "trial",
    "regulatory_doc",
    "product_profile",
    "knowledge_graph",
    "real_world_data",
    "model_run",
    "market_report",
    "interview",
    "expert_note",
)

POLARITIES = ("supports", "challenges", "neutral")


@dataclass
class Claim:
    """Primitive-only claim record. Every field is either a concrete fact
    (text, date, identifier) or a constrained enum tag. No evaluative
    judgments (no strength/confidence/tier opinions) and no speculative
    placeholders for unbuilt workflows."""

    # --- Identity (system-set) ---
    id: str
    ordinal: int

    # --- Content ---
    statement: str
    claim_type: str
    polarity: str

    # --- Source / provenance ---
    source_id: str
    source_kind: str
    source_locator: dict[str, Any]
    extracted_at: str
    valid_as_of: str | None = None

    # --- Header (document provenance, stamped by pipeline) ---
    org: str | None = None
    source_type: str | None = None
    intervention_class: str | None = None
    indication: str | None = None

    # --- Binding (output of the binder, scoped to a config attribute) ---
    attribute_ref: str | None = None

    # --- Schema versioning ---
    claim_schema_version: str = "v1"

    # --- Producer provenance (forward-compat for autonomous ingestion) ---
    source_url: str | None = None
    extractor_version: str | None = None
    model_id: str | None = None
    prompt_hash: str | None = None


@dataclass
class AttributeDef:
    name: str
    description: str
    parent: str | None = None
    expected_claim_types: list[str] = field(default_factory=list)


@dataclass
class AttributeConfig:
    """Evidence attribute namespace. Keyed by `intervention_class` only —
    the attribute set describes a product class, not a document format."""

    type_key: str
    intervention_class: str
    display_name: str
    attributes: list[AttributeDef]
    claim_types: list[str]
    preamble: str
    disambiguation: list[str] = field(default_factory=list)


# --- Serialization helpers ---


def claims_to_dicts(claims: list[Claim]) -> list[dict]:
    """Convert Claim objects to plain dictionaries."""
    return [asdict(claim) for claim in claims]


def config_to_dict(config: AttributeConfig) -> dict:
    """Convert an AttributeConfig to a plain dictionary."""
    return asdict(config)


# --- YAML loading ---


def load_config(intervention_class: str, extraction_path: str) -> AttributeConfig:
    """Load an AttributeConfig from shared vocabulary + benchmarker config."""
    import yaml

    with open(ATTRIBUTES_FILE, "r", encoding="utf-8") as vocab_file:
        vocab_data = yaml.safe_load(vocab_file)
    with open(extraction_path, "r", encoding="utf-8") as extraction_file:
        extraction_data = yaml.safe_load(extraction_file)

    if not isinstance(vocab_data, dict):
        raise ValueError("Attribute vocabulary file must contain a YAML mapping")
    if not isinstance(extraction_data, dict):
        raise ValueError("Benchmarker extraction config must contain a YAML mapping")

    if intervention_class not in vocab_data:
        raise ValueError(
            f"Shared attribute vocabulary missing intervention_class {intervention_class!r}"
        )
    vocab_attributes = vocab_data[intervention_class]

    extraction_required_fields = {
        "type_key",
        "intervention_class",
        "display_name",
        "claim_types",
        "preamble",
    }
    missing_extraction_fields = extraction_required_fields - extraction_data.keys()
    if missing_extraction_fields:
        missing = ", ".join(sorted(missing_extraction_fields))
        raise ValueError(f"Benchmarker extraction config missing required fields: {missing}")

    _validate_string_field(extraction_data, "type_key")
    _validate_string_field(extraction_data, "intervention_class")
    _validate_string_field(extraction_data, "display_name")
    _validate_string_field(extraction_data, "preamble")
    _validate_string_list(extraction_data["claim_types"], "claim_types")
    _validate_string_list(
        extraction_data.get("disambiguation", []),
        "disambiguation",
    )
    _validate_claim_types(extraction_data["claim_types"])

    if intervention_class != extraction_data["intervention_class"]:
        raise ValueError(
            f"Requested intervention_class '{intervention_class}' does not match "
            f"extraction config '{extraction_data['intervention_class']}'"
        )

    attribute_extraction = extraction_data.get("attribute_extraction", []) or []
    expected_by_ref = _expected_claim_types_by_ref(
        attribute_extraction,
        vocab_attributes,
        extraction_data["claim_types"],
    )
    joined_attributes = [
        {
            "name": attr["name"],
            "description": attr["description"],
            "expected_claim_types": expected_by_ref.get(attr["name"], []),
        }
        for attr in vocab_attributes
    ]
    _validate_attributes(joined_attributes, extraction_data["claim_types"])

    attributes = [
        AttributeDef(
            name=attr["name"],
            description=attr["description"],
            expected_claim_types=attr["expected_claim_types"],
        )
        for attr in joined_attributes
    ]

    return AttributeConfig(
        type_key=extraction_data["type_key"],
        intervention_class=extraction_data["intervention_class"],
        display_name=extraction_data["display_name"],
        attributes=attributes,
        claim_types=extraction_data["claim_types"],
        preamble=extraction_data["preamble"],
        disambiguation=extraction_data.get("disambiguation", []),
    )


# --- Validation ---


def validate_claim(claim: Claim, config: AttributeConfig | None = None) -> None:
    """Validate a Claim against the canonical vocabularies and (optionally) a config.

    Raises ValueError on any violation. Mirrors the discipline the substrate
    enforces at insert time.
    """
    _require(claim.id, "id")
    _require(claim.statement, "statement")
    _require(claim.source_id, "source_id")
    _require(claim.extracted_at, "extracted_at")

    if claim.claim_type not in CLAIM_TYPES:
        raise ValueError(f"Invalid claim_type: {claim.claim_type}")
    if claim.source_kind not in SOURCE_KINDS:
        raise ValueError(f"Invalid source_kind: {claim.source_kind}")
    if claim.polarity not in POLARITIES:
        raise ValueError(f"Invalid polarity: {claim.polarity}")
    if not isinstance(claim.source_locator, dict) or not claim.source_locator:
        raise ValueError("source_locator must be a non-empty dict")

    if config is not None:
        attribute_names = {a.name for a in config.attributes}
        if claim.attribute_ref is not None and claim.attribute_ref not in attribute_names:
            raise ValueError(
                f"attribute_ref '{claim.attribute_ref}' not in config "
                f"'{config.type_key}'"
            )
        if claim.intervention_class is not None and claim.intervention_class != config.intervention_class:
            raise ValueError(
                f"intervention_class '{claim.intervention_class}' does not match config "
                f"'{config.type_key}' (expected '{config.intervention_class}')"
            )
        if claim.claim_type not in config.claim_types:
            raise ValueError(
                f"claim_type '{claim.claim_type}' not in config "
                f"'{config.type_key}'"
            )


# --- Internal validators ---


def _require(value: Any, name: str) -> None:
    if value is None or value == "":
        raise ValueError(f"Field '{name}' is required")


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


def _validate_claim_types(claim_types: list[str]) -> None:
    for ct in claim_types:
        if ct not in CLAIM_TYPES:
            raise ValueError(
                f"claim_type '{ct}' is not a canonical claim_type. "
                f"Valid values: {CLAIM_TYPES}"
            )


def _expected_claim_types_by_ref(
    attribute_extraction: Any,
    vocab_attributes: Any,
    config_claim_types: list[str],
) -> dict[str, list[str]]:
    if not isinstance(attribute_extraction, list):
        raise ValueError("attribute_extraction must be a list")
    if not isinstance(vocab_attributes, list):
        raise ValueError("attributes must be a list")

    vocab_names = set()
    for index, attr in enumerate(vocab_attributes):
        if not isinstance(attr, dict):
            raise ValueError(f"attributes[{index}] must be a mapping")
        missing = {"name", "description"} - attr.keys()
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"attributes[{index}] missing required fields: {joined}")
        _validate_string_field(attr, "name", f"attributes[{index}]")
        _validate_string_field(attr, "description", f"attributes[{index}]")
        vocab_names.add(attr["name"])

    out: dict[str, list[str]] = {}
    for index, entry in enumerate(attribute_extraction):
        if not isinstance(entry, dict):
            raise ValueError(f"attribute_extraction[{index}] must be a mapping")
        missing = {"ref", "expected_claim_types"} - entry.keys()
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(
                f"attribute_extraction[{index}] missing required fields: {joined}"
            )
        _validate_string_field(entry, "ref", f"attribute_extraction[{index}]")
        ref = entry["ref"]
        if ref not in vocab_names:
            raise ValueError(
                f"attribute_extraction[{index}].ref '{ref}' not in shared vocabulary"
            )
        if ref in out:
            raise ValueError(f"Duplicate attribute_extraction ref: {ref}")
        _validate_string_list(
            entry["expected_claim_types"],
            f"attribute_extraction[{index}].expected_claim_types",
        )
        for claim_type in entry["expected_claim_types"]:
            if claim_type not in config_claim_types:
                raise ValueError(
                    f"attribute_extraction[{index}].expected_claim_types contains "
                    f"'{claim_type}' which is not declared in this config's claim_types"
                )
        out[ref] = entry["expected_claim_types"]
    return out


def _validate_attributes(attributes: Any, config_claim_types: list[str]) -> None:
    if not isinstance(attributes, list):
        raise ValueError("attributes must be a list")

    for index, attr in enumerate(attributes):
        if not isinstance(attr, dict):
            raise ValueError(f"attributes[{index}] must be a mapping")
        missing = {"name", "description"} - attr.keys()
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"attributes[{index}] missing required fields: {joined}")
        _validate_string_field(attr, "name", f"attributes[{index}]")
        _validate_string_field(attr, "description", f"attributes[{index}]")
        if "parent" in attr and attr["parent"] is not None and not isinstance(attr["parent"], str):
            raise ValueError(f"attributes[{index}].parent must be a string or null")
        if "expected_claim_types" in attr:
            _validate_string_list(
                attr["expected_claim_types"],
                f"attributes[{index}].expected_claim_types",
            )
            for ct in attr["expected_claim_types"]:
                if ct not in config_claim_types:
                    raise ValueError(
                        f"attributes[{index}].expected_claim_types contains "
                        f"'{ct}' which is not declared in this config's claim_types"
                    )
