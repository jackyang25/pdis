/**
 * Two comparisons meet at the document they share, and only there.
 *
 * The situation these tests are about: a plan that faithfully delivers a commitment
 * which itself falls short of the profile. Every verdict involved is correct, and the
 * second comparison alone reads as good news, so the link is the only thing that makes
 * it visible.
 *
 * What they mostly guard is the opposite — that nothing is linked on a guess. The join
 * is a block id and nothing else: no requirement-text matching, no document-type
 * assumptions, no inference about which clause of a passage each side meant.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { AlignmentFinding, AlignmentResult, AlignmentVerdict , DocumentSpan} from "./api.ts";
import { chainWarningText, chainWarnings } from "./aligner-chain.ts";

/** One cited passage. The chain pairs on blocks, so only the block ID has to be real. */
function cite(blockId: string): DocumentSpan {
  return { quote: `Content of ${blockId}.`, block_ids: [blockId] };
}

function finding(
  overrides: Partial<AlignmentFinding> & Pick<AlignmentFinding, "requirement_id" | "edge_id" | "verdict">,
): AlignmentFinding {
  return {
    requirement: `Requirement ${overrides.requirement_id}`,
    reference_spans: [],
    statement: "The document states something.",
    comparison_spans: [],
    ...overrides,
  };
}

/**
 * The three-document chain: profile → candidate → plan.
 *
 * `shared` is the candidate passage both comparisons cite — the first as where the
 * candidate falls short, the second as where the candidate commits.
 */
function chain(
  {
    upstreamVerdict = "falls_short" as AlignmentVerdict,
    upstreamBlocks = ["candidate/b-0042"],
    downstreamBlocks = ["candidate/b-0042"],
    downstreamVerdict = "meets" as AlignmentVerdict,
    gap = "Annual dosing against six-monthly offered.",
  } = {},
): AlignmentResult {
  return {
    documents: [
      { doc_id: "profile", source_type: "itpp", display_name: "iTPP" },
      { doc_id: "candidate", source_type: "ctpp", display_name: "cTPP" },
      { doc_id: "plan", source_type: "ipdp", display_name: "IPDP" },
    ],
    edges: [
      {
        edge_id: "itpp-to-ctpp",
        reference_doc_id: "profile",
        comparison_doc_id: "candidate",
        question: "Does the candidate meet the bar?",
      },
      {
        edge_id: "ctpp-to-ipdp",
        reference_doc_id: "candidate",
        comparison_doc_id: "plan",
        question: "Does the plan deliver it?",
      },
    ],
    org: "bmgf",
    intervention_class: "vaccine",
    indication: "malaria",
    blocks: [],
    findings: [
      finding({
        requirement_id: "itpp-to-ctpp/r-001",
        edge_id: "itpp-to-ctpp",
        verdict: upstreamVerdict,
        requirement: "Annual dosing.",
        reference_spans: [cite("profile/b-0001")],
        comparison_spans: upstreamBlocks.map(cite),
      }),
      finding({
        requirement_id: "ctpp-to-ipdp/r-001",
        edge_id: "ctpp-to-ipdp",
        verdict: downstreamVerdict,
        requirement: "Six-monthly dosing.",
        reference_spans: downstreamBlocks.map(cite),
        comparison_spans: [cite("plan/b-0007")],
      }),
    ],
  };
}

test("a plan meeting a commitment that falls short upstream is linked", () => {
  const warnings = chainWarnings(chain());
  const [warning] = warnings.get("ctpp-to-ipdp/r-001") ?? [];
  assert.ok(warning, "the downstream finding should carry a warning");
  assert.equal(warning.upstreamRequirementId, "itpp-to-ctpp/r-001");
  assert.equal(warning.upstreamVerdict, "falls_short");
  // No gap on the warning: it restated the upstream requirement, and a reader
  // following the warning arrives where that requirement is the heading.
  assert.ok(!("gap" in warning), "the warning carries a second sentence again");
  assert.equal(warning.upstreamReference, "iTPP");
  assert.equal(warning.sharedDocument, "cTPP");
  assert.deepEqual(warning.blockIds, ["candidate/b-0042"]);
});

test("nothing is linked when the two comparisons cite different passages", () => {
  // The honest limit: it under-reports rather than guessing. Two findings about one
  // commitment stated in two places do not meet, and no warning appears.
  const warnings = chainWarnings(
    chain({ downstreamBlocks: ["candidate/b-0099"] }),
  );
  assert.equal(warnings.size, 0);
});

test("an upstream verdict that settles the requirement links nothing", () => {
  for (const verdict of ["meets", "exceeds"] as AlignmentVerdict[]) {
    assert.equal(chainWarnings(chain({ upstreamVerdict: verdict })).size, 0, verdict);
  }
});

test("not_comparable upstream is linked too, in its own words", () => {
  // It is the other verdict that leaves a requirement unestablished against its bar.
  const warnings = chainWarnings(
    chain({
      upstreamVerdict: "not_comparable",
    }),
  );
  const [warning] = warnings.get("ctpp-to-ipdp/r-001") ?? [];
  assert.equal(warning?.upstreamVerdict, "not_comparable");
  assert.match(chainWarningText(warning), /cannot be compared with the iTPP/);
});

test("a downstream shortfall is not flagged again", () => {
  // It is already in the priorities and already carries its own gap. Flagging it here
  // would put one requirement in the panel twice for two different reasons.
  assert.equal(chainWarnings(chain({ downstreamVerdict: "falls_short" })).size, 0);
});

test("the warning claims something about the passage, never about the requirement", () => {
  // A block can hold several facts, so the two citations do not prove the two
  // requirements are the same one. The sentence has to be true either way.
  const [warning] = chainWarnings(chain()).get("ctpp-to-ipdp/r-001") ?? [];
  const text = chainWarningText(warning);
  assert.match(text, /^This passage of the cTPP/);
  assert.doesNotMatch(text, /requirement/i);
  // One sentence, and it ends there. It used to quote the upstream finding's `gap`,
  // which restated that finding's requirement - so a reader following the warning
  // arrived at a heading they had just been shown.
  assert.match(text, /falls short of the iTPP\.$/);
});

test("the chain is read from the edges, not from document types", () => {
  // Any edge whose measured document is another edge's reference document is upstream
  // of it. A configuration naming different types chains the same way.
  const result = chain();
  result.documents = [
    { doc_id: "a", source_type: "alpha", display_name: "Alpha" },
    { doc_id: "b", source_type: "beta", display_name: "Beta" },
    { doc_id: "c", source_type: "gamma", display_name: "Gamma" },
  ];
  result.edges = [
    { edge_id: "a-to-b", reference_doc_id: "a", comparison_doc_id: "b", question: "?" },
    { edge_id: "b-to-c", reference_doc_id: "b", comparison_doc_id: "c", question: "?" },
  ];
  result.findings = [
    finding({
      requirement_id: "a-to-b/r-001",
      edge_id: "a-to-b",
      verdict: "falls_short",
      reference_spans: [cite("a/b-0001")],
      comparison_spans: [cite("b/b-0001")],
    }),
    finding({
      requirement_id: "b-to-c/r-001",
      edge_id: "b-to-c",
      verdict: "meets",
      reference_spans: [cite("b/b-0001")],
      comparison_spans: [cite("c/b-0001")],
    }),
  ];

  const [warning] = chainWarnings(result).get("b-to-c/r-001") ?? [];
  assert.equal(warning?.sharedDocument, "Beta");
  assert.equal(warning?.upstreamReference, "Alpha");
});

test("a two-document run has no chain at all", () => {
  const result = chain();
  result.edges = result.edges.slice(0, 1);
  result.findings = result.findings.slice(0, 1);
  assert.equal(chainWarnings(result).size, 0);
});

test("one upstream finding reached through two passages is one warning", () => {
  const result = chain({
    upstreamBlocks: ["candidate/b-0042", "candidate/b-0043"],
    downstreamBlocks: ["candidate/b-0042", "candidate/b-0043"],
  });
  const warnings = chainWarnings(result).get("ctpp-to-ipdp/r-001") ?? [];
  assert.equal(warnings.length, 1);
  assert.deepEqual(warnings[0].blockIds, ["candidate/b-0042", "candidate/b-0043"]);
});

test("two upstream findings on one passage are two things to read", () => {
  const result = chain();
  result.findings.push(
    finding({
      requirement_id: "itpp-to-ctpp/r-002",
      edge_id: "itpp-to-ctpp",
      verdict: "falls_short",
      requirement: "Presented in a single-dose vial.",
      reference_spans: [cite("profile/b-0002")],
      comparison_spans: [cite("candidate/b-0042")],
    }),
  );
  const warnings = chainWarnings(result).get("ctpp-to-ipdp/r-001") ?? [];
  assert.deepEqual(
    warnings.map((warning) => warning.upstreamRequirementId),
    ["itpp-to-ctpp/r-001", "itpp-to-ctpp/r-002"],
  );
});
