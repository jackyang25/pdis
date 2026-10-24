"""Stage: decide which program and product names in the projections denote one thing.

The development landscape groups records by program and the safety view by product, and
the names arrive as each provider wrote them: a registry's code name, a regulator's
brand name, a press release's description. Whether "RSVpreF", "Abrysvo" and "RSVpreF
vaccine" are one programme is an identity decision, and identity is a model layer of its
own - grouping by a case-folded string merged nothing those three share and would merge
two products that happened to differ only in case.

One request over every distinct name, because the answer is a partition of that set
(AGENTS: a request carries several items when its answer is about the set). The model
may only group the supplied names and pick one as the group's display name; it never
writes a name. A partition that fails leaves every name its own group and is recorded.
"""

from __future__ import annotations

import json
from typing import Mapping

from services.searcher import Finding
from shared.ai import Effort, ModelTask

from ..ai_contracts import projection_reconciliation
from ..identity import partition
from ..models import IdentityReconciliation, LLMClientProtocol
from ..projections import projection_names

#: The whole set of names in one request: the answer is a partition of that set.
NAME_SETS_PER_REQUEST = 1
#: The reasoning tier at low effort: telling a code name from its brand name takes
#: knowledge of the products, and the call runs once per run.
TASK: ModelTask = "reasoning"
EFFORT: Effort = "low"
#: The reply is IDs only; the rest is reasoning room for a long list.
MAX_TOKENS = 16000


def build_system_prompt() -> str:
    return (
        "ROLE\n"
        "You decide which supplied names denote the same product or development "
        "programme. Partition the supplied name IDs and choose an existing member as each "
        "group's representative. You cannot write, shorten or correct a name.\n\n"
        "IDENTITY RULE\n"
        "Group names only when they denote one product or one programme: a development "
        "code and the brand or nonproprietary name it was licensed under, the same name "
        "written in different case, spacing or punctuation, or a name with and without "
        "its sponsor or dosage-form suffix. Keep different products separate even when "
        "they share a sponsor, a target, a platform or a disease; keep a combination "
        "product apart from its components, and a product apart from the class it belongs "
        "to. Each name lists the record types and sponsors it was stated with; use them to "
        "tell products apart, never as a reason to merge. When unsure, keep names apart.\n\n"
        "REPRESENTATIVE\n"
        "Choose the member a reader would recognise the product by: its nonproprietary or "
        "brand name where one is in the group, otherwise its development code.\n\n"
        "OUTPUT\n"
        "Return every supplied name ID exactly once across all groups, including singleton "
        "groups, each representative listed among its own members. Return only the "
        "schema-bound groups."
    )


def reconcile_projection_names(
    findings_by_attribute: Mapping[str, list[Finding]],
    llm_client: LLMClientProtocol,
    *,
    max_tokens: int = MAX_TOKENS,
) -> tuple[dict[str, str], IdentityReconciliation | None]:
    """Map each stated name to the name its group is shown under, and the record.

    Fewer than two names needs no call and records nothing.
    """
    names = projection_names(findings_by_attribute)
    if len(names) < 2:
        return {name: name for name in names}, None
    ids = [f"name-{index}" for index in range(len(names))]
    by_id = dict(zip(ids, names))
    context = _name_context(findings_by_attribute)
    payload = json.dumps(
        [
            {"name_id": name_id, "name": name, **context.get(name, {})}
            for name_id, name in by_id.items()
        ],
        ensure_ascii=False,
    )
    result = partition(
        llm_client,
        projection_reconciliation(ids),
        build_system_prompt(),
        payload,
        ids=ids,
        representative_key="representative_name_id",
        members_key="member_name_ids",
        layer="projections",
        max_tokens=max_tokens,
        task=TASK,
        effort=EFFORT,
    )
    return {
        by_id[member]: by_id[representative]
        for representative, members in result.groups
        for member in members
    }, result.record


def _name_context(
    findings_by_attribute: Mapping[str, list[Finding]],
) -> dict[str, dict[str, list[str]]]:
    """What each name was stated with: record types and sponsors, as providers gave them."""
    context: dict[str, dict[str, list[str]]] = {}
    for findings in findings_by_attribute.values():
        for finding in findings:
            for record in finding.development_records:
                entry = context.setdefault(record.program_name.strip(), {"stated_in": [], "sponsors": []})
                _add(entry["stated_in"], record.record_type)
                _add(entry["sponsors"], record.sponsor.strip())
            for observation in finding.safety_observations:
                entry = context.setdefault(observation.product_name.strip(), {"stated_in": [], "sponsors": []})
                _add(entry["stated_in"], observation.source_system)
    return context


def _add(values: list[str], value: str) -> None:
    if value and value not in values and len(values) < 5:
        values.append(value)
