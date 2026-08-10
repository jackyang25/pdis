---
name: write-the-review-summary
description: Write a short passage about a result that survives being quoted out of context
requires_any:
  - inspector
  - aligner
  - scout
  - expert
---

Answer one question: what can be said about this result, in a few sentences, that stays
true when someone repeats it without the result in front of them?

This is the skill with the highest chance of doing harm, because its output travels.
A written line goes into a memo, a slide, a committee paper, and it arrives without the
counts, the citations, or the caveats that made it defensible. So the constraint is not
brevity. It is that every sentence must survive on its own.

## What each result can and cannot support

Read the tool's own vocabulary before writing a word about it.

- **Inspector** graded one document against an authored rubric. It says whether the
  document contains and specifies what its template requires. It says nothing about
  whether the product is good, whether the targets are achievable, or whether anyone
  agrees with them.
- **Aligner** checked one document against another's requirements, one way. It says
  whether the measured document meets the bar. It does not say the bar is right, and it
  never checks whether a claim is true.
- **Scout** tested the document's targets against external evidence. It says what the
  literature it retrieved supports or disputes, within the window that run admitted.
- **Expert** triaged one gate's question bank. It says which questions the supplied
  material answers. It does not answer them, and it renders no verdict on the documents.

Name the authority in the passage itself. "Against the PDID template", "against the
intervention profile", "against published evidence", "against the Lead Candidate Selection
bank". A sentence that says a document "was assessed" and does not say against what is the
sentence most likely to be misquoted.

## How to write it

Produce two parts, in this order, and say which is which.

**The passage.** Three to six sentences, no citations of any kind inside it, one claim per
sentence:

1. What ran, on which documents, and against what authority.
2. The one or two findings that would change a decision, one sentence each.
3. What the result does not cover.

This part exists to be copied into a memo or a slide, so anything a reader cannot paste
does not belong in it. A citation inside the passage arrives at its destination as either
link syntax or clutter, and it stands exactly where the sentence should be. The passage
earns its trust from being specific and denominated, not from carrying references.

**What it rests on.** Underneath, a short list of the passages behind each sentence, as
openable links to document blocks. Say plainly that this part is not for the memo — it is
so you, or whoever asks where a sentence came from, can check it before it travels. Nothing
is unsourced; the sources simply sit outside the text.

Never cite a place in the analysis in either part. A result path like
`sections[2].units[1].findings[0]` is your own navigation and names nothing a reader can
see. Where a claim is about the analysis rather than the document — a count, a total — the
denominator is what makes it checkable, so give that and cite nothing.

Use the tool's words for its own states. Write "twelve requirements the candidate falls
short of" rather than "twelve failures"; "forty questions the documents do not answer"
rather than "forty gaps". The tools chose those words to avoid claims they cannot support,
and a synonym reintroduces the claim.

Give a count only with its denominator and its authority in the same sentence. "Twelve of
the fifty-one requirements the profile states" is quotable. "Twelve shortfalls" is not.

## Rules

No score, no percentage, no grade for the whole. Every one of these results is several
states that sum to a total, and blending them produces a figure none of the tools computed:
one number cannot hold "the document says it", "it says half of it", and "nobody has asked
yet". If you are asked for a headline number, give the largest state with its denominator
and say why there is no single figure.

Never compare across runs unless the runs are comparable, and say when they are not. A
gate review compares line by line against another run of the same gate. An alignment does
not: its total is however many requirements that reference document happens to state, so
two alignments have different denominators and neither is a baseline for the other.

Do not upgrade absence into fault, or a hint into a finding. `not_found`, `not_addressed`
and `missing` all mean the supplied material does not contain something. None of them means
anyone failed, and several of these questions were never going to be answered by the
documents at all.

Attribute every judgement to the tool that made it, inside the passage: "Inspector found",
"the alignment reports". That much survives being pasted, and a summary sentence with no
attribution reads as the assistant's own conclusion, which is the one thing it must never
be. The passage it rests on goes in the list below, not in the sentence.

State the run's boundaries. Which documents, which gate, which comparison, and for Scout
the `published_since` window. A reader who does not know what was in scope cannot tell what
the silence means.

If the result does not support a passage worth writing — nothing consequential, or nothing
citable — say that. A summary asserting significance the result does not carry is worse
than no summary.
