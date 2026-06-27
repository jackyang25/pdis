"""Two-dimension grader.

Each section is graded by TWO independent LLM calls - one per dimension
(completeness, adherence). Each call's prompt contains only the
rules and inputs that dimension needs:

- completeness call: rubric + draft.
- adherence call:    rubric + draft.

The two results are merged into a single SectionGrade (or VariableGrade
list) with the same `dimensions` shape the rest of the system already
consumes. The I/O contract is unchanged.

Sections grade in parallel, and the two dimension calls within each
section also run in parallel — so total wall-clock stays close to the
slowest individual LLM call.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from services.chunker import ContentBlock

from ..models import (
    DIMENSIONS,
    CrossSectionFinding,
    DimensionGrade,
    Grade,
    LLMClientProtocol,
    ReviewConfig,
    SectionGrade,
    SectionSpec,
    VariableGrade,
    VariableSpec,
)

logger = logging.getLogger(__name__)

VALID_GRADES: set[str] = {"A", "B", "C", "D", "F", "N/A"}
GRADE_TO_SCORE = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def grade_sections(
    labeled_blocks: list[ContentBlock],
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
    progress=None,
) -> list[SectionGrade]:
    blocks_by_section = _group_blocks_by_section(labeled_blocks)
    indexed: list[tuple[int, SectionSpec, list[ContentBlock] | None]] = []
    for idx, section_spec in enumerate(config.sections):
        section_blocks = blocks_by_section.get(section_spec.name, [])
        indexed.append((idx, section_spec, section_blocks or None))

    total = len(indexed)
    if progress:
        progress("grade", completed=0, total=total)
    lock = threading.Lock()
    done = {"n": 0}

    def grade_one(item):
        idx, section_spec, section_blocks = item
        if not section_blocks:
            out = (idx, _missing_section_grade(section_spec))
        else:
            section_grade = _grade_section(
                section_spec=section_spec,
                section_blocks=section_blocks,
                llm_client=llm_client,
                max_tokens=max_tokens,
                grading_guidance=config.grading_guidance,
            )
            if section_spec.variables:
                section_grade.dimensions = _rollup_dimensions(
                    [vg.dimensions for vg in section_grade.variable_grades]
                )
            out = (idx, section_grade)
        if progress:
            with lock:
                done["n"] += 1
                progress("grade", completed=done["n"], total=total)
        return out

    if len(indexed) <= 1:
        graded = [grade_one(item) for item in indexed]
    else:
        with ThreadPoolExecutor(max_workers=len(indexed)) as executor:
            graded = list(executor.map(grade_one, indexed))

    graded.sort(key=lambda pair: pair[0])
    return [g for _, g in graded]


# ---------------------------------------------------------------------------
# Per-section grading: two parallel dimension calls
# ---------------------------------------------------------------------------


def _grade_section(
    *,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
    grading_guidance: str = "",
) -> SectionGrade:
    """Run two independent dimension calls and merge into one SectionGrade."""

    blocks_text = _format_blocks(section_blocks)

    def call_completeness():
        return _call_dimension(
            dimension="completeness",
            section_spec=section_spec,
            blocks_text=blocks_text,
            section_blocks=section_blocks,
            llm_client=llm_client,
            max_tokens=max_tokens,
            grading_guidance=grading_guidance,
        )

    def call_adherence():
        return _call_dimension(
            dimension="adherence",
            section_spec=section_spec,
            blocks_text=blocks_text,
            section_blocks=section_blocks,
            llm_client=llm_client,
            max_tokens=max_tokens,
            grading_guidance=grading_guidance,
        )

    def call_rigor():
        return _call_dimension(
            dimension="rigor",
            section_spec=section_spec,
            blocks_text=blocks_text,
            section_blocks=section_blocks,
            llm_client=llm_client,
            max_tokens=max_tokens,
            grading_guidance=grading_guidance,
        )

    with ThreadPoolExecutor(max_workers=len(DIMENSIONS)) as executor:
        futures = {
            "completeness": executor.submit(call_completeness),
            "adherence": executor.submit(call_adherence),
            "rigor": executor.submit(call_rigor),
        }
        results = {name: future.result() for name, future in futures.items()}

    return _merge_dimension_results(section_spec, results)


def _call_dimension(
    *,
    dimension: str,
    section_spec: SectionSpec,
    blocks_text: str,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
    grading_guidance: str = "",
) -> dict[str, Any]:
    """Build the per-dimension prompt, call the LLM, parse the JSON.

    Returns the parsed dict from the LLM. Shape:

      Variable-bearing section:
        {
          "missing_variables": [str, ...],   # completeness only
          "variable_grades": [
            {
              "variable_name": str,
              "block_ids": [str, ...],
              "grade": "A|B|C|D|F|N/A",
              "issues": [str, ...],
              "recommendation": str
            }
          ]
        }

      Prose section:
        {
          "grade": "A|B|C|D|F|N/A",
          "issues": [str, ...],
          "recommendation": str
        }
    """
    system_prompt = _build_system_prompt(dimension, section_spec, grading_guidance)
    user_message = _build_user_message(
        section_spec=section_spec,
        blocks_text=blocks_text,
    )
    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    try:
        return _parse_dimension_response(raw, section_spec, section_blocks)
    except ValueError as first_error:
        retry_message = (
            f"{user_message}\n\nYour previous response was invalid JSON. "
            "Return only one valid JSON object matching the requested schema."
        )
        raw = llm_client.call(system_prompt, retry_message, max_tokens=max_tokens)
        try:
            return _parse_dimension_response(raw, section_spec, section_blocks)
        except ValueError:
            logger.exception(
                "Grader failed for %s on %s after retry: %s",
                section_spec.name,
                dimension,
                first_error,
            )
            return _failed_dimension_response(section_spec)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_system_prompt(
    dimension: str, section_spec: SectionSpec, grading_guidance: str = ""
) -> str:
    preamble = """You are reviewing a section of a PD document.

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Grade scale (A–F + N/A):
- A: Fully meets expectations on this dimension.
- B: Substantially meets expectations. Minor issues only.
- C: Partially meets expectations. Noticeable gaps.
- D: Significant gaps on this dimension.
- F: Largely fails this dimension.
- N/A: Not applicable.

Style for issues and recommendations:
- Each issue is one short factual statement (≤20 words). No preamble.
- Each recommendation is one short action sentence (≤20 words). Action-verb-leading. No preamble.
- Do not repeat the variable name. Do not hedge."""

    if dimension == "completeness":
        focus = _build_completeness_focus(section_spec)
    elif dimension == "adherence":
        focus = _build_adherence_focus(section_spec)
    elif dimension == "rigor":
        focus = _build_rigor_focus(section_spec)
    else:
        raise ValueError(f"Unknown dimension: {dimension}")

    output_schema = _output_schema(dimension, section_spec)

    parts = [preamble]
    if grading_guidance.strip():
        parts.append("# GRADING BAR (document stage)\n" + grading_guidance.strip())
    parts.extend([focus, output_schema])
    return "\n\n".join(parts)


def _build_completeness_focus(section_spec: SectionSpec) -> str:
    lines = [
        "# DIMENSION: COMPLETENESS",
        "Question: is every required variable filled with substantive content?",
        "",
        "Inputs you may consider: the rubric's expected variables and the draft content.",
        "",
        "Rules:",
        "- A required variable is missing if it has no content at all.",
        "- A variable is incomplete if only one of Minimum/Optimistic is filled, or values are placeholders (<<TBD>>, TBD, blank, dashes).",
        "- Substantive content means a concrete value or sentence, not a category label.",
    ]
    if section_spec.completeness:
        lines.append("")
        lines.append("Additional rules from rubric config:")
        for key, value in section_spec.completeness.items():
            lines.append(f"- {key}: {value}")
    if section_spec.variables:
        lines.append("")
        lines.append("Expected variables for this section:")
        for v in section_spec.variables:
            extra = _format_variable_dimension_rules(v, "completeness")
            lines.append(f"- {v.name}: {v.description}{extra}")
    return "\n".join(lines)


def _build_adherence_focus(section_spec: SectionSpec) -> str:
    lines = [
        "# DIMENSION: ADHERENCE",
        "Question: does the content follow the rubric's structural expectations?",
        "",
        "Inputs you may consider: the rubric's structural rules and the draft content.",
        "",
        "Rules:",
        "- Section and variable names should match the rubric's expected names.",
        "- Annotations column should be present where the rubric expects it.",
        "- No template tokens like <<...>> should remain.",
        "- No internal contradictions between Minimum and Optimistic columns.",
    ]
    if section_spec.adherence:
        lines.append("")
        lines.append("Additional rules from rubric config:")
        for key, value in section_spec.adherence.items():
            lines.append(f"- {key}: {value}")
    if section_spec.variables:
        lines.append("")
        lines.append("Expected variables for this section:")
        for v in section_spec.variables:
            extra = _format_variable_dimension_rules(v, "adherence")
            lines.append(f"- {v.name}: {v.description}{extra}")
    return "\n".join(lines)


def _build_rigor_focus(section_spec: SectionSpec) -> str:
    lines = [
        "# DIMENSION: RIGOR",
        "Question: is the content substantively sound - specific, measurable, and meaningful?",
        "",
        "This is about QUALITY, not presence (that is completeness) and not formatting (that "
        "is adherence). Do NOT re-report missing variables, naming, template tokens, or "
        "structural issues here - only the substantive quality of the content that IS present.",
        "",
        "Rules:",
        "- Measurability: a target should be concrete and testable - a value with units or a "
        "clear pass/fail - not vague language ('robust', 'adequate', 'best-in-class') that has "
        "no testable meaning.",
        "- Specificity: the target should be unambiguous; flag hand-waving or undefined terms.",
        "- Soundness: the value should be meaningful for the variable; flag filler that is "
        "technically present but says nothing, or a target that is internally implausible.",
        "- Judge against the document's stage (see GRADING BAR above): an intervention-stage "
        "qualitative target can still be rigorous if it is clear and bounded; a candidate-stage "
        "target should be concretely measured.",
    ]
    if section_spec.rigor:
        lines.append("")
        lines.append("Additional rules from rubric config:")
        for key, value in section_spec.rigor.items():
            lines.append(f"- {key}: {value}")
    if section_spec.variables:
        lines.append("")
        lines.append("Expected variables for this section:")
        for v in section_spec.variables:
            extra = _format_variable_dimension_rules(v, "rigor")
            lines.append(f"- {v.name}: {v.description}{extra}")
    return "\n".join(lines)


def _format_variable_dimension_rules(v: VariableSpec, dimension: str) -> str:
    block = getattr(v, dimension, {}) or {}
    if not block:
        return ""
    parts = [f"{k}={v_}" for k, v_ in block.items()]
    return f"  [rules: {', '.join(parts)}]"


def _output_schema(dimension: str, section_spec: SectionSpec) -> str:
    if section_spec.variables:
        per_variable = (
            '{"variable_name": "exact name", "block_ids": ["block id"], '
            '"grade": "A|B|C|D|F|N/A", "issues": ["..."], "recommendation": "..."'
        )
        per_variable += "}"

        schema = {
            "missing_variables": "list of expected variable names not present in the content (completeness only - leave empty for adherence)",
            "variable_grades": f"list of {per_variable}",
        }
        return "Output schema:\n" + json.dumps(schema, indent=2)
    else:
        section_obj = '{"grade": "A|B|C|D|F|N/A", "issues": ["..."], "recommendation": "..."'
        section_obj += "}"
        return f"Output schema:\n{section_obj}"


def _build_user_message(
    *,
    section_spec: SectionSpec,
    blocks_text: str,
) -> str:
    parts = [
        f"Section: {section_spec.name}",
        f"What this section should cover: {section_spec.description}",
        "Actual document blocks:",
        blocks_text,
    ]
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_dimension_response(
    raw: str,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
) -> dict[str, Any]:
    parsed = json.loads(_extract_json_object(_strip_markdown_fences(raw).strip()))
    if not isinstance(parsed, dict):
        raise ValueError("Grader response must be an object")

    if section_spec.variables:
        variable_grades_raw = parsed.get("variable_grades")
        if not isinstance(variable_grades_raw, list):
            raise ValueError("variable_grades must be a list")
        valid_block_ids = {b.id for b in section_blocks}
        cleaned_vars = []
        for item in variable_grades_raw:
            if not isinstance(item, dict):
                continue
            cleaned_vars.append(
                {
                    "variable_name": _string_value(item.get("variable_name")),
                    "block_ids": [
                        bid for bid in _string_list(item.get("block_ids")) if bid in valid_block_ids
                    ],
                    "grade": _grade_value(item.get("grade")),
                    "issues": _string_list(item.get("issues")),
                    "recommendation": _string_value(item.get("recommendation")),
                }
            )
        return {
            "missing_variables": _string_list(parsed.get("missing_variables")),
            "variable_grades": cleaned_vars,
        }

    return {
        "grade": _grade_value(parsed.get("grade")),
        "issues": _string_list(parsed.get("issues")),
        "recommendation": _string_value(parsed.get("recommendation")),
    }


def _failed_dimension_response(section_spec: SectionSpec) -> dict[str, Any]:
    if section_spec.variables:
        return {"missing_variables": [], "variable_grades": []}
    return {
        "grade": "N/A",
        "issues": ["Grading failed."],
        "recommendation": "Retry grading or review this section manually.",
    }


# ---------------------------------------------------------------------------
# Merging three dimension responses into a SectionGrade
# ---------------------------------------------------------------------------


def _merge_dimension_results(
    section_spec: SectionSpec,
    results: dict[str, dict[str, Any]],
) -> SectionGrade:
    if section_spec.variables:
        return _merge_variable_bearing(section_spec, results)
    return _merge_prose(section_spec, results)


def _merge_variable_bearing(
    section_spec: SectionSpec,
    results: dict[str, dict[str, Any]],
) -> SectionGrade:
    # Use completeness's missing_variables as the canonical list.
    missing = list(results.get("completeness", {}).get("missing_variables", []))

    # Index each dimension's variable_grades by variable_name.
    per_dim_by_name: dict[str, dict[str, dict[str, Any]]] = {
        dim: {vg["variable_name"]: vg for vg in results.get(dim, {}).get("variable_grades", [])}
        for dim in DIMENSIONS
    }

    # Variables to build grades for: union of named variables across all dimensions
    # (in rubric order so the output is stable).
    all_names: list[str] = []
    seen: set[str] = set()
    for v in section_spec.variables:
        if v.name in seen:
            continue
        if any(v.name in per_dim_by_name[d] for d in DIMENSIONS):
            all_names.append(v.name)
            seen.add(v.name)
    # Pick up any extra names the LLM produced that aren't in the rubric.
    for d in DIMENSIONS:
        for n in per_dim_by_name[d]:
            if n and n not in seen:
                all_names.append(n)
                seen.add(n)

    variable_grades: list[VariableGrade] = []
    for name in all_names:
        block_ids: list[str] = []
        dimensions: dict[str, DimensionGrade] = {}
        for d in DIMENSIONS:
            item = per_dim_by_name[d].get(name)
            if item is None:
                dimensions[d] = DimensionGrade(grade="N/A")
                continue
            dimensions[d] = DimensionGrade(
                grade=item.get("grade", "N/A"),
                issues=list(item.get("issues", [])),
                recommendation=item.get("recommendation", ""),
            )
            for bid in item.get("block_ids", []):
                if bid not in block_ids:
                    block_ids.append(bid)
        variable_grades.append(
            VariableGrade(
                variable_name=name,
                dimensions=dimensions,
                block_ids=block_ids,
            )
        )

    # Section dimensions get rolled up from variable dimensions in the caller.
    return SectionGrade(
        section_name=section_spec.name,
        is_present=True,
        dimensions={d: DimensionGrade(grade="N/A") for d in DIMENSIONS},
        missing_variables=missing,
        variable_grades=variable_grades,
    )


def _merge_prose(
    section_spec: SectionSpec,
    results: dict[str, dict[str, Any]],
) -> SectionGrade:
    dimensions: dict[str, DimensionGrade] = {}
    for d in DIMENSIONS:
        item = results.get(d, {})
        dimensions[d] = DimensionGrade(
            grade=item.get("grade", "N/A"),
            issues=list(item.get("issues", [])),
            recommendation=item.get("recommendation", ""),
        )
    return SectionGrade(
        section_name=section_spec.name,
        is_present=True,
        dimensions=dimensions,
    )


# ---------------------------------------------------------------------------
# Helpers shared with the rest of the pipeline
# ---------------------------------------------------------------------------


def _rollup_dimensions(
    children: list[dict[str, DimensionGrade]],
) -> dict[str, DimensionGrade]:
    """Average each dimension across children; collect issues/recommendations."""
    out: dict[str, DimensionGrade] = {}
    for name in DIMENSIONS:
        grades = [c[name].grade for c in children if name in c]
        score = _average_score(grades)
        issues: list[str] = []
        recs: list[str] = []
        for c in children:
            dg = c.get(name)
            if dg is None:
                continue
            issues.extend(dg.issues)
            if dg.recommendation:
                recs.append(dg.recommendation)
        out[name] = DimensionGrade(
            grade=_score_to_grade(score),
            issues=issues,
            recommendation="; ".join(dict.fromkeys(recs)),
        )
    return out


def _average_score(grades: list[Grade]) -> float | None:
    scores = [GRADE_TO_SCORE[g] for g in grades if g in GRADE_TO_SCORE]
    if not scores:
        return None
    return sum(scores) / len(scores)


def _score_to_grade(score: float | None) -> Grade:
    if score is None:
        return "N/A"
    if score >= 3.5:
        return "A"
    if score >= 2.5:
        return "B"
    if score >= 1.5:
        return "C"
    if score >= 0.5:
        return "D"
    return "F"


def _missing_section_grade(section_spec: SectionSpec) -> SectionGrade:
    missing = DimensionGrade(
        grade="F",
        issues=["Section is missing."],
        recommendation=f"Add this section covering: {section_spec.description}",
    )
    return SectionGrade(
        section_name=section_spec.name,
        is_present=False,
        dimensions={d: missing for d in DIMENSIONS},
    )


def _group_blocks_by_section(
    blocks: list[ContentBlock],
) -> dict[str, list[ContentBlock]]:
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


def _strip_markdown_fences(raw: str) -> str:
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw, re.DOTALL)
    if match:
        return match.group(1)
    return raw


def _extract_json_object(text: str) -> str:
    decoder = json.JSONDecoder()
    for start in range(len(text)):
        if text[start] != "{":
            continue
        try:
            parsed, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return text[start : start + end]
    return text


def _grade_value(value: Any) -> Grade:
    grade = str(value or "N/A").strip().upper()
    if grade not in VALID_GRADES:
        return "N/A"
    return grade  # type: ignore[return-value]


def _string_value(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _extract_json_array(text: str) -> str:
    decoder = json.JSONDecoder()
    for start in range(len(text)):
        if text[start] != "[":
            continue
        try:
            parsed, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return text[start : start + end]
    return text


# ---------------------------------------------------------------------------
# Cross-section consistency: the one pass that sees ALL sections at once
# ---------------------------------------------------------------------------

# Whole-doc context cap, in lockstep spirit with the other doc-reading stages so
# a long document never silently loses its tail in this pass.
MAX_DOC_CONTEXT_CHARS = 120000


def check_cross_section(
    labeled_blocks: list[ContentBlock],
    config: ReviewConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> list[CrossSectionFinding]:
    """Find consistency problems that span MORE THAN ONE section.

    Per-section grading is deliberately isolated (a section never sees another),
    so it cannot catch "Section A targets >=80%, Section B says 90%". This pass
    sees every section together and reports only cross-section conflicts. It is
    an additive quality layer: any parse failure returns [] and never blocks the
    report."""
    blocks_by_section = _group_blocks_by_section(labeled_blocks)
    if len(blocks_by_section) < 2:
        return []  # need at least two sections for a cross-section conflict

    system_prompt = _cross_section_system_prompt(config)
    user_message = _cross_section_user_message(blocks_by_section)

    raw = llm_client.call(system_prompt, user_message, max_tokens=max_tokens)
    findings = _parse_cross_section(raw)
    if findings is None:
        raw = llm_client.call(
            system_prompt,
            user_message + "\n\nYour previous reply was invalid. Return only a JSON array.",
            max_tokens=max_tokens,
        )
        findings = _parse_cross_section(raw)
    return findings or []


def _cross_section_system_prompt(config: ReviewConfig) -> str:
    return (
        f"You check a {config.intervention_class} Target Product Profile for CROSS-SECTION "
        "consistency: places where TWO DIFFERENT sections state conflicting or mismatched "
        "claims about the SAME attribute - e.g. one section targets >=80% efficacy and "
        "another states 90%; the target population, dosing schedule, presentation, or "
        "timelines disagree between sections.\n\n"
        "Report ONLY conflicts that span more than one section. Do NOT report problems "
        "inside a single section, missing content, vague wording, or formatting - those are "
        "graded elsewhere. If there are no cross-section conflicts, return an empty array.\n\n"
        "Return ONLY a JSON array. No markdown, no preamble. Each item:\n"
        '{"description": "the specific conflicting values and what disagrees", '
        '"sections": ["Section A name", "Section B name"], '
        '"recommendation": "one short action to reconcile them"}'
    )


def _cross_section_user_message(
    blocks_by_section: dict[str, list[ContentBlock]],
) -> str:
    parts: list[str] = ["Document sections and their content:\n"]
    for section_name, blocks in blocks_by_section.items():
        parts.append(f"=== SECTION: {section_name} ===")
        parts.append(_format_blocks(blocks))
        parts.append("")
    body = "\n".join(parts)
    if len(body) > MAX_DOC_CONTEXT_CHARS:
        body = body[:MAX_DOC_CONTEXT_CHARS] + "\n...[truncated]"
    return body + "\nFind cross-section consistency conflicts now."


def _parse_cross_section(raw: str) -> list[CrossSectionFinding] | None:
    text = _strip_markdown_fences(raw).strip()
    try:
        parsed = json.loads(_extract_json_array(text))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, list):
        return None
    out: list[CrossSectionFinding] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        description = _string_value(item.get("description"))
        if not description:
            continue
        out.append(
            CrossSectionFinding(
                description=description,
                sections=_string_list(item.get("sections")),
                recommendation=_string_value(item.get("recommendation")),
            )
        )
    return out
