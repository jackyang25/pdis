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
    "dimension. Shared numbers or units do not make two measures the "
    "same. Record only meaning supported by the supplied context, and preserve genuine absence "
    "or ambiguity rather than filling it from background knowledge."
)

COMPARATOR_POLICY_PRIMITIVE = (
    "The semantic profile records what the document says; populate comparison_contract separately "
    "to record "
    "what external evidence may vary while still measuring the same target: exact requires the "
    "same entity-level meaning; compatible permits variation only inside its stated scope; "
    "unconstrained means that dimension does not control admission; mode=unknown preserves genuine "
    "ambiguity for review. A dimension is constraining only when changing it could change whether the "
    "external value answers the target. Mere mention elsewhere in the document does not make it "
    "constraining. Measure is always exact by construct, not merely by unit. A named document "
    "candidate is not automatically an exact-identity requirement. Target magnitude, pass/fail, "
    "and whether a result is favorable never determine comparability."
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
    "Contradiction requires propositions that cannot both be true, or direct evidence that the same "
    "candidate, configuration, or factual claim failed. A different comparator value, including a "
    "stricter or looser benchmark, can coexist with the document target and is not by itself a "
    "contradiction. Confirmation requires direct support for the claim; evidence that merely "
    "explains the need for the target adds context instead."
)
