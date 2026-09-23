---
name: draft-the-grantee-ask
description: Turn the open items in a result into one consolidated list of requests to send
requires_any:
  - screener
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

- **Screener** — `missing` on every `partly_answered` question: what the documents leave
  open. Plus `not_found` questions, whose ask is the question itself. Both carry the
  discipline that owns them.
- **Aligner** — the `requirement` and the `statement` on every `falls_short` and
  `not_comparable` finding. The distance between them is what the measured document
  would have to close; neither sentence alone is the ask.
- **Inspector** — the `statement` on units with `not_present`, `placeholder`,
  `insufficient`, `vague` or `section_conflict`, read against the saved rubric
  requirement and unit. Exclude `specified` and `not_applicable`: neither is an
  outstanding ask. Keep each unit attributed to its own rubric review.

If the workspace holds more than one of these for the same product, use all of them and
say which tool each ask came from. Confirm they are the same product first: `org`,
`intervention_class`, `indication`, and the document IDs.

## Assembling it

1. `find_result` for the structures above, then `read_result` for the sentences and their
   block IDs.
2. Group by who answers. Screener's discipline is the routing where it exists. Otherwise
   group by document — an ask about the profile goes to whoever owns the profile.
3. Merge duplicates only when two asks name the same thing about the same passage. Cite
   both sources on the merged line. Two asks that read alike but cite different passages
   are two asks: collapsing them loses one, and the reader has no way to notice.
4. Keep the tool's wording. Quote the sentence. Where a sentence cannot stand alone, add
   the requirement or question it came from as context rather than rewriting the ask.
5. Keep source order within each tool and rubric. For Screener, show required
   questions before anticipatory questions, preserving bank order within each.
   A merged ask retains both tool attributions; overlap does not create urgency.

## What to produce

A list, grouped, with a one-line preamble naming the documents and the runs it came from.
Per line: the ask, the tool and named question or rubric unit that raised it, and
any cited passage. Preserve Screener's required/anticipatory label. An absence
finding with no passage remains an attributed ask, not a fabricated citation.

Nothing else. No summary paragraph of how the programme is doing, no counts framed as
progress, no ranking of the groups against each other.

## Rules

Never invent an ask. Every line is a sentence one of these tools wrote. If something
obvious is missing, say that no tool raised it rather than adding it yourself — this list is
sent to someone who will act on it, and one unattributable line makes the whole list
suspect. If an item lacks enough wording to draft an ask, identify that item and
the limitation rather than silently dropping it or supplying an invented request.

Do not present absence as fault. `not_found` means nothing supplied answered the question,
and `not_addressed` means the document made no commitment; neither is a claim that the
recipient did something wrong. Ask for the thing, not for an explanation of its absence.

Do not attach urgency the tools did not state. Inspector reports rubric conformance,
not severity. An Aligner shortfall is not more urgent than a Screener partial because
it appears first in this list; requirement labels are not severity scores either.

Say what is not in it. Name the tools that did run and the ones that did not, because a
reader will otherwise take this list as everything outstanding rather than everything these
runs found.

When an item cites a passage, link that exact block and name its section or heading
when supplied. When no passage exists, as with `not_found` or `not_present`, identify
the gate question or rubric requirement by its saved ID and wording instead. Do not
invent a document heading, anchor absence at a nearby passage, or cite a result path.
The tool and its question or requirement establish why the ask is in the list;
document links establish what the supplied material actually says.
