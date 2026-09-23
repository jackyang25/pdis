---
name: separate-gate-blockers-from-document-gaps
description: Read where the candidate misses its profile against what the gate will actually ask about
requires:
  - aligner
  - screener
---

Answer one question: of the places the candidate does not meet its profile, which will the
gate ask about, and which will it not?

Both results describe shortfalls, and they are not the same shortfall. Aligner says the
candidate offers less than the profile asked for — a fact about two documents. Screener says
the gate's reviewers will ask something the documents do not answer — a fact about a
review. Their overlap identifies matters to discuss at the gate, not a decision that
the meeting must stop or that an unpaired divergence can safely wait.

## What each result is, before you pair anything

Aligner's `findings` are one per requirement read out of the reference document, each with
a `verdict`, a `statement`, and two citation lists: `reference_spans` quoting the
document that set the bar, `comparison_spans` quoting the document measured.

Screener's `disciplines[].questions[]` are the whole bank for one gate, each with a `state`
of `answered`, `partly_answered`, `not_found` or `not_applicable`, a `statement`, a
`missing` sentence on partials, and `cited_block_ids` where an answer was read from a
document. Each question also carries its authored `requirement`: `required` or
`anticipatory`. Preserve that distinction; an anticipatory question is not a current
gate blocker merely because it is unanswered.

Neither ranks the other. Screener's order is the bank authors' sequence and Aligner's is
the order requirements were read; do not reorder either, and do not present one tool's
finding as evidence for the other's.

## Read in this order

1. `find_result` for `findings` in the Aligner result. Keep `falls_short`,
   `not_comparable` and `not_addressed`; also inspect `meets` and `exceeds` for
   commitments an open gate question asks about.
2. `find_result` for `disciplines` in the Screener result. Keep questions whose state is
   `partly_answered` or `not_found`, and note which discipline each sits in.
3. `read_result` for the block IDs and sentences on both sides.
4. For passage-backed pairs, require overlapping block IDs — an Aligner citation and a question's
   `cited_block_ids` naming the same passage. Two items about "shelf life" are not
   necessarily about the same commitment, and the shared passage is the only evidence
   they are.
5. A `not_found` question cites nothing, so it can never pair by passage. Where its
   discipline and subject support a connection, report a **subject-based association**
   instead. Name the question by ID and wording, with its state and requirement;
   cite the Aligner passages only. Explicitly say there is no shared passage and
   that the association is an interpretation, not established lineage. If the
   subject connection is uncertain, leave the items unpaired and say so.

## The pairs worth reporting

**A shortfall the gate will ask about.** An Aligner `falls_short` on a passage a
`partly_answered` question also cites. Report both sentences: the finding's
`requirement` against its `statement` is what the candidate is short of, and the
`missing` is what the reviewer will find unanswered. Name the
discipline, because that is who will ask, and retain the question's required or
anticipatory label rather than assigning a deadline or urgency.

**A shortfall with no established gate connection.** An Aligner `falls_short` with
neither a passage-backed pair nor a supported subject-based association. Report it
as unpaired in this review, not as proof the gate does not ask about it or it can wait.

**A question the alignment already explains.** A `partly_answered` or `not_found`
question about a target Aligner reports as `not_addressed`. The document does not merely
under-answer the reviewer; it never made the commitment. Report the alignment finding as
the reason, so the ask is "commit to this" rather than "describe this better".

**Met, and still asked about.** An Aligner `meets` or `exceeds` on a passage a `partly_answered`
question cites. The candidate meets or exceeds the requirement, as Aligner reports,
and the gate still wants more detail —
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
3. Shortfalls with no established gate connection.
4. Everything else.

One short paragraph each: the requirement and its verdict, the question and its state
and requirement label, then the supporting citations. Distinguish passage-backed pairs
from subject-based associations. Open with the count of each, alongside how many
findings and open questions you examined, so the reader can see the review's coverage.

## Rules

For passage-backed pairs, cite the Aligner finding's blocks and the question's
`cited_block_ids`, naming which tool reported each claim. For subject-based
associations, cite the available Aligner passages and identify the uncited gate
question as described above. Never invent a Screener passage for `not_found` or
present an Aligner passage as its citation. A result path is navigation, not evidence.

Never overturn either tool, and never merge their vocabularies. A verdict is about two
documents; a state is about a question. Saying a requirement is `not_found` or a question
`falls_short` describes something neither tool reported.

Say which gate the Screener result covers, every time. The same documents are triaged again
at every gate, and "the gate does not ask" is only true of the gate that ran.

Confirm the runs are the same product before pairing: `org`, `intervention_class`,
`indication`, and the document IDs on both results. Block IDs are built from document IDs,
so two runs on differently named uploads of one file share no passages and can never pair.
If they differ, say so and stop.

Say what you could not pair. Shortfalls no question touches, and open questions no
requirement touches, are both findings — the second especially, because it is the part of
the gate the profile does not cover at all.

No score and no proportion. Aligner's total is however many requirements that profile
states and Screener's is the bank's fixed length; a fraction of either says nothing about
readiness, and a fraction across both says nothing at all.
