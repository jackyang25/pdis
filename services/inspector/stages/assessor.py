"""Ask one question per rubric unit, and read findings off the answer.

One schema-bound call per unit: "what is wrong with this, and why". That replaced
three calls per unit, one for completeness, adherence, and rigor. Three calls cost
three times the requests for a 26-unit rubric and could each report the same defect
under its own axis, so a funding disclaimer sitting where an introduction belongs
was simultaneously incomplete, off-template, and weak.

Merging them also removed the naming problem that split created: the same axis was
`adherence` in the data and "Template adherence" in two interfaces, while
completeness escaped it only because its key happened to read well.

Sections run in parallel, and the unit calls within a section also run in parallel,
so wall-clock stays close to the slowest single call.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import replace
from typing import Any

from shared.ai import request_structured
from shared.batching import map_ordered

from services.chunker import ContentBlock

from ..assembly import absent_unit_findings, finding_id
from ..models import (
    UNCITED_REASON,
    UNIT_REASONS,
    ConsistencyStatus,
    Finding,
    InspectionConfig,
    LLMClientProtocol,
    SectionSpec,
    VariableSpec,
)

MAX_PARALLEL_SECTIONS = 4
# One assessment per rubric unit, so an unrelated unit can never sit in this
# decision's prompt. Throughput comes from fan-out, never from packing units.
UNITS_PER_REQUEST = 1
MAX_PARALLEL_UNIT_CALLS = 6

# What each reason is for, stated once and rendered into the prompt. Adding a
# reason means adding it here and to `FINDING_REASONS`; nothing between this module
# and the interface needs to know.
_REASON_GUIDANCE: tuple[tuple[str, str], ...] = (
    ("missing", "there is no content at all for this unit."),
    ("placeholder", "a template token such as <<TBD>>, TBD, a dash, or a blank sits where the value belongs."),
    ("unmet", "content is present and does not satisfy the requirement, for example only one of Minimum/Optimistic is filled, or a category label stands in for a value."),
    ("off_template", "the content is there but does not follow the rubric's expected structure or naming, or a template token remains beside real content."),
    ("unclear", "the requirement is satisfied but the content is vague, unmeasurable, or internally incoherent."),
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def assess_document(
    labeled_blocks: list[ContentBlock],
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
    progress=None,
) -> tuple[list[Finding], dict[str, list[str]]]:
    """Assess every rubric unit.

    Returns the findings and the blocks mapped to each section. Presence is not
    returned separately: a section is present exactly when the mapper gave it
    blocks, so the mapping already says so. Parse lineage travels beside the
    findings rather than inside them, because it is an assignment the mapper made
    rather than something any judgment cited.
    """
    blocks_by_section = _group_blocks_by_section(labeled_blocks)
    indexed = [
        (index, spec, blocks_by_section.get(spec.name) or None)
        for index, spec in enumerate(config.sections)
    ]

    total = len(indexed)
    if progress:
        progress("assess", completed=0, total=total)
    lock = threading.Lock()
    done = {"n": 0}

    def assess_one(item):
        index, section_spec, section_blocks = item
        if not section_blocks:
            out = (index, absent_unit_findings(config, section_spec.name), [])
        else:
            out = (
                index,
                _assess_section(
                    section_spec=section_spec,
                    section_blocks=section_blocks,
                    llm_client=llm_client,
                    max_tokens=max_tokens,
                    stage_guidance=config.stage_guidance,
                ),
                [block.id for block in section_blocks],
            )
        if progress:
            with lock:
                done["n"] += 1
                progress("assess", completed=done["n"], total=total)
        return out

    assessed = map_ordered(indexed, assess_one, workers=MAX_PARALLEL_SECTIONS)

    findings = [f for _, section_findings, _ in assessed for f in section_findings]
    mapped = {config.sections[i].name: block_ids for i, _, block_ids in assessed}
    return findings, mapped


# ---------------------------------------------------------------------------
# Per-section assessment: one parallel call per unit
# ---------------------------------------------------------------------------


def _assess_section(
    *,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
    stage_guidance: str = "",
) -> list[Finding]:
    blocks_text = _format_blocks(section_blocks)
    units = section_spec.variables or [None]

    def call_one(unit: VariableSpec | None) -> list[Finding]:
        return _assess_unit(
            section_spec=section_spec,
            unit=unit,
            blocks_text=blocks_text,
            section_blocks=section_blocks,
            llm_client=llm_client,
            max_tokens=max_tokens,
            stage_guidance=stage_guidance,
        )

    batched = map_ordered(units, call_one, workers=MAX_PARALLEL_UNIT_CALLS)
    return [finding for unit_findings in batched for finding in unit_findings]


def _assess_unit(
    *,
    section_spec: SectionSpec,
    unit: VariableSpec | None,
    blocks_text: str,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
    stage_guidance: str = "",
) -> list[Finding]:
    """Build one schema-bound decision for one unit and validate its lineage.

    One call means the answer needs no unit name: this function already knows which
    unit it asked about. The accounting that a three-call shape needed - every
    expected name present exactly once - goes away with it.
    """
    system_prompt = build_assessment_prompt(section_spec, unit, stage_guidance)
    user_message = _build_user_message(section_spec, unit, blocks_text)
    schema = assessment_schema(section_blocks)
    images = _image_inputs(section_blocks)
    unit_name = unit.name if unit else None

    first_error = "model returned no structured decision"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior decision failed the Inspector contract: "
                f"{first_error}. Report at most one finding per reason, and cite the "
                "exact supplied block IDs for every finding except an absent one."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="inspector_unit_assessment",
            schema=schema,
            images=images or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured decision")
            return _parse_unit_payload(
                payload,
                section_name=section_spec.name,
                variable_name=unit_name,
                section_blocks=section_blocks,
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(
        f"Inspector could not assess {unit_name or section_spec.name} "
        f"in {section_spec.name}: {first_error}"
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_assessment_prompt(
    section_spec: SectionSpec,
    unit: VariableSpec | None = None,
    stage_guidance: str = "",
) -> str:
    reasons = "\n".join(f"- {reason}: {text}" for reason, text in _REASON_GUIDANCE)
    preamble = f"""You are inspecting one unit of a product-development document against its authored rubric.

Scope boundary:
- Judge the quality and usability of what the document states; do not assess real-world program feasibility or investment merit.
- If the rubric expects risks, judge whether the document identifies, rates, and mitigates them. Do not independently assign program risk levels.
- Do not recommend funding decisions, prioritize an investment portfolio, or propose organizational support.
- Do not assume external facts or evidence that are absent from the supplied document and rubric.

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Report every distinct problem with this unit, at most one per reason, and nothing
when the unit is sound. Do not report the same problem twice under two reasons:
choose the one that names it best.

Reasons:
{reasons}

If the content is absent, report `missing` alone. Absence is not also off-template
or unclear, and there is nothing there to have read.

Lineage is required, not optional. Every finding except `missing` MUST cite in
`block_ids` the exact blocks you read to reach it.

Describe the document; do not direct the reader. State what is or is not there,
not what must be done about it. The recommendation is the one place an action
belongs.

Style:
- `statement` is one short factual sentence (max 20 words) naming the problem.
- `recommendation` is one short action sentence (max 20 words), action-verb-leading.
- Do not repeat the unit's name in either. Do not hedge."""

    parts = [preamble]
    if stage_guidance.strip():
        parts.append("# ASSESSMENT BAR (document stage)\n" + stage_guidance.strip())
    parts.append(_expectations_block(section_spec, unit))
    return "\n\n".join(parts)


def _expectations_block(section_spec: SectionSpec, unit: VariableSpec | None) -> str:
    lines = ["# THE UNIT YOU ARE ASSESSING"]
    if unit is None:
        lines.append(f"The {section_spec.name} section as a whole.")
        lines.append(f"What it should cover: {section_spec.description}")
        if section_spec.expectations:
            lines.append(f"Expectations: {section_spec.expectations}")
        if section_spec.optional:
            lines.append("The rubric accepts this section being absent.")
        return "\n".join(lines)

    lines.append(f"{unit.name}, within the {section_spec.name} section.")
    lines.append(f"What it should contain: {unit.description}")
    expectations = unit.expectations or section_spec.expectations
    if expectations:
        lines.append(f"Expectations: {expectations}")
    if unit.optional or section_spec.optional:
        lines.append("The rubric accepts this unit being absent.")
    return "\n".join(lines)


def assessment_schema(section_blocks: list[ContentBlock]) -> dict[str, Any]:
    """The closed shape one unit's answer must take."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "maxItems": len(UNIT_REASONS),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["reason", "statement", "recommendation", "block_ids"],
                    "properties": {
                        "reason": {"type": "string", "enum": list(UNIT_REASONS)},
                        "statement": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "block_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [block.id for block in section_blocks],
                            },
                        },
                    },
                },
            }
        },
    }


def _build_user_message(
    section_spec: SectionSpec,
    unit: VariableSpec | None,
    blocks_text: str,
) -> str:
    subject = unit.name if unit else section_spec.name
    return "\n\n".join(
        [
            f"Assess: {subject}",
            f"Section: {section_spec.name}",
            "Actual document blocks for this section:",
            blocks_text,
        ]
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_unit_payload(
    parsed: object,
    *,
    section_name: str,
    variable_name: str | None,
    section_blocks: list[ContentBlock],
) -> list[Finding]:
    if not isinstance(parsed, dict):
        raise ValueError("assessment response must be an object")
    raw = parsed.get("findings")
    if not isinstance(raw, list):
        raise ValueError("findings must be a list")

    valid_block_ids = {block.id for block in section_blocks}
    allowed = set(UNIT_REASONS)
    subject = variable_name or section_name

    by_reason: dict[str, Finding] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each finding must be an object")
        reason = _closed_value(item.get("reason"), allowed, "reason")
        if reason in by_reason:
            raise ValueError(f"{subject} raised {reason} twice")
        block_ids = list(dict.fromkeys(_string_list(item.get("block_ids"))))
        if any(block_id not in valid_block_ids for block_id in block_ids):
            raise ValueError(f"{subject} cited an unknown block ID")
        statement = _string_value(item.get("statement"))
        if not statement:
            raise ValueError(f"{subject} reported a finding with no statement")
        # Presence and lineage have to agree, and the rule is the same everywhere:
        # absence cites nothing and everything else cites something.
        if reason == UNCITED_REASON:
            block_ids = []
        elif not block_ids:
            raise ValueError(f"{subject} reported {reason} without citing a block")
        by_reason[reason] = Finding(
            id=finding_id(section_name, variable_name, reason),
            reason=reason,  # type: ignore[arg-type]
            statement=statement,
            recommendation=_string_value(item.get("recommendation")),
            section_name=section_name,
            variable_name=variable_name,
            cited_block_ids=block_ids,
        )

    if UNCITED_REASON in by_reason and len(by_reason) > 1:
        # Absence gates the rest. Code used to add a second finding of its own
        # here, so every absent unit was counted twice before the model spoke.
        return [by_reason[UNCITED_REASON]]
    return [by_reason[reason] for reason in UNIT_REASONS if reason in by_reason]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _group_blocks_by_section(blocks: list[ContentBlock]) -> dict[str, list[ContentBlock]]:
    blocks_by_section: dict[str, list[ContentBlock]] = defaultdict(list)
    for block in blocks:
        if block.section_label:
            blocks_by_section[block.section_label].append(block)
    return dict(blocks_by_section)


def _format_blocks(blocks: list[ContentBlock]) -> str:
    if not blocks:
        return "(none)"
    return "\n\n".join(_format_block(b) for b in blocks)


def _format_block(block: ContentBlock) -> str:
    heading_stack = " > ".join(block.heading_stack) if block.heading_stack else "none"
    return (
        f"[{block.id} | {block.block_type} | headings: {heading_stack}]\n"
        f"{block.content}"
    )


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _closed_value(value: Any, allowed: set[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{label} must use its closed vocabulary")
    return value


# ---------------------------------------------------------------------------
# Cross-section consistency: the one pass that sees ALL sections at once
# ---------------------------------------------------------------------------

# Whole-doc context cap, in lockstep spirit with the other doc-reading stages so a
# long document never silently loses its tail in this pass.
MAX_DOC_CONTEXT_CHARS = 120000


def check_cross_section(
    labeled_blocks: list[ContentBlock],
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> tuple[list[Finding], ConsistencyStatus]:
    """Find consistency problems that span MORE THAN ONE section.

    Per-unit assessment is deliberately isolated, so it cannot catch "Section A
    targets >=80%, Section B says 90%". This pass sees every section together and
    reports conflicts as ordinary findings under the `conflicting` reason - they used
    to be a fourth shape with their own field names for the same concepts. It is an
    additive layer: a parse failure returns a failed status and never masquerades as
    a completed no-conflict result.
    """
    # Scoped to rubric sections, in rubric order. Chunker labels blocks with its own
    # taxonomy, which adds "Document Metadata" and "Other" beyond the rubric, and
    # per-unit assessment ignores those by looking up rubric names. This pass scopes
    # the same way: a finding citing an unmapped block is one the result contract
    # rejects, which would lose a whole assessed document to an additive check.
    labeled_by_section = _group_blocks_by_section(labeled_blocks)
    blocks_by_section = {
        section.name: labeled_by_section[section.name]
        for section in config.sections
        if labeled_by_section.get(section.name)
    }
    if len(blocks_by_section) < 2:
        return [], "not_applicable"  # need two sections for a cross-section conflict

    system_prompt = build_cross_section_prompt(config)
    user_message, context_blocks_by_section, context_limited = _cross_section_user_message(
        blocks_by_section
    )
    context_blocks = [b for blocks in context_blocks_by_section.values() for b in blocks]
    schema = cross_section_schema(context_blocks_by_section)
    images = _image_inputs(context_blocks)

    findings = None
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior response failed the consistency contract. Return only "
                "cross-section conflicts, each citing exact supplied block IDs from at "
                "least two different sections."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name="inspector_cross_section_consistency",
            schema=schema,
            images=images or None,
        )
        findings = _parse_cross_section_payload(payload, context_blocks_by_section)
        if findings is not None:
            break
    if findings is None:
        return [], "failed"
    return findings, "partial" if context_limited else "complete"


def build_cross_section_prompt(config: InspectionConfig) -> str:
    return (
        f"You check a {config.intervention_term} product-development document for CROSS-SECTION "
        "consistency: places where TWO DIFFERENT sections state conflicting or mismatched "
        "claims about the SAME attribute - e.g. one section targets >=80% efficacy and "
        "another states 90%; the target population, dosing schedule, presentation, or "
        "timelines disagree between sections.\n\n"
        "Report ONLY conflicts that span more than one section. Do NOT report problems "
        "inside a single section, missing content, vague wording, or formatting - those are "
        "assessed per unit. If there are no cross-section conflicts, return an empty array.\n\n"
        # The same boundary the per-unit prompt states, in the same words. Without it this
        # pass is the one place Inspector can reach a verdict it has no authority for: the
        # structural gate accepts any finding citing two real blocks in two real sections,
        # so "both of these targets are clinically unrealistic" passes every check while
        # being Scout's judgment made without any evidence behind it.
        "A conflict is the document disagreeing with itself: two sections stating "
        "different values for the same attribute. Do not assess whether a stated value is "
        "correct, achievable, or clinically plausible, and do not assume external facts or "
        "evidence that are absent from the supplied document. Two sections that agree are "
        "not in conflict because you judge the agreed value to be wrong.\n\n"
        "Return only structured findings. Each item contains:\n"
        '{"statement": "the specific conflicting values and what disagrees", '
        '"recommendation": "one short action to reconcile them", '
        '"block_ids": ["exact supporting block ID from each disagreeing section"]}\n\n'
        "Use only supplied block IDs, and cite at least one from each of at least two "
        "different sections - that span is what makes a conflict cross-section. The sections "
        "involved are read back from the blocks you cite, so do not name them separately."
    )


def cross_section_schema(
    blocks_by_section: dict[str, list[ContentBlock]],
) -> dict[str, Any]:
    block_ids = [b.id for blocks in blocks_by_section.values() for b in blocks]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["findings"],
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["statement", "recommendation", "block_ids"],
                    "properties": {
                        "statement": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "block_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": block_ids},
                        },
                    },
                },
            }
        },
    }


def _cross_section_user_message(
    blocks_by_section: dict[str, list[ContentBlock]],
) -> tuple[str, dict[str, list[ContentBlock]], bool]:
    selected, limited = _bounded_cross_section_blocks(blocks_by_section)
    parts: list[str] = ["Document sections and their content:\n"]
    for section_name, blocks in selected.items():
        parts.append(f"=== SECTION: {section_name} ===")
        parts.append(_format_blocks(blocks))
        if len(blocks) < len(blocks_by_section[section_name]):
            parts.append(
                f"[Context limited: {len(blocks)} of {len(blocks_by_section[section_name])} blocks shown]"
            )
        parts.append("")
    return (
        "\n".join(parts) + "\nFind cross-section consistency conflicts now.",
        selected,
        limited,
    )


def _bounded_cross_section_blocks(
    blocks_by_section: dict[str, list[ContentBlock]],
) -> tuple[dict[str, list[ContentBlock]], bool]:
    """Keep every section represented when whole-document context is bounded.

    Full documents are retained when they fit. For unusually large documents, each
    section receives an equal character budget and keeps blocks from both its
    beginning and end; the prompt states when coverage is partial.
    """
    full_size = sum(
        len(_format_block(block)) + 2
        for blocks in blocks_by_section.values()
        for block in blocks
    )
    if full_size <= MAX_DOC_CONTEXT_CHARS:
        return blocks_by_section, False
    per_section = max(1000, MAX_DOC_CONTEXT_CHARS // len(blocks_by_section))
    selected: dict[str, list[ContentBlock]] = {}
    limited = False
    for section_name, blocks in blocks_by_section.items():
        left, right, used = 0, len(blocks) - 1, 0
        chosen: list[ContentBlock] = []
        take_front = True
        while left <= right:
            index = left if take_front else right
            candidate = blocks[index]
            size = len(_format_block(candidate)) + 2
            if not chosen and size > per_section:
                overhead = max(0, size - len(candidate.content or ""))
                content_budget = max(0, per_section - overhead - 32)
                chosen.append(
                    replace(
                        candidate,
                        content=(candidate.content or "")[:content_budget]
                        + "\n...[block excerpt limited]",
                    )
                )
                limited = True
                break
            if chosen and used + size > per_section:
                limited = True
                break
            chosen.append(candidate)
            used += size
            if take_front:
                left += 1
            else:
                right -= 1
            take_front = not take_front
        chosen.sort(key=lambda block: block.ordinal)
        selected[section_name] = chosen
        if len(chosen) < len(blocks):
            limited = True
    return selected, limited


def _parse_cross_section_payload(
    payload: object,
    blocks_by_section: dict[str, list[ContentBlock]],
) -> list[Finding] | None:
    if not isinstance(payload, dict):
        return None
    parsed = payload.get("findings")
    if not isinstance(parsed, list):
        return None
    section_by_block_id = {
        block.id: section_name
        for section_name, blocks in blocks_by_section.items()
        for block in blocks
    }
    out: list[Finding] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            return None
        statement = _string_value(item.get("statement"))
        block_ids = list(dict.fromkeys(_string_list(item.get("block_ids"))))
        if not statement or not block_ids:
            return None
        if any(block_id not in section_by_block_id for block_id in block_ids):
            return None
        # The citations decide whether this is cross-section, so the sections are
        # read back from them rather than asked for and then checked against them.
        if len({section_by_block_id[block_id] for block_id in block_ids}) < 2:
            return None
        out.append(
            Finding(
                id=f"conflict|{index}",
                reason="conflicting",
                statement=statement,
                recommendation=_string_value(item.get("recommendation")),
                cited_block_ids=block_ids,
            )
        )
    return out
