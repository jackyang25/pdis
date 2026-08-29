---
name: compare-drift-against-evidence
description: Read where a candidate misses its profile against what current evidence says about that target
requires:
  - aligner
  - scout
---

Answer one question: where the candidate does not meet the profile, is the candidate
behind, or is the profile asking for something the field cannot deliver?

Neither result answers it alone. Aligner says whether one document meets another's
requirements and never looks outside them, so it cannot tell a lagging candidate from an
unreasonable bar. Scout tests targets against external evidence and never knows which of
them a candidate failed to meet.

## Which side the evidence lands on decides the question

An Aligner finding cites two documents. `reference_spans` quote the document that sets the
bar; `comparison_spans` quote the document measured against it. Each span carries the exact
lines and the block they came from, so a pair can reproduce both sentences verbatim rather
than describing the passages they sit in.

Scout runs on one document at a time, so which of those two its evidence touches decides
what a pair can say:

- Evidence meeting the **requirement** side asks **is the bar achievable**.
- Evidence meeting the **verdict** side asks **is this document's claim supported**.

Answering the first with evidence about the second is the error to avoid. It reads as a
finding and points at the wrong document.

Read those as sides of a comparison, never as document types. A run holds one comparison
per declared pair, and a document sits on whichever side the comparison puts it on:

- Two documents, one comparison (iTPP to cTPP). Evidence on the iTPP tests the bar;
  evidence on the cTPP tests the candidate's claim.
- Three documents, two comparisons (iTPP to cTPP, cTPP to IPDP). **The cTPP is on both
  sides** — measured in the first comparison, authoritative in the second. So one Scout
  run on the cTPP answers two different questions, and which one depends entirely on
  which comparison you are pairing with. Against the first comparison it tests whether
  the candidate's claim holds up. Against the second it tests whether the bar the plan
  is being held to is itself sound.

State the comparison by its `edge_id` in every pair. Without it, "evidence contradicts
the cTPP" is two different findings and a reader cannot tell which one you made.

## Read in this order

1. `find_result` for `findings` in the Aligner result. Each carries `requirement`,
   `verdict`, `statement`, `edge_id`, and both citation lists.
2. Take the verdicts that leave something open: `falls_short`, `not_comparable`, and
   `not_addressed`. `meets` and `exceeds` still matter, but only for the one pair that
   turns on them: a met requirement whose claim the evidence contradicts.
3. `read_result` at each finding's path for its quoted spans and its `statement`.
4. `find_result` for `matches` and any assessments in the Scout result. Each carries an
   insight, its relation to the document (`contradicts`, `extends`, `confirms`,
   `unrelated`), and the document blocks it was assessed against.
5. Pair only where the **block IDs overlap**. Two items that both mention efficacy are
   not necessarily about the same target; the shared passage is the only evidence that
   they are. State which passage a pair rests on.

## The pairs worth reporting

Each is a different decision, so name which one you are making.

**A shortfall the evidence says is unachievable.** `falls_short`, and Scout on the
reference document `contradicts` that requirement. The gap is in the profile, not in the
candidate: say plainly that the bar is what the evidence disputes, and do not report it as
a candidate deficiency.

**A shortfall the evidence undercuts on both sides.** `falls_short`, and Scout on the
**comparison** document contradicts the value that document offers. The candidate is short
of the bar, and the weaker value it offers instead is itself unsupported — so the bar is
further out of reach than the shortfall alone suggests.

This is the one place evidence about the comparison document may be read against the
requirement, and it is arithmetic rather than inference: `falls_short` means the document
does less than the requirement asks, on that requirement's own axis and in that direction.
Evidence that cannot reach the lesser value cannot reach the greater one. State it that
way, showing both values, so a reader can check the step rather than take it.

It holds only where all three are true, and saying so is part of the finding:

- the verdict is `falls_short` — on `not_comparable` the two documents share no axis,
  which is what that verdict means, so there is no direction to argue along
- the evidence is against the value, not merely thin on it — an unsupported target and an
  unstudied one are different findings
- the requirement and the statement are the same quantity — "under $3 a dose" against
  "under $5 a dose", not a cost against a schedule

The ask changes entirely: not about moving the grantee from its value to the bar, but about
whether the bar was ever reachable.

These two are the findings this skill exists to produce, because they are the only ones
that change who the next conversation is with. They reach it from opposite sides — the
first from evidence about the document that set the bar, the second from evidence about
the document measured against it — so a run where Scout read only one of the two documents
can still reach it, by exactly one of the two routes.

**A shortfall the evidence leaves standing.** `falls_short`, and evidence `confirms` the
requirement or is silent on it. The bar survives, so the ask is the requirement itself,
and the `statement` is how far the document currently gets. Quote both.

**A met requirement whose claim the evidence contradicts.** `meets` or `exceeds`, and
Scout on the comparison document `contradicts` that passage. Aligner judges coherence,
never feasibility, so a document can honour a requirement exactly and the value it states
still be one nothing supports. Report it as the alignment being no assurance, not as
Aligner being wrong.

**An incomparable requirement the evidence can make comparable.** `not_comparable`, and
Scout holds external measurements for that attribute. The evidence supplies the terms the
two documents failed to share — a unit, a population, an endpoint. Turn the pair into a
concrete ask rather than repeating that the two cannot be compared.

**A shortfall that sits where the field sits.** `falls_short`, and Scout's precedent or
comparators cluster at the value the candidate offers. The candidate is at the state of
the art and the profile is ahead of the field. This is a different conversation from a
lagging candidate; say which one it is.

Not to be confused with *a shortfall the evidence undercuts on both sides*, which carries
the same verdict and the same evidence on the same document. What separates them is where
the comparators fall relative to the value the candidate offers: *at* it, and the candidate
is as good as the field gets; *short of* it, and the candidate's own value is unsupported
too. The first says the profile is ahead of the field; the second says it is further ahead
than anyone had noticed. Read the comparators before choosing, and quote them either way.

**Absent on both sides.** `not_addressed`, and Scout found nothing on the subject either.
Unknown territory rather than an omission. Report it separately, because asking a grantee
to document something nobody has established is the wrong ask.

## Where two comparisons meet, before any evidence

Do this whenever the run holds more than one comparison, because it is the one finding
the verdicts cannot show on their own and it is not in the result as a field.

A document that is measured in one comparison is authoritative in the next, so a plan can
faithfully deliver a commitment that itself falls short — `meets` in the second
comparison, `falls_short` in the first, and every verdict correct. Read the second
comparison alone and it is all good news.

Find it the same way you pair with evidence, by shared passage: take each finding whose
verdict is `falls_short` or `not_comparable`, note the blocks its `comparison_spans`
cite, and look for a later comparison whose findings cite any of those same blocks in
`reference_spans`. Where they overlap, the later document is delivering against a
commitment the earlier comparison already questioned.

Say it as a claim about the passage, not about the requirement: a paragraph can carry
several facts, so a shared citation does not prove both comparisons meant the same clause.
Quote the earlier finding's requirement and its `statement` — the two together are the
shortfall, and neither alone is. Do not change either verdict — the plan does meet the
document it was measured against, and that is the point.

Then layer evidence on top if you have it. A commitment that falls short of the profile,
is faithfully planned for, and is contradicted by external evidence is the strongest thing
this pairing can report: the programme is executing precisely toward a target the field
disputes.

## How to report it

Order by what a reader would act on differently, not by the order you found things:

1. A bar the evidence disputes, by either route. It changes who the next conversation is
   with. Say which document the evidence read, because that is what a reader will check.
2. A met requirement whose claim the evidence contradicts. It withdraws a reassurance
   the alignment appeared to give.
3. A commitment delivered downstream that an earlier comparison questioned.
4. Everything else, and last the pairs where nothing is in tension.

One short paragraph each, in this order: the requirement and its verdict, then what the
evidence does to it, then the citation on both sides. Not a table — a table of every
requirement buries the three findings that matter in the forty that do not.

Lead with a sentence naming how many pairs you formed and out of how many findings, so a
reader knows whether they are looking at a thorough pairing or two coincidences.

## Rules

Cite both sides as things a reader can open: the shared document passage, and the source
URL behind the evidence. Name the Aligner finding and the Scout item so the pairing is
traceable, but a result path is navigation rather than a citation — it shows a reader
nothing. A claim you cannot cite on both sides is a claim this skill cannot make.

Never overturn either tool. You are reporting what two results say together; you are not
issuing a third verdict. Do not restate an Aligner verdict as a different one because
evidence disagrees with it — say that they disagree, and which document each concerns.

Respect the direction. An Aligner comparison runs one way, and a pair inherits that:
never describe a shortfall as the reference document failing the comparison document.

Never pair across runs you have not confirmed are the same product. Check `org`,
`intervention_class`, `indication`, and the document IDs on both results first. The
document IDs matter twice: they establish it is the same product, and block IDs are built
from them, so two runs on differently named uploads of the same file share no passages and
can never pair at all. If they differ, say so and stop rather than reporting an empty
pairing as agreement.

Say what you could not pair. Shortfalls with no evidence are unexamined risk; evidence
touching nothing the candidate missed is context. Both are findings, and silence about
them reads as coverage you do not have.

No score, and no counting of pairs as a proportion. Aligner's total is however many
requirements that profile happens to state, so a fraction of it means nothing outside
this one comparison.

Scout's benchmark statistics describe the cohort that run admitted. If it declares a
`published_since` window, say so when quoting any count, because a reader will otherwise
take it as the whole field.
