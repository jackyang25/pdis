"""Opt-in live Screener scope regression; uses synthetic sources only.

Run with configured provider credentials: python -m scripts.check_screener_relevance
This is deliberately outside pytest: a stub cannot test model interpretation.
"""
from __future__ import annotations

from services.chunker import ContentBlock
from services.screener import QuestionSpec
from services.screener.stages.assessor import assess_question
from services.screener.stages.selector import select_evidence
from shared.openai_client import OpenAIClient


def source(doc: str, text: str, index: int = 1) -> ContentBlock:
    return ContentBlock(f"{doc}:{index}", doc, index - 1, "paragraph", text, [], {}, {})


def main() -> None:
    plan = QuestionSpec("Q1", "Is a launch and uptake strategy planned?", requirement="required")
    background = QuestionSpec(
        "Q2", "Have relevant delivery approaches from comparator programs been assessed?",
        requirement="required",
    )
    partial = QuestionSpec(
        "Q3", "Are the following planned: launch strategy and manufacturing scale-up?",
        requirement="required",
    )
    unrelated = source("other", "Candidate B is an HIV drug. Its launch and uptake strategy "
                       "targets clinics in first-wave countries, with adherence support. "
                       "Its manufacturing scale-up is planned for next year.")
    matched = source("review", "Candidate A is a drug for respiratory syncytial virus. "
                     "Its launch and uptake strategy is planned through pediatric clinics "
                     "in first-wave countries with caregiver support.")
    support = source("support", "Candidate A's respiratory syncytial virus drug program assessed "
                     "clinic delivery approaches from Candidate B's HIV program as comparators. "
                     "The assessment found appointment reminders transferable to caregiver visits, "
                     "but adult adherence counseling unsuitable for this population.")
    identity = source("identity", "Candidate D is a drug for respiratory syncytial virus.")
    launch = source("identity", "Candidate D's launch and uptake strategy is planned via "
                    "pediatric clinics and caregiver support.", 2)
    manufacturing = source("manufacturing", "Candidate D's manufacturing scale-up is planned "
                           "for next year, expanding production to two additional sites.")
    cases = [
        ("mismatched plan", plan, [[unrelated]], "not_found", set()),
        ("matched plan", plan, [[matched]], "answered", {"review:1"}),
        ("mixed plans", plan, [[matched], [unrelated]], "answered", {"review:1"}),
        ("applicable comparator", background, [[support]], "answered", {"support:1"}),
        ("partial not filled by unrelated program", partial, [[matched], [unrelated]],
         "partly_answered", {"review:1"}),
        ("ambiguous subject", plan, [[source("unknown", "Launch and uptake are planned via clinics. "
                                           "The product and indication are not identified.")]],
         "not_found", set()),
        ("other disease mismatch", plan,
         [[source("malaria", "Candidate C is a malaria drug with a launch and uptake "
                              "strategy planned through community clinics.")]],
         "not_found", set()),
        ("identity separate from plan", plan, [[identity, launch]],
         "answered", {"identity:1", "identity:2"}),
        ("complementary documents", partial, [[identity, launch], [manufacturing]],
         "answered", {"identity:1", "identity:2", "manufacturing:1"}),
        ("complementary documents with unrelated plan", partial,
         [[identity, launch], [manufacturing], [unrelated]],
         "answered", {"identity:1", "identity:2", "manufacturing:1"}),
    ]
    client = OpenAIClient()
    failures = []
    for name, question, documents, state, citations in cases:
        selected = []
        for document in documents:
            selected.extend(select_evidence(
                question, document, indication="respiratory_syncytial_virus",
                intervention_class="drug", llm_client=client, max_tokens=4000,
            ))
        result = assess_question(
            question, blocks=selected, indication="respiratory_syncytial_virus",
            intervention_class="drug", llm_client=client, max_tokens=4000,
        )
        passed = result.state == state and set(result.cited_block_ids) == citations
        if not passed:
            failures.append(name)
        print(f"{'PASS' if passed else 'FAIL'} {name}: {result.state}; "
              f"citations={result.cited_block_ids}; {result.statement}", flush=True)
    if failures:
        raise SystemExit(f"Failed scope cases: {', '.join(failures)}")


if __name__ == "__main__":
    main()
