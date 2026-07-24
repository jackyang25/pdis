from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..models import (
    AlignmentConfig,
    AlignmentLink,
    AlignmentStats,
    AlignmentUnit,
    LLMClientProtocol,
)

logger = logging.getLogger(__name__)
LLM_RELATIONS = {"aligned", "modified", "conflict", "missing"}


def align_units(
    reference_units: list[AlignmentUnit],
    comparison_units: list[AlignmentUnit],
    *,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> tuple[list[AlignmentLink], AlignmentStats]:
    if not reference_units:
        links = [_introduced_link(unit) for unit in comparison_units]
        return links, _stats(reference_units, comparison_units, links)
    if not comparison_units:
        links = [_missing_link(unit) for unit in reference_units]
        return links, _stats(reference_units, comparison_units, links)

    reference_batches = [
        reference_units[index : index + config.alignment_batch_units]
        for index in range(0, len(reference_units), config.alignment_batch_units)
    ]
    comparison_batches = [
        comparison_units[index : index + config.alignment_comparison_batch_units]
        for index in range(0, len(comparison_units), config.alignment_comparison_batch_units)
    ]

    def run(pair: tuple[int, list[AlignmentUnit], list[AlignmentUnit]]):
        batch_index, reference_batch, comparison_batch = pair
        return _align_batch(
            reference_batch,
            comparison_batch,
            config=config,
            llm_client=llm_client,
            max_tokens=max_tokens,
        ), batch_index

    # Scan every bounded reference/comparison batch pair. This preserves full
    # pair coverage without placing an arbitrarily large comparison document in
    # one prompt. Each scan returns at most one candidate set per reference.
    pairs = [
        (batch_index, reference_batch, comparison_batch)
        for batch_index, reference_batch in enumerate(reference_batches)
        for comparison_batch in comparison_batches
    ]
    workers = max(1, min(config.max_parallel_calls, len(pairs)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        scans = list(executor.map(run, pairs))

    candidates_by_batch: dict[int, set[str]] = {
        index: set() for index in range(len(reference_batches))
    }
    for scan_links, batch_index in scans:
        candidates_by_batch[batch_index].update(
            comparison_id
            for link in scan_links
            if link.relation != "missing"
            for comparison_id in link.comparison_unit_ids
        )

    comparison_by_id = {unit.id: unit for unit in comparison_units}
    links: list[AlignmentLink] = []
    for batch_index, reference_batch in enumerate(reference_batches):
        candidate_units = [
            comparison_by_id[unit_id]
            for unit_id in comparison_by_id
            if unit_id in candidates_by_batch[batch_index]
        ]
        if not candidate_units:
            links.extend(_missing_link(unit) for unit in reference_batch)
            continue
        # Reconcile candidates from all comparison batches into one final link
        # per reference unit. Candidate count grows by matches, not document size.
        links.extend(
            _align_batch(
                reference_batch,
                candidate_units,
                config=config,
                llm_client=llm_client,
                max_tokens=max_tokens,
            )
        )

    matched_comparison_ids = {
        unit_id for link in links for unit_id in link.comparison_unit_ids
    }
    links.extend(
        _introduced_link(unit)
        for unit in comparison_units
        if unit.id not in matched_comparison_ids
    )
    return links, _stats(reference_units, comparison_units, links)


def _align_batch(
    reference_units: list[AlignmentUnit],
    comparison_units: list[AlignmentUnit],
    *,
    config: AlignmentConfig,
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> list[AlignmentLink]:
    relation_text = "\n".join(
        f'- "{item.name}": {item.description}'
        for item in config.relations
        if item.name != "introduced"
    )
    system_prompt = f"""You compare explicit units from two product-development documents to build a traceability matrix.

For every REFERENCE unit, choose exactly one relation:
{relation_text}

Rules:
- Use aligned only when the substance is preserved, even if wording differs.
- Use modified for a carried-forward topic whose scope, numeric value, timing, population, ownership, or implementation changed.
- Use conflict only for statements that cannot both hold as written; difference alone is not conflict.
- Use missing when no comparison unit is a substantive counterpart.
- Cite comparison IDs only from the supplied list. A relation may cite multiple comparison units when one reference commitment was split.
- Do not create introduced links; the system derives them deterministically from unused comparison units.
- Return every supplied reference ID exactly once.

Return ONLY valid JSON:
{{"links":[{{"reference_unit_id":"unit_...","comparison_unit_ids":["unit_..."],"relation":"aligned|modified|conflict|missing","reason":"one concise document-grounded explanation"}}]}}
"""
    user_message = (
        "REFERENCE units:\n"
        + _format_units(reference_units)
        + "\n\nCOMPARISON units:\n"
        + _format_units(comparison_units)
    )
    ref_by_id = {unit.id: unit for unit in reference_units}
    comp_by_id = {unit.id: unit for unit in comparison_units}
    selected: dict[str, AlignmentLink] | None = None
    for attempt in range(2):
        raw = llm_client.call(
            system_prompt,
            user_message
            + (
                "\n\nThe previous response was invalid. Return only the requested JSON object."
                if attempt
                else ""
            ),
            max_tokens=max_tokens,
        )
        try:
            parsed = json.loads(_extract_json_object(raw))
            values = parsed.get("links")
            if not isinstance(values, list):
                raise ValueError("links must be a list")
            candidate = _validate_batch_links(values, ref_by_id, comp_by_id)
            if attempt == 0 and set(candidate) != set(ref_by_id):
                raise ValueError("Alignment response omitted one or more reference units")
            selected = candidate
            break
        except (ValueError, json.JSONDecodeError, AttributeError) as exc:
            if attempt:
                logger.error("Aligner linking returned invalid JSON after retry: %s", exc)
    if selected is None:
        raise RuntimeError("Aligner linking failed after retry")
    return [selected.get(unit.id, _missing_link(unit)) for unit in reference_units]


def _validate_batch_links(
    values: list[Any],
    ref_by_id: dict[str, AlignmentUnit],
    comp_by_id: dict[str, AlignmentUnit],
) -> dict[str, AlignmentLink]:
    selected: dict[str, AlignmentLink] = {}
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("Every alignment link must be an object")
        reference_id = item.get("reference_unit_id")
        relation = item.get("relation")
        if reference_id not in ref_by_id or reference_id in selected:
            raise ValueError("Alignment response contains an unknown or duplicate reference ID")
        if relation not in LLM_RELATIONS:
            raise ValueError("Alignment response contains an unknown relation")
        raw_comparison_ids = item.get("comparison_unit_ids")
        if not isinstance(raw_comparison_ids, list) or any(
            not isinstance(unit_id, str) or unit_id not in comp_by_id
            for unit_id in raw_comparison_ids
        ):
            raise ValueError("Alignment response contains an unknown comparison ID")
        comparison_ids = list(dict.fromkeys(raw_comparison_ids))
        if len(comparison_ids) != len(raw_comparison_ids):
            raise ValueError("Alignment response contains duplicate comparison IDs")
        if relation == "missing" and comparison_ids:
            raise ValueError("Missing links cannot cite comparison units")
        if relation != "missing" and not comparison_ids:
            raise ValueError("Mapped links must cite at least one comparison unit")
        reason = _clean_reason(item.get("reason"))
        if not reason:
            raise ValueError("Every alignment link requires a document-grounded reason")
        selected[reference_id] = _link(
            relation=relation,
            reference_units=[ref_by_id[reference_id]],
            comparison_units=[comp_by_id[unit_id] for unit_id in comparison_ids],
            reason=reason,
        )
    return selected


def _format_units(units: list[AlignmentUnit]) -> str:
    return "\n".join(
        f'[{unit.id}] type={unit.unit_type} blocks={",".join(unit.block_ids)}\n{unit.statement}'
        for unit in units
    )


def _link(
    *,
    relation: str,
    reference_units: list[AlignmentUnit],
    comparison_units: list[AlignmentUnit],
    reason: str,
) -> AlignmentLink:
    reference_ids = [unit.id for unit in reference_units]
    comparison_ids = [unit.id for unit in comparison_units]
    payload = "\0".join([relation, *reference_ids, *comparison_ids])
    return AlignmentLink(
        id=f"link_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}",
        relation=relation,  # type: ignore[arg-type]
        reference_unit_ids=reference_ids,
        comparison_unit_ids=comparison_ids,
        reason=reason,
        reference_block_ids=_unit_block_ids(reference_units),
        comparison_block_ids=_unit_block_ids(comparison_units),
    )


def _missing_link(unit: AlignmentUnit) -> AlignmentLink:
    return _link(
        relation="missing",
        reference_units=[unit],
        comparison_units=[],
        reason="No substantive counterpart was identified in the comparison document.",
    )


def _introduced_link(unit: AlignmentUnit) -> AlignmentLink:
    return _link(
        relation="introduced",
        reference_units=[],
        comparison_units=[unit],
        reason="This unit has no linked antecedent in the reference document.",
    )


def _stats(
    reference_units: list[AlignmentUnit],
    comparison_units: list[AlignmentUnit],
    links: list[AlignmentLink],
) -> AlignmentStats:
    counts = {name: 0 for name in ("aligned", "modified", "conflict", "missing", "introduced")}
    for link in links:
        counts[link.relation] += 1
    return AlignmentStats(
        reference_units=len(reference_units),
        comparison_units=len(comparison_units),
        aligned=counts["aligned"],
        modified=counts["modified"],
        conflict=counts["conflict"],
        missing=counts["missing"],
        introduced=counts["introduced"],
    )


def _unit_block_ids(units: list[AlignmentUnit]) -> list[str]:
    return list(dict.fromkeys(block_id for unit in units for block_id in unit.block_ids))


def _clean_reason(value: Any) -> str:
    return " ".join(value.split()).strip() if isinstance(value, str) else ""


def _extract_json_object(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    decoder = json.JSONDecoder()
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return text[start : start + end]
    raise ValueError("response did not contain a JSON object")
