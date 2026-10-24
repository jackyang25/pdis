"""Ask one question per rubric unit, and read findings off the answer.

One schema-bound call per unit: "what is wrong with this, and why". That replaced
three calls per unit, one for completeness, adherence, and rigor. Three calls cost
three times the requests for a 26-unit rubric and could each report the same defect
under its own axis, so a funding disclaimer sitting where an introduction belongs
was simultaneously incomplete, off-template, and weak.

Merging them also removed the naming problem that split created: the same axis was
`adherence` in the data and "Template adherence" in two interfaces, while
completeness escaped it only because its key happened to read well.

All rubric units share one bounded worker pool per document run. Rubrics remain
independent requests; scheduling never changes their evidence or authored order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import zip_longest
from typing import Any, NamedTuple

from shared.ai import (
    RECORDABLE_FAILURES,
    Effort,
    FailureCode,
    ModelTask,
    failure_code,
    request_validated,
)
from shared.batching import map_ordered
from shared.references import reference_array
from shared.request_budget import check_request
from shared.schemas import non_empty_text
from shared.source_blocks import image_inputs, render_block, render_blocks
from shared.vocabulary import search_term

from services.chunker import ContentBlock

from ..assembly import absent_unit_assessments, unit_id
from ..source_context import with_slide_overviews
from ..models import (
    ASSESSED_VERDICTS,
    UNCITED_VERDICTS,
    UNIT_VERDICTS,
    Assessment,
    ConsistencyStatus,
    InspectionConfig,
    LLMClientProtocol,
    SectionSpec,
    VariableSpec,
)

# One assessment per rubric unit, so an unrelated unit can never sit in this
# decision's prompt. Throughput comes from fan-out, never from packing units.
UNITS_PER_REQUEST = 1
#: The reasoning tier: a verdict is a judgement of coverage against usability, the one
#: boundary readers and models most often get wrong.
UNIT_TASK: ModelTask = "reasoning"
#: Low: one unit against its own section, answered in one closed verdict and a sentence
#: of at most 20 words. The rubric's expectations and the boundary note carry the
#: judgement; more effort spent the budget re-reading the section.
UNIT_EFFORT: Effort = "low"
#: The answer is under a hundred tokens; the rest is reasoning room. A unit cut off at it
#: is asked again with twice the room (`shared.ai.after_truncation`). The route used to
#: send 32000 for a three-field verdict.
UNIT_MAX_TOKENS = 8000
# Preserve the former upper bound (4 section pools × 6 unit calls), now across
# ALL included rubrics rather than multiplying pools as rubrics are added.
MAX_PARALLEL_UNIT_CALLS = 24

# What each verdict is for, stated once and rendered into the prompt. Adding one
# means adding it here and to `VERDICTS`; nothing between this module and the
# interface needs to know.
_VERDICT_GUIDANCE: tuple[tuple[str, str], ...] = (
    ("specified", "the rubric asks for this and the document supplies it usably. Nothing to say."),
    (
        "not_present",
        "there is no content at all for this unit. Use this only where the rubric asks "
        "for it; where the rubric marks the unit optional, absence is not_applicable.",
    ),
    ("placeholder", "a template token such as <<TBD>>, TBD, a dash, or a blank sits where the value belongs."),
    (
        "insufficient",
        "content is present but does not cover what the requirement asks for - part of "
        "it is answered and part is not. For example only one of Minimum/Optimistic is "
        "filled, or a category label stands in for a value.",
    ),
    (
        "vague",
        "content is present and covers what the requirement asks for, but is unusable "
        "as stated - unmeasurable, self-contradictory, or too general to act on.",
    ),
    ("not_applicable", "the rubric marks this optional and the document omits it."),
)

# `insufficient` and `vague` are the pair readers and models most often confuse, so
# the boundary is stated rather than left to be inferred from two adjectives:
# coverage versus usability. Insufficient is "some of what was asked for is not
# there"; vague is "all of it is there and none of it can be acted on". A unit that
# is both is `insufficient`, because a gap outranks a weakness - which is also the
# published order of the two.
_BOUNDARY_NOTE = (
    "insufficient and vague are not degrees of each other. Ask coverage first: is any "
    "part of what the requirement asks for absent? If yes, insufficient. Only if the "
    "content covers the whole requirement and is still unusable as stated is it vague. "
    "A unit that is both is insufficient."
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _UnitWork:
    rubric_index: int
    section: SectionSpec
    unit: VariableSpec | None
    blocks: list[ContentBlock]
    blocks_text: str
    stage_guidance: str
    context: str
    absent: Assessment | None = None


def assess_rubrics(
    labeled_blocks: list[ContentBlock],
    configs: list[InspectionConfig],
    llm_client: LLMClientProtocol,
    *,
    indication: str | None = None,
    progress=None,
) -> list[tuple[list[Assessment], dict[str, list[str]]]]:
    """Assess independent units with one run-wide limit and progress counter.

    Results retain rubric/section/unit order regardless of completion order.
    Each rubric retains its own evidence mapping; whole-document topics never
    become physical section mappings. A failed unit raises instead of returning
    a partial collection. Every distinct request is measured against the request
    budget before any unit is sent.
    """
    grouped = _group_blocks_by_section(labeled_blocks)
    section_context = {
        name: with_slide_overviews(blocks, labeled_blocks)
        for name, blocks in grouped.items()
    }
    section_text = {name: _format_blocks(blocks) for name, blocks in section_context.items()}
    whole_text = (
        _format_blocks(labeled_blocks)
        if any(config.evidence_scope == "whole_document" for config in configs)
        else ""
    )
    checked: set[str | None] = set()
    plans: list[list[_UnitWork]] = []
    results: list[tuple[list[Assessment], dict[str, list[str]]]] = []
    for index, config in enumerate(configs):
        if config.evidence_scope not in {"mapped_section", "whole_document"}:
            raise ValueError(f"unknown Inspector evidence scope: {config.evidence_scope}")
        whole_document = config.evidence_scope == "whole_document"
        work: list[_UnitWork] = []
        mapped: dict[str, list[str]] = {}
        for section in config.sections:
            blocks = labeled_blocks if whole_document else section_context.get(section.name, [])
            text = whole_text if whole_document else section_text.get(section.name, "")
            mapped[section.name] = [] if whole_document else [
                block.id for block in grouped.get(section.name, [])
            ]
            units = section.variables or [None]
            absent = absent_unit_assessments(config, section.name) if not blocks else []
            # Measured once per distinct request, before any unit is sent.
            scope = None if whole_document else section.name
            if blocks and scope not in checked:
                checked.add(scope)
                check_request(
                    f"Inspector's {'whole-document review' if scope is None else scope + ' section'}",
                    text=text, images=image_inputs(blocks),
                )
            context = review_context(config, indication)
            for unit_index, unit in enumerate(units):
                work.append(_UnitWork(
                    index, section, unit, blocks, text, config.stage_guidance, context,
                    absent[unit_index] if absent else None,
                ))
        plans.append(work)
        results.append(([], mapped))

    # Interleave rubrics so a large template does not queue every guideline behind
    # itself. This changes submission order only, never request contents or ranking.
    tasks = [task for row in zip_longest(*plans) for task in row if task is not None]
    if progress:
        progress("assess", completed=0, total=len(tasks))

    def run(task: _UnitWork) -> Assessment:
        if task.absent is not None:
            return task.absent
        return _assess_unit(
            section_spec=task.section, unit=task.unit,
            blocks_text=task.blocks_text, section_blocks=task.blocks,
            llm_client=llm_client, stage_guidance=task.stage_guidance,
            context=task.context,
        )

    assessed = map_ordered(
        tasks, run, workers=MAX_PARALLEL_UNIT_CALLS,
        on_progress=(
            (lambda done, total: progress("assess", completed=done, total=total))
            if progress else None
        ),
    )
    for task, assessment in zip(tasks, assessed):
        results[task.rubric_index][0].append(assessment)
    return results


def _assess_unit(
    *,
    section_spec: SectionSpec,
    unit: VariableSpec | None,
    blocks_text: str,
    section_blocks: list[ContentBlock],
    llm_client: LLMClientProtocol,
    stage_guidance: str = "",
    context: str = "",
) -> Assessment:
    """Build one schema-bound decision for one unit and validate its lineage.

    One call means the answer needs no unit name: this function already knows which
    unit it asked about. The accounting that a three-call shape needed - every
    expected name present exactly once - goes away with it.
    """
    system_prompt = build_assessment_prompt(stage_guidance)
    unit_name = unit.name if unit else None
    optional = section_spec.optional or bool(unit and unit.optional)
    schema = assessment_schema(section_blocks, optional=optional)
    images = image_inputs(section_blocks)

    def parse(payload: dict[str, Any] | None) -> Assessment:
        if payload is None:
            raise ValueError("model returned no structured decision")
        return _parse_unit_payload(
            payload,
            section_name=section_spec.name,
            variable_name=unit_name,
            optional=optional,
            section_blocks=section_blocks,
        )

    # The section's blocks and images lead, identical for every unit of the section;
    # the unit being asked about follows them, so the shared prefix stays reusable.
    return request_validated(
        llm_client,
        system_prompt,
        _build_user_message(blocks_text, context),
        trailing_text=unit_request(section_spec, unit),
        max_tokens=UNIT_MAX_TOKENS,
        task=UNIT_TASK,
        effort=UNIT_EFFORT,
        schema_name="inspector_unit_assessment",
        schema=schema,
        images=images or None,
        parse=parse,
        failure=(
            f"Inspector could not assess {unit_name or section_spec.name} "
            f"in {section_spec.name}"
        ),
        repair=lambda error: (
            "\n\nThe prior decision failed the Inspector contract: "
            f"{error}. Return exactly one verdict, and cite the exact "
            "supplied block IDs unless the unit is absent."
        ),
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_assessment_prompt(stage_guidance: str = "") -> str:
    """The unit-assessment system prompt: fixed for a rubric, whatever the unit.

    The unit being asked about travels in the user message (`unit_request`), after
    the section's content, so every request for one rubric shares this prompt.
    """
    verdicts = "\n".join(f"- {verdict}: {text}" for verdict, text in _VERDICT_GUIDANCE)
    preamble = f"""You are inspecting one unit of a product-development document against its authored rubric.

Scope boundary:
- Judge the quality and usability of what the document states; do not assess real-world program feasibility or investment merit.
- If the rubric expects risks, judge whether the document identifies, rates, and mitigates them. Do not independently assign program risk levels.
- Do not recommend funding decisions, prioritize an investment portfolio, or propose organizational support.
- Do not assume external facts or evidence that are absent from the supplied document and rubric.

Return exactly one verdict for this unit. One question, one answer: if more than one
label could apply, choose the one that names the unit's condition best. They are
listed worst-first, so prefer the earlier of two that fit equally.

Verdicts:
{verdicts}

{_BOUNDARY_NOTE}

Do not judge structure or naming on its own. Whether a heading, a column, or a label
matches the template is not a verdict here. If the layout costs a reader something -
a value that cannot be found, or a requirement left half-answered because a column is
absent - report that as insufficient or vague on its own merits. If it costs them
nothing, it is not a finding.

Lineage is required, not optional. Every verdict except `not_present` and
`not_applicable` MUST cite in `block_ids` the exact blocks you read to reach it -
including `specified`, which is a claim about content you saw.

Describe the document; do not direct the reader. State what is or is not there, not
what must be done about it: a reader who knows a value is missing knows to add it.

Style:
- `statement` is one short factual sentence (max 20 words) naming the problem.
- Leave `statement` empty for `specified` and `not_applicable`. There is nothing wrong
  to describe, and a sentence there would be a claim with no defect behind it.
- Do not repeat the unit's name in it. Do not hedge."""

    parts = [preamble]
    if stage_guidance.strip():
        parts.append("# ASSESSMENT BAR (document stage)\n" + stage_guidance.strip())
    return "\n\n".join(parts)


def unit_request(section_spec: SectionSpec, unit: VariableSpec | None = None) -> str:
    """The one unit a request asks about: its name, its section, its expectations."""
    subject = unit.name if unit else section_spec.name
    return "\n\n".join([
        f"Assess: {subject}",
        f"Section: {section_spec.name}",
        _expectations_block(section_spec, unit),
    ])


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


def offered_verdicts(optional: bool) -> tuple[str, ...]:
    """The verdicts one unit may receive. Absence has one name, and the rubric picks it.

    A required unit that is absent is `not_present`; an optional one is `not_applicable`.
    Offering both let the model file an optional absence as a shortfall, or a required one
    as acceptable, and the parser had to correct one direction and refuse the other.
    """
    excluded = "not_present" if optional else "not_applicable"
    return tuple(verdict for verdict in UNIT_VERDICTS if verdict != excluded)


def assessment_schema(section_blocks: list[ContentBlock], *, optional: bool = False) -> dict[str, Any]:
    """The closed shape one unit's answer must take."""
    return {
        "type": "object",
        "additionalProperties": False,
        # One object, not an array of them. The array let a unit come back with
        # several answers to one question, and every layer above had to decide which
        # of them the unit was.
        "required": ["verdict", "statement", "block_ids"],
        "properties": {
            "verdict": {"type": "string", "enum": list(offered_verdicts(optional))},
            # Empty on a sound unit and written on a defective one. A conditional
            # requirement is the one thing this schema cannot say, so the verdict
            # carries the condition and the parser checks the pairing.
            "statement": {"type": "string"},
            "block_ids": reference_array([block.id for block in section_blocks]),
        },
    }


def review_context(config: InspectionConfig, indication: str | None) -> str:
    """What the document is about, as the user selected it. Context, never evidence.

    The same for every unit of a run, so it leads the shared prefix. A rubric unit about
    the target population or dosing is read against the disease it is for.
    """
    lines = ["Review context (user-selected, not evidence):",
             f"Intervention class: {config.intervention_term}"]
    if indication:
        lines.append(f"Disease / condition: {search_term(indication)}")
    return "\n".join(lines)


def _build_user_message(blocks_text: str, context: str = "") -> str:
    return "\n\n".join(part for part in (
        context, "Actual document blocks for this section:", blocks_text,
    ) if part)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_unit_payload(
    parsed: object,
    *,
    section_name: str,
    variable_name: str | None,
    optional: bool,
    section_blocks: list[ContentBlock],
) -> Assessment:
    if not isinstance(parsed, dict):
        raise ValueError("assessment response must be an object")

    valid_block_ids = {block.id for block in section_blocks}
    subject = variable_name or section_name

    verdict = _closed_value(parsed.get("verdict"), set(offered_verdicts(optional)), "verdict")
    statement = _string_value(parsed.get("statement"))
    block_ids = list(dict.fromkeys(_string_list(parsed.get("block_ids"))))
    if any(block_id not in valid_block_ids for block_id in block_ids):
        raise ValueError(f"{subject} cited an unknown block ID")

    # Presence and lineage have to agree, and the rule is the same everywhere:
    # absence cites nothing and everything else cites something.
    if verdict in UNCITED_VERDICTS:
        block_ids = []
    elif not block_ids:
        raise ValueError(f"{subject} returned {verdict} without citing a block")

    # A verdict with nothing wrong has nothing to say, and one with something wrong
    # has to say it. Normalised here rather than refused, because a model adding
    # "Specified." to a sound unit is not a contract failure worth a retry.
    if verdict not in ASSESSED_VERDICTS:
        statement = ""
    elif not statement:
        raise ValueError(f"{subject} returned {verdict} with no statement")

    # The rubric decides what absence means, not the model: `offered_verdicts` gives an
    # optional unit `not_applicable` and a required one `not_present`, never both, so
    # the closed value above already refused the other.
    return Assessment(
        id=unit_id(section_name, variable_name),
        verdict=verdict,  # type: ignore[arg-type]
        statement=statement,
        section_name=section_name,
        variable_name=variable_name,
        optional=optional,
        cited_block_ids=block_ids,
    )


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
    return render_blocks(blocks)


def _format_block(block: ContentBlock) -> str:
    return render_block(block)


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

#: One request for the whole document: whether two sections disagree is a statement
#: about the set of sections, the case the one-item-per-request rule exempts.
DOCUMENTS_PER_REQUEST = 1
#: The reasoning tier at medium effort: the pass compares every section against every
#: other for the same attribute, which is the most reading any Inspector call does.
CONSISTENCY_TASK: ModelTask = "reasoning"
CONSISTENCY_EFFORT: Effort = "medium"
#: Findings are few and short; the budget is reasoning room over up to 120k characters.
CONSISTENCY_MAX_TOKENS = 16000


class ConsistencyCheck(NamedTuple):
    """The consistency pass's findings and the process facts about the pass itself."""

    findings: list[Assessment]
    status: ConsistencyStatus
    failure_code: FailureCode | None = None
    """Why the pass failed, from `shared.ai.FAILURE_CODES`; set exactly when failed."""


def check_cross_section(
    labeled_blocks: list[ContentBlock],
    config: InspectionConfig,
    llm_client: LLMClientProtocol,
) -> ConsistencyCheck:
    """Find consistency problems that span MORE THAN ONE section.

    Per-unit assessment is deliberately isolated, so it cannot catch "Section A
    targets >=80%, Section B says 90%". This pass sees every section together and
    reports conflicts as ordinary findings under the `section_conflict` verdict. It
    is an additive layer that runs after every unit is assessed, so its failure - an
    answer that stayed invalid or was cut off - is recorded as a failed status with
    its code and never discards the assessment, nor masquerades as a completed
    no-conflict result.
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
        # Two sections are needed for a cross-section conflict.
        return ConsistencyCheck([], "not_applicable")

    system_prompt = build_cross_section_prompt(config)
    user_message, context_blocks_by_section, context_limited = _cross_section_user_message(
        blocks_by_section
    )
    context_blocks = [b for blocks in context_blocks_by_section.values() for b in blocks]
    schema = cross_section_schema(context_blocks_by_section)
    images = image_inputs(context_blocks)
    check_request("Inspector's consistency check", text=user_message, images=images)

    try:
        findings = request_validated(
            llm_client,
            system_prompt,
            user_message,
            max_tokens=CONSISTENCY_MAX_TOKENS,
            task=CONSISTENCY_TASK,
            effort=CONSISTENCY_EFFORT,
            schema_name="inspector_cross_section_consistency",
            schema=schema,
            images=images or None,
            parse=lambda payload: _parse_cross_section_payload(
                payload, context_blocks_by_section,
            ),
            failure="Inspector could not check cross-section consistency",
            repair=lambda error: (
                f"\n\nThe prior response failed the consistency contract: {error}. Return "
                "only cross-section conflicts, each citing exact supplied block IDs from at "
                "least two different sections."
            ),
        )
    except RECORDABLE_FAILURES as exc:
        return ConsistencyCheck([], "failed", failure_code(exc))
    return ConsistencyCheck(findings, "partial" if context_limited else "complete")


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
                    "required": ["statement", "block_ids"],
                    "properties": {
                        "statement": non_empty_text(),
                        # Two blocks at least: a conflict cites each of the two or
                        # more sections that disagree.
                        "block_ids": {**reference_array(block_ids), "minItems": 2},
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
) -> list[Assessment]:
    """Validate one consistency answer, raising ``ValueError`` naming what is wrong."""
    if not isinstance(payload, dict):
        raise ValueError("model returned no structured decision")
    parsed = payload.get("findings")
    if not isinstance(parsed, list):
        raise ValueError("findings must be an array")
    section_by_block_id = {
        block.id: section_name
        for section_name, blocks in blocks_by_section.items()
        for block in blocks
    }
    out: list[Assessment] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError("each finding must be an object")
        statement = _string_value(item.get("statement"))
        block_ids = list(dict.fromkeys(_string_list(item.get("block_ids"))))
        if not statement or not block_ids:
            raise ValueError("each finding needs a statement and cited blocks")
        if any(block_id not in section_by_block_id for block_id in block_ids):
            raise ValueError("a finding cited an unknown block ID")
        # The citations decide whether this is cross-section, so the sections are
        # read back from them rather than asked for and then checked against them.
        if len({section_by_block_id[block_id] for block_id in block_ids}) < 2:
            raise ValueError("a finding must cite blocks from two different sections")
        out.append(
            Assessment(
                id=f"conflict|{index}",
                verdict="section_conflict",
                statement=statement,
                cited_block_ids=block_ids,
            )
        )
    return out
