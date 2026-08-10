---
name: separate-gate-blockers-from-document-gaps
description: Read where the candidate misses its profile against what the gate will actually ask about
requires:
  - aligner
  - expert
---

Answer one question: of the places the candidate does not meet its profile, which will the
gate ask about, and which will it not?

Both results describe shortfalls, and they are not the same shortfall. Aligner says the
candidate offers less than the profile asked for — a fact about two documents. Expert says
the gate's reviewers will ask something the documents do not answer — a fact about a
review. A divergence nobody asks about at this gate can wait. An unanswered question about
a target the candidate already misses is the one that stops a meeting.

## What each result is, before you pair anything

Aligner's `findings` are one per requirement read out of the reference document, each with
a `verdict`, a `statement`, a `gap` where the verdict has one, and two citation lists:
`reference_block_ids` in the document that set the bar, `comparison_block_ids` in the
document measured.

Expert's `disciplines[].questions[]` are the whole bank for one gate, each with a `state`
of `answered`, `partly_answered`, `not_found` or `not_applicable`, a `statement`, a
`missing` sentence on partials, and `cited_block_ids` where an answer was read from a
document.

Neither ranks the other. Expert's order is the bank authors' sequence and Aligner's is
the order requirements were read; do not reorder either, and do not present one tool's
finding as evidence for the other's.

## Read in this order

1. `find_result` for `findings` in the Aligner result. Keep `falls_short`,
   `not_comparable` and `not_addressed`.
2. `find_result` for `disciplines` in the Expert result. Keep questions whose state is
   `partly_answered` or `not_found`, and note which discipline each sits in.
3. `read_result` for the block IDs and sentences on both sides.
4. Pair only where the block IDs overlap — an Aligner citation and a question's
   `cited_block_ids` naming the same passage. Two items about "shelf life" are not
   necessarily about the same commitment, and the shared passage is the only evidence
   they are.
5. A `not_found` question cites nothing, so it can never pair by passage. Pair it by
   **discipline and subject** instead, and say explicitly that you did so — that is a
   judgement about wording, not a lineage, and a reader must be able to discount it.

## The pairs worth reporting

**A shortfall the gate will ask about.** An Aligner `falls_short` on a passage a
`partly_answered` question also cites. Report both sentences: the `gap` says what the
candidate is short of, the `missing` says what the reviewer will find unanswered. Name the
discipline, because that is who will ask. This is the pair that decides what gets fixed
before the meeting.

**A shortfall the gate does not reach.** An Aligner `falls_short` with no question on that
passage. Still a divergence from the profile and still worth an ask, but it is not a gate
blocker at this gate — say which gate the Expert result covers, because a later one may
ask.

**A question the alignment already explains.** A `partly_answered` or `not_found`
question about a target Aligner reports as `not_addressed`. The document does not merely
under-answer the reviewer; it never made the commitment. Report the alignment finding as
the reason, so the ask is "commit to this" rather than "describe this better".

**Met, and still asked about.** An Aligner `meets` on a passage a `partly_answered`
question cites. The candidate matches the profile and the gate still wants more detail —
meeting a bar is not the same as satisfying a reviewer. Do not report this as a
contradiction between the tools; they are answering different questions.

**A gate question about something the profile never asked for.** A `not_found` question in
a discipline whose subject appears in no Aligner requirement. The gate expects something
the profile does not, which is a question about the profile rather than about the
candidate.

## How to report it

Order by what a reader would act on differently:

1. Shortfalls the gate will ask about, by discipline.
2. Questions the alignment explains — where the ask changes shape.
3. Shortfalls outside this gate.
4. Everything else.

One short paragraph each: the requirement and its verdict, the question and its state,
then the passages on both sides. Open with how many pairs you formed out of how many
findings and how many open questions, so a reader knows whether this is a thorough pairing
or a coincidence.

## Rules

Cite both sides as document passages, and name which side each sentence came from: the
Aligner finding's blocks and the question's `cited_block_ids`. A result path locates a
finding for you and shows a reader nothing. A claim you cannot cite on both sides is a
claim this skill cannot make.

Never overturn either tool, and never merge their vocabularies. A verdict is about two
documents; a state is about a question. Saying a requirement is `not_found` or a question
`falls_short` describes something neither tool reported.

Say which gate the Expert result covers, every time. The same documents are triaged again
at every gate, and "the gate does not ask" is only true of the gate that ran.

Confirm the runs are the same product before pairing: `org`, `intervention_class`,
`indication`, and the document IDs on both results. Block IDs are built from document IDs,
so two runs on differently named uploads of one file share no passages and can never pair.
If they differ, say so and stop.

Say what you could not pair. Shortfalls no question touches, and open questions no
requirement touches, are both findings — the second especially, because it is the part of
the gate the profile does not cover at all.

No score and no proportion. Aligner's total is however many requirements that profile
states and Expert's is the bank's fixed length; a fraction of either says nothing about
readiness, and a fraction across both says nothing at all.
