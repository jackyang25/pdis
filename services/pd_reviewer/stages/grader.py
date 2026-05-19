from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any

from services.chunker import ContentBlock

from ..models import (
    Grade,
    LLMClientProtocol,
    ReviewConfig,
    SectionGrade,
    SectionSpec,
    VariableGrade,
)

logger = logging.getLogger(__name__)

VALID_GRADES: set[str] = {"A", "B", "C", "D", "F", "N/A"}


def grade_sections(
    labeled_blocks: list[ContentBlock],
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
    peer_claims: list | None = None,
) -> list[SectionGrade]:
    """
    For each section, ask the LLM to grade completeness and adherence.

    If `peer_claims` is provided (Claim records from OTHER documents in the
    same intervention/therapeutic area), they're injected into the grader
    prompt as **comparative benchmark context**. The grader can then judge
    the document being graded against what peer documents have claimed.
    """
    blocks_by_section = _group_blocks_by_section(labeled_blocks)
    section_grades: list[SectionGrade] = []
    peer_context = _format_peer_claims_for_prompt(peer_claims) if peer_claims else ""

    for section_spec in config.sections:
        section_blocks = blocks_by_section.get(section_spec.name, [])
        if not section_blocks:
            section_grades.append(_missing_section_grade(section_spec))
            continue

        system_prompt = _build_system_prompt(section_spec)
        user_message = _build_user_message(
            section_spec,
            section_blocks,
            peer_context=_filter_peers_for_section(peer_context, section_spec),
        )
        section_grades.append(
            _grade_section(
                section_spec.name,
                section_blocks,
                system_prompt,
                user_message,
                llm_client,
                max_tokens=max_tokens,
            )
        )

    return section_grades


def _format_peer_claims_for_prompt(peer_claims: list) -> str:
    """Render peer claims grouped by attribute_ref for comparative context."""
    if not peer_claims:
        return ""
    # Group by attribute_ref so the grader can see "for vaccine.efficacy, peers said..."
    by_attr: dict[str, list] = {}
    for claim in peer_claims:
        attr = getattr(claim, "attribute_ref", None) or "unbound"
        by_attr.setdefault(attr, []).append(claim)

    # Track distinct source documents in the peer set
    sources = {getattr(c, "source_id", "") for c in peer_claims if getattr(c, "source_id", None)}
    n_docs = len(sources)
    n_claims = len(peer_claims)

    lines = [
        "",
        f"PEER BENCHMARK — {n_claims} claims from {n_docs} peer document(s) "
        f"in the same intervention class. Use as comparative context when grading "
        f"the document above. Flag where this document is below, above, or absent "
        f"relative to peer claims.",
        "",
    ]
    for attr in sorted(by_attr.keys()):
        claims_for_attr = by_attr[attr]
        lines.append(f"  {attr} ({len(claims_for_attr)} peer claim(s)):")
        for claim in claims_for_attr[:5]:  # cap at 5 per attribute to keep prompt tight
            statement = (getattr(claim, "statement", "") or "")[:160]
            src = getattr(claim, "source_id", "?")
            lines.append(f"    - [{src}] {statement}")
        if len(claims_for_attr) > 5:
            lines.append(f"    ... ({len(claims_for_attr) - 5} more)")
    return "\n".join(lines)


def _filter_peers_for_section(peer_context: str, section_spec: SectionSpec) -> str:
    """For now, pass full peer context to every section. Future: filter by section's expected attributes."""
    return peer_context


def _grade_section(
    section_name: str,
    section_blocks: list[ContentBlock],
    system_prompt: str,
    user_message: str,
    llm_client: LLMClientProtocol,
    max_tokens: int,
) -> SectionGrade:
    raw_response = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    try:
        return _parse_section_grade(section_name, raw_response, section_blocks)
    except ValueError as first_error:
        logger.warning("Grader returned invalid JSON for %s; retrying", section_name)
        retry_message = (
            f"{user_message}\n\n"
            "Your previous response was invalid JSON. Return only one valid JSON object "
            "matching the requested schema."
        )
        raw_response = llm_client.call(
            system_prompt,
            retry_message,
            max_tokens=max_tokens,
        )
        try:
            return _parse_section_grade(section_name, raw_response, section_blocks)
        except ValueError:
            logger.exception(
                "Grader failed for %s after retry: %s",
                section_name,
                first_error,
            )
            return SectionGrade(
                section_name=section_name,
                grade="N/A",
                is_present=True,
                issues=["Grading failed."],
                recommendation="Retry grading or review this section manually.",
            )


def _build_system_prompt(section_spec: SectionSpec) -> str:
    rubric = """You are reviewing a PD document.

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Grade definitions:
- A: Meets all configured expectations. Quantitative where required. Annotations cite sources.
- B: Mostly complete. Minor gaps in annotations or optional details.
- C: Acceptable but weak. Several variables lack source data or are qualitative where they should be quantitative.
- D: Significant gaps. Multiple required variables missing or contain only placeholder text.
- F: Section largely empty, contradicts itself, or violates structural expectations.
- N/A: Section not applicable.

Review criteria:
- Quantitative criteria: numeric targets ("at least X%") preferred over vague language ("better").
- Source data: annotations should cite data sources, regulatory precedents, or comparable interventions.
- Template tokens: content with <<...>> placeholders has not been filled in.
- Both columns filled: Minimum AND Optimistic should be populated.
- Internal consistency: contradictions between sections are issues.

Output schema:
{
  "section_name": "section name",
  "grade": "A|B|C|D|F|N/A",
  "is_present": true,
  "missing_variables": ["missing expected variable"],
  "issues": ["specific issue"],
  "recommendation": "specific recommendation",
  "variable_grades": [
    {
      "variable_name": "variable name",
      "grade": "A|B|C|D|F|N/A",
      "issues": ["specific issue"],
      "recommendation": "specific recommendation",
      "block_ids": ["source block id"]
    }
  ]
}"""
    if section_spec.variables:
        section_instructions = "\n".join(
            [
                f"\nSection: {section_spec.name}",
                f"What this section should cover: {section_spec.description}",
                "",
                "Expected variables and what each should contain:",
                *_format_variable_specs(section_spec),
                "",
                "Grade this section A-F. For each expected variable:",
                "- Determine if it is present in the content.",
                "- If present, grade it A-F with specific issues and recommendation.",
                "- Include the source block_ids that support each present variable grade.",
                "- If missing, list it in missing_variables.",
                "",
                "Missing required variables should significantly downgrade the section.",
                "Only include present variables in variable_grades.",
                "Only use block_ids exactly as provided in the actual document blocks.",
                "Apply the universal rubric: quantitative criteria, source data in annotations, no template tokens, and both Minimum and Optimistic columns filled.",
            ]
        )
    else:
        section_instructions = (
            f"\nSection: {section_spec.name}\n"
            f"What this section should cover: {section_spec.description}\n\n"
            "Grade this prose section A-F based on completeness, specificity, source support, "
            "absence of template tokens, and alignment with the section description. "
            "Return missing_variables as an empty list and variable_grades as an empty list."
        )

    return f"{rubric}\n{section_instructions}"


def _build_user_message(
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
    *,
    peer_context: str = "",
) -> str:
    parts = [
        f"Section: {section_spec.name}",
        f"What this section should cover: {section_spec.description}",
        "Actual document blocks:",
        _format_blocks(section_blocks),
    ]
    if peer_context:
        parts.append(peer_context)
    return "\n\n".join(parts)


def _format_variable_specs(section_spec: SectionSpec) -> list[str]:
    lines: list[str] = []
    for variable in section_spec.variables:
        lines.append(f"- {variable.name}: {variable.description}")
    return lines


def _format_blocks(blocks: list[ContentBlock]) -> str:
    if not blocks:
        return "(none)"
    return "\n\n".join(_format_block(block) for block in blocks)


def _format_block(block: ContentBlock) -> str:
    heading_stack = " > ".join(block.heading_stack) if block.heading_stack else "none"
    return (
        f"[{block.id} | {block.block_type} | headings: {heading_stack}]\n"
        f"{block.content}"
    )


def _parse_section_grade(
    expected_section_name: str,
    raw_response: str,
    section_blocks: list[ContentBlock],
) -> SectionGrade:
    parsed = json.loads(_extract_json_object(_strip_markdown_fences(raw_response).strip()))
    if not isinstance(parsed, dict):
        raise ValueError("Grader response must be an object")

    section_name = _string_value(parsed.get("section_name")) or expected_section_name
    grade = _grade_value(parsed.get("grade"))
    variable_grades = [
        _parse_variable_grade(item, section_blocks)
        for item in _list_value(parsed.get("variable_grades"))
        if isinstance(item, dict)
    ]
    return SectionGrade(
        section_name=section_name,
        grade=grade,
        is_present=_bool_value(parsed.get("is_present"), default=True),
        missing_variables=_string_list(parsed.get("missing_variables")),
        issues=_string_list(parsed.get("issues")),
        recommendation=_string_value(parsed.get("recommendation")),
        variable_grades=variable_grades,
    )


def _parse_variable_grade(
    item: dict[str, Any],
    section_blocks: list[ContentBlock],
) -> VariableGrade:
    variable_name = _string_value(item.get("variable_name"))
    return VariableGrade(
        variable_name=variable_name,
        grade=_grade_value(item.get("grade")),
        issues=_string_list(item.get("issues")),
        recommendation=_string_value(item.get("recommendation")),
        block_ids=_valid_block_ids(item.get("block_ids"), section_blocks),
    )


def _valid_block_ids(value: Any, section_blocks: list[ContentBlock]) -> list[str]:
    valid_ids = {block.id for block in section_blocks}
    block_ids = []
    for block_id in _string_list(value):
        if block_id in valid_ids and block_id not in block_ids:
            block_ids.append(block_id)
    return block_ids


def _missing_section_grade(section_spec: SectionSpec) -> SectionGrade:
    return SectionGrade(
        section_name=section_spec.name,
        grade="F",
        is_present=False,
        issues=["Section is missing."],
        recommendation=f"Add this section covering: {section_spec.description}",
    )


def _group_blocks_by_section(
    blocks: list[ContentBlock],
) -> dict[str, list[ContentBlock]]:
    blocks_by_section: dict[str, list[ContentBlock]] = defaultdict(list)
    for block in blocks:
        if block.section_label:
            blocks_by_section[block.section_label].append(block)
    return dict(blocks_by_section)


def _strip_markdown_fences(raw_response: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw_response, re.DOTALL)
    if match:
        return match.group(1)
    return raw_response


def _extract_json_object(response_text: str) -> str:
    decoder = json.JSONDecoder()
    for start_index, char in enumerate(response_text):
        if char != "{":
            continue
        try:
            parsed, end_index = decoder.raw_decode(response_text[start_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return response_text[start_index : start_index + end_index]
    return response_text


def _grade_value(value: Any) -> Grade:
    grade = str(value or "N/A").strip().upper()
    if grade not in VALID_GRADES:
        raise ValueError(f"Invalid grade: {value}")
    return grade  # type: ignore[return-value]


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _list_value(value: Any) -> list:
    return value if isinstance(value, list) else []


def _bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())
