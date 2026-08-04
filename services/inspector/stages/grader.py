"""Three-dimension grader.

Each section is graded once per dimension (completeness, adherence, rigor)
and once per rubric variable within it, so a variable's grade never shares a
prompt with an unrelated variable. Each call's prompt contains only the rules
and inputs that dimension needs:

- completeness call: rubric + draft.
- adherence call:    rubric + draft.
- rigor call:         rubric + draft.

The three results are merged into a single SectionGrade (or VariableGrade
list) with the same `dimensions` shape the rest of the system already
consumes. The I/O contract is unchanged.

Sections grade in parallel, and the three dimension calls within each
section also run in parallel — so total wall-clock stays close to the
slowest individual LLM call.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import replace
from typing import Any

from shared.ai import request_structured
from shared.batching import fixed_batches, map_ordered

from services.chunker import ContentBlock

from ..models import (
    DIMENSIONS,
    CrossSectionFinding,
    ConsistencyStatus,
    DimensionAssessment,
    DimensionVerdict,
    LLMClientProtocol,
    InspectionConfig,
    SectionGrade,
    SectionSpec,
    VariableGrade,
    VariableSpec,
    ABSENT_CONTENT_STATUS,
    CONTENT_STATUSES,
    PRESENT_CONTENT_STATUSES,
    DIMENSION_VERDICTS,
    INAPPLICABLE_VERDICT,
)

MAX_PARALLEL_SECTIONS = 4
# Per-item scope: one grade per rubric variable, so an unrelated variable can
# never sit in this decision's prompt. Speed comes from dimension fan-out.
VARIABLES_PER_REQUEST = 1
MAX_PARALLEL_DIMENSION_BATCHES = 6


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def grade_sections(
    labeled_blocks: list[ContentBlock],
    config: InspectionConfig,
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
            # Publish the mapping used to build this section's prompt, so the
            # contract check and the document view read it instead of each
            # rebuilding it from `section_label`.
            section_grade.mapped_block_ids = [block.id for block in section_blocks]
            out = (idx, section_grade)
        if progress:
            with lock:
                done["n"] += 1
                progress("grade", completed=done["n"], total=total)
        return out

    # map_ordered guarantees input order, so no re-sort is needed.
    graded = map_ordered(indexed, grade_one, workers=MAX_PARALLEL_SECTIONS)
    return [g for _, g in graded]


# ---------------------------------------------------------------------------
# Per-section grading: three parallel dimension calls
# ---------------------------------------------------------------------------


def _grade_section(
    *,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    max_tokens: int,
    grading_guidance: str = "",
) -> SectionGrade:
    """Run three independent dimension calls and merge into one SectionGrade."""

    blocks_text = _format_blocks(section_blocks)

    variable_batches = _variable_batches(section_spec.variables)
    jobs = [
        (dimension, variables)
        for dimension in DIMENSIONS
        for variables in variable_batches
    ]

    def call_one(item: tuple[str, list[VariableSpec]]) -> tuple[str, dict[str, Any]]:
        dimension, variables = item
        return dimension, _call_dimension(
            dimension=dimension,
            section_spec=replace(section_spec, variables=variables),
            blocks_text=blocks_text,
            section_blocks=section_blocks,
            llm_client=llm_client,
            max_tokens=max_tokens,
            grading_guidance=grading_guidance,
        )

    batch_results = map_ordered(jobs, call_one, workers=MAX_PARALLEL_DIMENSION_BATCHES)

    if not section_spec.variables:
        results = {dimension: batch for dimension, batch in batch_results}
    else:
        results = {dimension: {"variable_grades": []} for dimension in DIMENSIONS}
        for dimension, batch in batch_results:
            results[dimension]["variable_grades"].extend(
                batch.get("variable_grades", [])
            )

    return _merge_dimension_results(section_spec, results)


def _variable_batches(variables: list[VariableSpec]) -> list[list[VariableSpec]]:
    if not variables:
        return [[]]
    return fixed_batches(variables, VARIABLES_PER_REQUEST)


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
    """Build one schema-bound dimension decision and validate its lineage.

    Returns the parsed dict from the LLM. Shape:

      Variable-bearing section:
        {
          "variable_grades": [
            {
              "variable_name": str,
              "block_ids": [str, ...],
              "verdict": "critical|for_consideration|meets|not_applicable",
              "issues": [str, ...],
              "recommendation": str
            }
          ]
        }

      Prose section:
        {
          "verdict": "critical|for_consideration|meets|not_applicable",
          "issues": [str, ...],
          "recommendation": str
        }
    """
    system_prompt = build_dimension_prompt(dimension, section_spec, grading_guidance)
    user_message = _build_user_message(
        section_spec=section_spec,
        blocks_text=blocks_text,
    )
    images = _image_inputs(section_blocks)
    schema = _dimension_schema(dimension, section_spec, section_blocks)
    first_error = "model returned no structured decision"
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior decision failed the Inspector contract: "
                f"{first_error}. Return one complete decision for every listed rubric variable, "
                "using only the supplied variable names and block IDs."
            )
        payload = request_structured(
            llm_client,
            system_prompt,
            message,
            max_tokens=max_tokens,
            schema_name=f"inspector_{dimension}_verdict",
            schema=schema,
            images=images or None,
        )
        try:
            if payload is None:
                raise ValueError("model returned no structured decision")
            return _parse_dimension_payload(
                payload, dimension, section_spec, section_blocks
            )
        except ValueError as exc:
            first_error = str(exc)
    raise ValueError(
        f"Inspector could not complete {dimension} grading for {section_spec.name}: "
        f"{first_error}"
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_dimension_prompt(
    dimension: str, section_spec: SectionSpec, grading_guidance: str = ""
) -> str:
    preamble = """You are inspecting a section of a product-development document against its authored rubric.

Scope boundary:
- Judge the quality and usability of what the document states; do not assess real-world program feasibility or investment merit.
- If the rubric expects risks, judge whether the document identifies, rates, and mitigates them. Do not independently assign program risk levels.
- Do not recommend funding decisions, prioritize an investment portfolio, or propose organizational support.
- Do not assume external facts or evidence that are absent from the supplied document and rubric.

Return ONLY valid JSON. No markdown fences, no preamble, no explanation.

Verdict for this dimension:
- critical: the rubric requires this and the document does not usably supply it.
- for_consideration: stated and usable, but it could be stronger.
- meets: no gap on this dimension.
- not_applicable: the rubric does not ask this dimension of this content.

Use critical only when the gap must be closed before the document is usable. Do
not rank severity by how much text is missing; rank it by whether a reader could
act on what is there.

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
        "technically present but says nothing, or content that is internally incoherent.",
        "- Internal coherence: Minimum and Optimistic values must not contradict or reverse "
        "their stated ordering.",
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
        status = (
            " For completeness, also classify content_status as substantive, partial, "
            "placeholder, missing, or not_applicable."
            if dimension == "completeness"
            else ""
        )
        lineage = (
            " Completeness owns presence and source lineage: cite exact block IDs for "
            "substantive, partial, or placeholder content, and use no block IDs when content "
            "is missing. For adherence or rigor, use not_applicable with no block IDs when there is no "
            "content to judge."
        )
        return (
            "Output contract: return exactly one decision for every listed variable. "
            "Use exact supplied variable names and block IDs; an absent variable uses no block IDs."
            + status
            + lineage
        )
    return (
        "Output contract: return one section verdict with issues and one recommendation."
    )


def _dimension_schema(
    dimension: str,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
) -> dict[str, Any]:
    verdict = {"type": "string", "enum": sorted(DIMENSION_VERDICTS)}
    strings = {"type": "array", "items": {"type": "string"}}
    if not section_spec.variables:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["verdict", "issues", "recommendation"],
            "properties": {
                "verdict": verdict,
                "issues": strings,
                "recommendation": {"type": "string"},
            },
        }

    required = ["variable_name", "block_ids", "verdict", "issues", "recommendation"]
    properties: dict[str, Any] = {
        "variable_name": {
            "type": "string",
            "enum": [variable.name for variable in section_spec.variables],
        },
        "block_ids": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [block.id for block in section_blocks],
            },
        },
        "verdict": verdict,
        "issues": strings,
        "recommendation": {"type": "string"},
    }
    if dimension == "completeness":
        required.append("content_status")
        properties["content_status"] = {
            "type": "string",
            "enum": sorted(CONTENT_STATUSES),
        }
    count = len(section_spec.variables)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["variable_grades"],
        "properties": {
            "variable_grades": {
                "type": "array",
                "minItems": count,
                "maxItems": count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": required,
                    "properties": properties,
                },
            }
        },
    }


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


def _parse_dimension_payload(
    parsed: object,
    dimension: str,
    section_spec: SectionSpec,
    section_blocks: list[ContentBlock],
) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("Grader response must be an object")

    if section_spec.variables:
        expected_names = [variable.name for variable in section_spec.variables]
        expected_set = set(expected_names)
        variable_grades_raw = parsed.get("variable_grades")
        if not isinstance(variable_grades_raw, list):
            raise ValueError("variable_grades must be a list")
        valid_block_ids = {b.id for b in section_blocks}
        cleaned_by_name: dict[str, dict[str, Any]] = {}
        for item in variable_grades_raw:
            if not isinstance(item, dict):
                raise ValueError("Each variable_grades item must be an object")
            name = _string_value(item.get("variable_name"))
            if name not in expected_set:
                raise ValueError(f"Unknown rubric variable: {name}")
            if name in cleaned_by_name:
                raise ValueError(f"Duplicate variable assessment: {name}")
            raw_block_ids = _string_list(item.get("block_ids"))
            if any(block_id not in valid_block_ids for block_id in raw_block_ids):
                raise ValueError(f"Variable {name} cited an unknown block ID")
            verdict = _verdict_value(item.get("verdict"))
            content_status = (
                _closed_value(item.get("content_status"), CONTENT_STATUSES, "content_status")
                if dimension == "completeness"
                else ""
            )
            absent = content_status == ABSENT_CONTENT_STATUS
            has_source_content = content_status in PRESENT_CONTENT_STATUSES
            if dimension == "completeness" and has_source_content and not raw_block_ids:
                raise ValueError(f"Variable {name} must cite a source block")
            if dimension == "completeness" and raw_block_ids and absent:
                raise ValueError(f"Absent variable {name} cannot cite a source block")
            cleaned_by_name[name] = {
                "variable_name": name,
                "block_ids": list(dict.fromkeys(raw_block_ids)),
                "verdict": verdict,
                "issues": _string_list(item.get("issues")),
                "recommendation": _string_value(item.get("recommendation")),
                "content_status": content_status,
            }
        accounted = set(cleaned_by_name)
        if accounted != expected_set:
            raise ValueError("Every expected variable must be accounted for exactly once")
        # No separate missing list: each item carries its own `content_status`,
        # which is the one authority for presence.
        return {
            "variable_grades": [
                cleaned_by_name[name] for name in expected_names if name in cleaned_by_name
            ],
        }

    return {
        "verdict": _verdict_value(parsed.get("verdict")),
        "issues": _string_list(parsed.get("issues")),
        "recommendation": _string_value(parsed.get("recommendation")),
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
    # Index each dimension's variable_grades by variable_name.
    per_dim_by_name: dict[str, dict[str, dict[str, Any]]] = {
        dim: {vg["variable_name"]: vg for vg in results.get(dim, {}).get("variable_grades", [])}
        for dim in DIMENSIONS
    }

    variable_grades: list[VariableGrade] = []
    for variable in section_spec.variables:
        name = variable.name
        content_status = (
            per_dim_by_name["completeness"].get(name, {}).get("content_status", "")
            or "not_applicable"
        )
        dimensions: dict[str, DimensionAssessment] = {}
        for d in DIMENSIONS:
            item = per_dim_by_name[d].get(name)
            if item is None:
                dimensions[d] = DimensionAssessment(verdict=INAPPLICABLE_VERDICT)
                continue
            dimensions[d] = DimensionAssessment(
                verdict=item.get("verdict", INAPPLICABLE_VERDICT),
                issues=list(item.get("issues", [])),
                recommendation=item.get("recommendation", ""),
                # This dimension's own citations. The parser has already rejected
                # any block outside the section and any lineage that contradicts
                # the presence decision.
                cited_block_ids=list(item.get("block_ids", [])),
            )
        if content_status == ABSENT_CONTENT_STATUS:
            # Absent content cannot be well-formed or rigorous, and cites nothing.
            dimensions["completeness"] = DimensionAssessment(
                verdict="critical",
                issues=["Required variable is missing."],
                recommendation=f"Add substantive content for {name}.",
            )
            dimensions["adherence"] = DimensionAssessment(
                verdict="critical",
                issues=["Required rubric structure is absent."],
                recommendation=f"Add the required {name} entry.",
            )
            dimensions["rigor"] = DimensionAssessment(verdict=INAPPLICABLE_VERDICT)
        elif content_status == "not_applicable":
            dimensions = {
                d: DimensionAssessment(verdict=INAPPLICABLE_VERDICT) for d in DIMENSIONS
            }
        variable_grades.append(
            VariableGrade(
                variable_name=name,
                dimensions=dimensions,
                content_status=content_status,
            )
        )

    # A section that has variables carries no verdict of its own: its variables
    # hold the judgements and `SectionGrade.gap_counts` counts them.
    return SectionGrade(
        section_name=section_spec.name,
        is_present=True,
        variable_grades=variable_grades,
    )


def _merge_prose(
    section_spec: SectionSpec,
    results: dict[str, dict[str, Any]],
) -> SectionGrade:
    dimensions: dict[str, DimensionAssessment] = {}
    for d in DIMENSIONS:
        item = results.get(d, {})
        dimensions[d] = DimensionAssessment(
            verdict=item.get("verdict", INAPPLICABLE_VERDICT),
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


def _missing_section_grade(section_spec: SectionSpec) -> SectionGrade:
    return SectionGrade(
        section_name=section_spec.name,
        is_present=False,
        dimensions={
            "completeness": DimensionAssessment(
                verdict="critical",
                issues=["Section is missing."],
                recommendation=f"Add this section covering: {section_spec.description}",
            ),
            "adherence": DimensionAssessment(
                verdict="critical",
                issues=["Required section structure is absent."],
                recommendation=f"Add the required {section_spec.name} section.",
            ),
            "rigor": DimensionAssessment(verdict=INAPPLICABLE_VERDICT),
        },
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


def _image_inputs(blocks: list[ContentBlock]) -> list[dict[str, str]]:
    return [
        {"block_id": block.id, "data_url": block.image.data_url()}
        for block in blocks
        if block.image
    ]


def _verdict_value(value: Any) -> DimensionVerdict:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("verdict must be one of the closed verdict labels")
    verdict = value.strip().lower()
    if verdict not in DIMENSION_VERDICTS:
        raise ValueError(f"Unknown verdict label: {verdict}")
    return verdict  # type: ignore[return-value]


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

# Whole-doc context cap, in lockstep spirit with the other doc-reading stages so
# a long document never silently loses its tail in this pass.
MAX_DOC_CONTEXT_CHARS = 120000


def check_cross_section(
    labeled_blocks: list[ContentBlock],
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int,
) -> tuple[list[CrossSectionFinding], ConsistencyStatus]:
    """Find consistency problems that span MORE THAN ONE section.

    Per-section grading is deliberately isolated (a section never sees another),
    so it cannot catch "Section A targets >=80%, Section B says 90%". This pass
    sees every section together and reports only cross-section conflicts. It is
    an additive quality layer: a parse failure is returned explicitly as a
    failed status and never masquerades as a completed no-conflict result."""
    blocks_by_section = _group_blocks_by_section(labeled_blocks)
    if len(blocks_by_section) < 2:
        return [], "not_applicable"  # need two sections for a cross-section conflict

    system_prompt = build_cross_section_prompt(config)
    user_message, context_blocks_by_section, context_limited = _cross_section_user_message(
        blocks_by_section
    )

    context_blocks = [
        block
        for blocks in context_blocks_by_section.values()
        for block in blocks
    ]
    images = _image_inputs(context_blocks)
    schema = _cross_section_schema(context_blocks_by_section)
    findings = None
    for attempt in range(2):
        message = user_message
        if attempt:
            message += (
                "\n\nThe prior response failed the consistency contract. Return only "
                "cross-section conflicts with exact supplied section names and block IDs."
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
        f"You check a {config.intervention_class} product-development document for CROSS-SECTION "
        "consistency: places where TWO DIFFERENT sections state conflicting or mismatched "
        "claims about the SAME attribute - e.g. one section targets >=80% efficacy and "
        "another states 90%; the target population, dosing schedule, presentation, or "
        "timelines disagree between sections.\n\n"
        "Report ONLY conflicts that span more than one section. Do NOT report problems "
        "inside a single section, missing content, vague wording, or formatting - those are "
        "graded elsewhere. If there are no cross-section conflicts, return an empty array.\n\n"
        "Return only structured findings. Each item contains:\n"
        '{"description": "the specific conflicting values and what disagrees", '
        '"sections": ["Section A name", "Section B name"], '
        '"recommendation": "one short action to reconcile them", '
        '"block_ids": ["exact supporting block ID from each named section"]}\n\n'
        "Use only supplied section names and block IDs. Every finding must name at least "
        "two sections and cite at least one block from each named section."
    )


def _cross_section_schema(
    blocks_by_section: dict[str, list[ContentBlock]],
) -> dict[str, Any]:
    section_names = list(blocks_by_section)
    block_ids = [
        block.id for blocks in blocks_by_section.values() for block in blocks
    ]
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
                    "required": [
                        "description",
                        "sections",
                        "recommendation",
                        "block_ids",
                    ],
                    "properties": {
                        "description": {"type": "string"},
                        "sections": {
                            "type": "array",
                            "items": {"type": "string", "enum": section_names},
                        },
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

    Full documents are retained when they fit. For unusually large documents,
    each section receives an equal character budget and keeps blocks from both
    its beginning and end; the prompt states when coverage is partial.
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
        left = 0
        right = len(blocks) - 1
        used = 0
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
                used = per_section
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
) -> list[CrossSectionFinding] | None:
    if not isinstance(payload, dict):
        return None
    parsed = payload.get("findings")
    if not isinstance(parsed, list):
        return None
    allowed_sections = set(blocks_by_section)
    section_by_block_id = {
        block.id: section_name
        for section_name, blocks in blocks_by_section.items()
        for block in blocks
    }
    out: list[CrossSectionFinding] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        description = _string_value(item.get("description"))
        if not description:
            return None
        sections = list(dict.fromkeys(_string_list(item.get("sections"))))
        block_ids = list(dict.fromkeys(_string_list(item.get("block_ids"))))
        if (
            len(sections) < 2
            or any(section not in allowed_sections for section in sections)
            or not block_ids
            or any(block_id not in section_by_block_id for block_id in block_ids)
            or any(
                not any(section_by_block_id[block_id] == section for block_id in block_ids)
                for section in sections
            )
        ):
            return None
        out.append(
            CrossSectionFinding(
                description=description,
                sections=sections,
                recommendation=_string_value(item.get("recommendation")),
                block_ids=block_ids,
            )
        )
    return out
