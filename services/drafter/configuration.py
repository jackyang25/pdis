"""Loading and checking Drafter's configuration.

A config names the sources a product type reads and the guidance for planning its searches.
`load_config` refuses anything the run could not honour - a product type with no shared
variables, or a source Searcher does not register - because each would surface later as a
silent gap.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from services.searcher import validate_source_keys
from shared.vocabulary import attribute_definitions

from .models import CONFIGS_DIR, DrafterConfig

SOURCE_TYPE = "itpp"


def load_config(config_path: str) -> DrafterConfig:
    path = Path(config_path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: a config is a mapping")
    org = _text(data, "org", path)
    source_type = _text(data, "source_type", path)
    intervention_class = _text(data, "intervention_class", path)
    if source_type != SOURCE_TYPE:
        raise ValueError(f"{path.name}: Drafter drafts iTPPs; source_type must be {SOURCE_TYPE!r}")
    if not attribute_definitions(intervention_class):
        raise ValueError(f"{path.name}: no shared variables for {intervention_class!r}")
    try:
        sources = validate_source_keys(data.get("sources") or ())
    except ValueError as exc:
        raise ValueError(f"{path.name}: {exc}") from exc
    if not sources:
        raise ValueError(f"{path.name}: at least one source is required")
    return DrafterConfig(
        type_key=_text(data, "type_key", path),
        org=org,
        source_type=source_type,
        intervention_class=intervention_class,
        display_name=_text(data, "display_name", path),
        sources=tuple(sources),
        query_guidance=_text(data, "query_guidance", path),
    )


def available_configs() -> list[DrafterConfig]:
    """Every product type Drafter can draft for, in stable order.

    Decided by whether a file loads as a config, not by the shape of its name, as
    Scout's and Inspector's are.
    """
    configs: list[DrafterConfig] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            config = load_config(str(path))
        except (ValueError, KeyError, TypeError):
            continue
        if config.type_key == path.stem:
            configs.append(config)
    return configs


def find_config(org: str, source_type: str, intervention_class: str) -> DrafterConfig:
    """The config for one product type, or LookupError when there is none."""
    expected = (org, source_type, intervention_class)
    path = CONFIGS_DIR / f"{'_'.join(expected)}.yaml"
    if not path.exists():
        raise LookupError(f"No Drafter config for ({org}, {source_type}, {intervention_class}).")
    config = load_config(str(path))
    actual = (config.org, config.source_type, config.intervention_class)
    if actual != expected or config.type_key != "_".join(expected):
        raise LookupError(f"Drafter config identity mismatch: requested {expected}, file declares {actual}")
    return config


def has_config(org: str, source_type: str, intervention_class: str) -> bool:
    try:
        find_config(org, source_type, intervention_class)
    except LookupError:
        return False
    return True


def _text(data: dict, key: str, path: Path) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ValueError(f"{path.name}: {key} is required")
    return value
