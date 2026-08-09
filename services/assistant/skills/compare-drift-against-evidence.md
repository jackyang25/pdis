---
name: compare-drift-against-evidence
description: Read what changed between two documents against what current evidence says about it
requires:
  - aligner
  - scout
---

Answer one question: of the commitments that changed between the two documents,
which does external evidence support, and which does it undermine?

Neither result answers this alone. Aligner reports what moved without knowing
whether the new position is defensible. Scout tests targets against evidence
without knowing which of them are new.

## Read in this order

1. `find_result` for `links` in the Aligner result. Take only the relations that
   represent a change: `modified` and `conflict`. `aligned` did not move, and
   `missing` and `introduced` have no before-and-after to weigh.
2. For each, `read_result` at that link's path to get its reference and comparison
   unit IDs, its exact block IDs, and its stated reason.
3. `find_result` for `matches` in the Scout result. Each carries an insight and a
   relation to the document: `contradicts`, `extends`, `confirms`, or `unrelated`.
4. Pair a change with an insight only when they concern the same commitment. Two
   items mentioning efficacy are not necessarily about the same target; check the
   unit and the cited blocks, not the wording.

## What to say about each pair

State the change first, then what the evidence does to it, then the citation.

- A `modified` commitment whose new value the evidence `contradicts` is the most
  consequential thing you can report. Say so plainly.
- A `modified` commitment the evidence `confirms` is a change that gained support.
  Worth stating, because a reviewer looking only at drift would treat it as risk.
- A `conflict` where the evidence favours one side tells the reader which
  document to correct, which neither tool says on its own.
- `extends` is a gap, not a failure. It means the current standard differs from
  an aspirational target — do not report it as a contradiction.

## Rules

Cite both sides. Every statement names the Aligner link and the Scout insight it
rests on, so a reader can check it. A claim you cannot cite on both sides is a
claim this workflow cannot make.

Never pair across documents you have not confirmed are the same product. The two
results may concern different uploads.

Say what you could not pair. Changes with no matching evidence, and evidence
touching nothing that changed, are both real findings — the first is unexamined
risk, the second is context. Silence about them reads as coverage you do not have.

Scout's benchmark statistics describe the cohort that run admitted. If it declares
a `published_since` window, say so when quoting any count, because a reader will
otherwise take it as the whole field.
