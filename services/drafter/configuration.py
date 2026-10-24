"""Loading and checking Drafter's configuration.

A config names the sources a product type reads and the guidance for planning its searches.
`load_config` refuses anything the run could not honour - a product type with no shared
variables, a source Searcher does not register, or a source whose excerpts are not the
source's own words - because each would surface later as a silent gap or an unquotable
reading. A config that does not load is a broken product type, never one to skip.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from services.searcher import source_specs, validate_source_keys
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
    verbatim = {spec.key for spec in source_specs() if spec.excerpt_is_verbatim}
    snippets = [key for key in sources if key not in verbatim]
    if snippets:
        raise ValueError(
            f"{path.name}: {', '.join(snippets)} returns snippets rather than the source's own words, "
            "which can support neither a quotation nor a number"
        )
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

    Every file in the directory is a config and must load: a malformed one raises, as
    Screener's and Inspector's do, rather than quietly removing a product type.
    """
    configs: list[DrafterConfig] = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        config = load_config(str(path))
        if config.type_key != path.stem:
            raise ValueError(f"{path.name}: type_key {config.type_key!r} must match its filename")
        identity = (config.org, config.source_type, config.intervention_class)
        if identity in seen:
            raise ValueError(f"{path.name}: a second config for {identity}")
        seen.add(identity)
        configs.append(config)
    return configs


def find_config(org: str, source_type: str, intervention_class: str) -> DrafterConfig:
    """The config declaring this triple, or LookupError when there is none.

    Found by what each config declares, never by building a filename from the keys.
    """
    expected = (org, source_type, intervention_class)
    for config in available_configs():
        if (config.org, config.source_type, config.intervention_class) == expected:
            return config
    raise LookupError(f"No Drafter config for ({org}, {source_type}, {intervention_class}).")


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
