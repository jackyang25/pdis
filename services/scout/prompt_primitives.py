"""Shared semantic vocabulary for Scout's schema-bound model stages.

These strings define meaning only. Each stage keeps its own task, authority,
schema, and output rules; importing a primitive prevents those stages from
quietly redefining the same concept in different prose.
"""

CANONICAL_CLAIM_PRIMITIVE = (
    "A canonical claim is one document-authored assertion with exact source lineage. "
    "It is not a summary, downstream implication, neighboring table value, template prompt, "
    "or fact supplied by background knowledge. Preserve every qualifier that changes the "
    "assertion's meaning, including population, intervention, endpoint, regimen, time, and "
    "conditions. Fields are views of claims; a field label does not create, duplicate, or "
    "rewrite a claim."
)

NUMERIC_DISPLAY_PRIMITIVE = (
    "Numeric expression display metadata changes presentation only. Set display.kind to "
    "calendar_year only for an explicitly stated calendar year, never for a duration or "
    "because a number has four digits; otherwise use quantity. Supply unit_singular and "
    "unit_plural as grammatical forms of the same expression unit without converting it. "
    "For invariant symbols such as % or mL, use the same form for both. For a calendar year "
    "leave both forms empty. Do not change the numeric value, comparator, or calculation unit "
    "to improve display."
)

ATOMIC_TARGET_PRIMITIVE = (
    "An atomic target is one independently testable document commitment expressed as one "
    "measure plus one directional or exact scalar and its material qualifiers. Split a source "
    "statement only when it contains independently testable commitments. Keep a numeric "
    "qualifier attached to the claim it qualifies; do not promote an example, background fact, "
    "rejected alternative, study-design detail, or contextual number into a separate target."
)

SEMANTIC_DIMENSIONS_PRIMITIVE = (
    "Use semantic dimensions consistently: measure is the exact construct represented by the "
    "number; endpoint is the event or outcome measured; intervention is what is administered, "
    "built, or evaluated; population is who or what the result describes; regimen is the dose, "
    "schedule, configuration, or operating pattern; time_horizon is when or for how long; "
    "statistic is the reported estimand or summary form. Conditions includes only settings or "
    "circumstances that change numeric interpretation and are not already represented by another "
    "dimension; minimum/optimal ambition belongs in target role, not conditions. Shared numbers or units do not make two measures the "
    "same. Record only meaning supported by the supplied context, and preserve genuine absence "
    "or ambiguity rather than filling it from background knowledge."
)

COMPARATOR_POLICY_PRIMITIVE = (
    "COMPARISON POLICY\n"
    "Separate three things: the semantic profile describes the document requirement; the numeric "
    "expression and role specify the value to test; comparison_contract specifies which external "
    "measurements can answer that test. Comparability precedes evaluation of the value.\n"
    "Measured value: never require evidence to repeat the target's number, bound, deadline, or "
    "minimum/optimal role. If a semantic dimension only restates that value or role, its comparison "
    "rule is unconstrained. A milestone year or duration being measured may differ from the target; "
    "a fixed observation window for measuring another quantity remains a material qualifier. "
    "If a dimension contains both, constrain only the independent qualifier, not the tested value.\n"
    "Matching rules: exact requires the same measurement meaning, not identical wording or equal "
    "numeric outcomes; measure is always exact by construct, not merely by unit. Compatible permits "
    "only variation within a stated, justified scope that preserves interpretation. Unconstrained "
    "means the dimension does not control admission; unknown means its required scope cannot be "
    "established. Missing support for a required qualifier stays unknown, never unconstrained.\n"
    "Scope authority: preserve material endpoint definitions, populations, regimens, observation "
    "windows, statistical forms, and operating conditions. Do not widen them merely because two "
    "document targets or columns differ, because evidence is scarce, or because two outcomes are "
    "related. A named candidate is not automatically an exact-identity requirement; a broader "
    "class comparison needs support in the supplied context. For each rule, explain the specific "
    "difference that would change interpretation or why the allowed variation would not. Avoid "
    "generic reasons such as 'identity is fixed by construct'. Favorability and pass/fail never "
    "determine comparability."
)

EVIDENCE_UNIT_PRIMITIVE = (
    "An evidence unit is the smallest independent source-owned population, arm, cohort, specimen "
    "set, or other observation unit that may contribute once to statistics. Repeated statements, "
    "alternative estimates, timepoints, endpoints, analyses, and nested subgroups from the same "
    "underlying unit remain one review choice unless the source explicitly establishes mutually "
    "exclusive, non-overlapping units. Source records and numeric statements are provenance "
    "containers, not automatic proof of statistical independence."
)

RELATIONSHIP_PRIMITIVE = (
    "Classify the logical relationship to the document claim, not the desirability of the result. "
    "Contradiction requires propositions that cannot both be true within the claim's subject, "
    "time, conditions, and scope. A failure must concern the asserted endpoint or commitment; "
    "sharing a candidate name alone does not make every failure a contradiction. "
    "A target specifies the intended product, not what every other product must be. An alternative "
    "design can coexist with that target even when it would not meet the specification itself. "
    "A different comparator value, including a "
    "stricter or looser benchmark, can coexist with the document target and is not by itself a "
    "contradiction. Confirmation requires direct support for the claim; evidence that merely "
    "explains the need for the target adds context instead. Missing confirmation in retrieved "
    "material is not evidence that the document claim is false. Distinguish search silence "
    "from an explicit source-owned negative finding, and compare the latter within its stated "
    "subject, time, and scope."
    " Compare the exact property asserted: novelty or difference in one component does not "
    "establish a prohibited property in another. Do not infer equivalence of components, "
    "mechanisms, or categories without evidence establishing the connection. A missing property "
    "neither proves its absence nor its presence. On-topic evidence that leaves this connection "
    "unestablished adds context rather than confirming or contradicting the claim. "
    "Preserve quantifiers: a counterexample can refute an explicit universal or exclusivity "
    "claim, but a product target must not be silently expanded into such a claim."
)
