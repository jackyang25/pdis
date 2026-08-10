---
name: draft-the-grantee-ask
description: Turn the open items in a result into one consolidated list of requests to send
requires_any:
  - expert
  - aligner
  - inspector
---

Answer one question: what should be asked for, of whom, in one message?

Every tool already produces the sentences. What it does not produce is a message: the open
items sit inside their own structures, one per finding, in the order the analysis was made
rather than the order anyone would send. This assembles them and nothing more — it does not
decide what matters, and it does not soften or sharpen a single ask.

## Where the asks already are

Take only these. Each is a sentence a tool wrote for exactly this purpose.

- **Expert** — `missing` on every `partly_answered` question: what the documents leave
  open. Plus `not_found` questions, whose ask is the question itself. Both carry the
  discipline that owns them.
- **Aligner** — `gap` on every `falls_short` and `not_comparable` finding: what the
  measured document would have to close.
- **Inspector** — `recommendation` on every finding that carries one, and the finding's
  `statement` where it does not.

If the workspace holds more than one of these for the same product, use all of them and
say which tool each ask came from. Confirm they are the same product first: `org`,
`intervention_class`, `indication`, and the document IDs.

## Assembling it

1. `find_result` for the structures above, then `read_result` for the sentences and their
   block IDs.
2. Group by who answers. Expert's discipline is the routing where it exists. Otherwise
   group by document — an ask about the profile goes to whoever owns the profile.
3. Merge duplicates only when two asks name the same thing about the same passage. Cite
   both sources on the merged line. Two asks that read alike but cite different passages
   are two asks: collapsing them loses one, and the reader has no way to notice.
4. Keep the tool's wording. Quote the sentence. Where a sentence cannot stand alone, add
   the requirement or question it came from as context rather than rewriting the ask.
5. Order within a group by what blocks the most: an ask that closes both a shortfall and
   an open gate question first, then shortfalls, then unanswered questions, then anything
   advisory.

## What to produce

A list, grouped, with a one-line preamble naming the documents and the runs it came from.
Per line: the ask, the passage it concerns, and the tool that raised it.

Nothing else. No summary paragraph of how the programme is doing, no counts framed as
progress, no ranking of the groups against each other.

## Rules

Never invent an ask. Every line is a sentence one of these tools wrote. If something
obvious is missing, say that no tool raised it rather than adding it yourself — this list is
sent to someone who will act on it, and one unattributable line makes the whole list
suspect.

Do not present absence as fault. `not_found` means nothing supplied answered the question,
and `not_addressed` means the document made no commitment; neither is a claim that the
recipient did something wrong. Ask for the thing, not for an explanation of its absence.

Do not attach urgency the tools did not state. Inspector grades severity and nothing else
does; an Aligner shortfall is not more urgent than an Expert partial because it appears
first in this list.

Say what is not in it. Name the tools that did run and the ones that did not, because a
reader will otherwise take this list as everything outstanding rather than everything these
runs found.

Point every line at the recipient's own document, and do it in their terms: name the
section or heading the passage sits under, because a block ID means nothing to someone who
has never seen our parse. Keep the block as an openable link beside it so you can check
the line yourself, and never cite a result path — that locates a finding in our analysis,
which is not something they can look at. An ask a recipient cannot trace to a place in
their own document is one they can dispute forever.
