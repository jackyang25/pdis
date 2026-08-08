# Librarian — the case for it and what has to be decided

**Status:** nothing built. A `coming_soon` card exists in `web/lib/tools.ts` and a
`drafting` section in `web/lib/tool-sections.ts`, so the gap is visible on the
overview. No service, route, config, result type, or contract.

This document exists so the next person to pick it up does not have to
reconstruct the reasoning from an email thread.

## Where the request came from

Janet raised two use cases. The second one:

> Developing a new iTPP from scratch where there is little precedent: user could
> be a PPL, Initiative Lead or a Grantee. In this case it would be helpful to scan
> TPPs for similar modalities (e.g. other vaccines targeted to the same
> population) and pull in product attributes that are pathogen agnostic. So for
> vaccines you might want to ask whether it is for infants, adults or pregnant
> women, or whether it is for routine immunization or immunization campaigns
> during a disease outbreak. The product attributes that are generic across
> pathogens include dosing schedule, duration of protection, presentation, shelf
> life and stability, procurement price.

The scope as settled: a dataset of the Foundation's own iTPPs, cTPPs, and IPDPs
already exists. The user picks a few facts about the product they are planning —
vaccine, infants, routine immunization — and Librarian reads across that library
and shows what comparable programs committed to on the attributes that do not
depend on the indication. Every value cites the exact block in the source
document. No public evidence, no upload.

**A note on wording.** The email says "pathogen agnostic," and that is right for
vaccines, but a pathogen is the vaccine-shaped instance of a general rule. The
config carries five intervention classes — `vaccine`, `monoclonal_antibody`, `drug`, `diagnostic`,
`device` — and a diagnostic's or device's indication may name no pathogen at all.
The general form is **independent of the indication**, which is the field the
system already has. The same caution applies to the attribute examples: dosing
schedule and duration of protection are vaccine-shaped, while presentation, shelf
life, and procurement price hold across every class. Which attributes are actually
indication-independent is per intervention class, so it belongs in the attribute
vocabulary, not in code or copy.

The question it answers is not "does my target hold up" but "what have we asked
for before" — an answer that today exists only in people's heads and in thirty
separate files.

## Why it is not Scout, and not a fourth authority

Scout is built one way: the document states a number, and Scout tests whether
that number holds up against external evidence, always citing the sentence it was
read from. Librarian has no document and no stated number, so there is nothing to
test. Making one tool do both would blur what either result means.

More importantly, **Librarian renders no verdict.** Inspector judges against a
rubric, Aligner against a second document, Scout against external evidence.
Librarian reports what the library says. So it does not extend the founding split
with a fourth authority — it sits beside it: three judges, one reporter.

Write that down wherever the split is stated, because the obvious next feature
request is "and tell me whether my draft is in line with precedent," which would
silently make Librarian into Aligner with a corpus.

## Decisions already made — do not relitigate without reason

- **Separate tool, not a Scout mode.** Different input (none), different output
  (reported values, not judgments), different authority (none).
- **It reuses nothing of Scout's result contract.** It may reuse measurement
  normalization if that turns out to be separable; it cannot reuse the result
  shape, because Scout's lineage is anchored to an uploaded document's blocks.
- **A fifth card in the PST band, last**, not a group of its own. It was briefly
  given a "Drafting from precedent" section, which was wrong twice: sections group
  by audience, so a section named after a phase of the process puts two axes at one
  heading level; and "precedent" is Scout's own vocabulary (`precedent_classifier`,
  a precedent axis in its results), so the heading implied a relationship to Scout
  that does not exist. It goes last despite asking the earliest question, because
  leading with it pushes Scout off the first row of the two-column grid. The PST
  section copy carries its clause at the end, matching card order.
- **Named Librarian.** Not *Drafter*, which implies it writes the iTPP; it writes
  nothing. Not *Precedent*, which collides with a term Scout already owns in its
  result axes.
- **Its card description states no authority**, unlike every other tool's. See the
  note on `description` in `web/lib/tools.ts`. Do not give it one for symmetry.

## The five things that have to be decided

### 1. Permission scope — decide before the file format exists

**This is the one to settle first**, because it constrains the result shape and is
far cheaper to decide now than after saved files are in circulation.

Every other tool cites blocks from a document the user just uploaded, and the
saved result embeds those blocks. Librarian's citations come from *other
programs'* documents. An iTPP is Foundation-authored, but a cTPP is
grantee-authored and a committed procurement price may be commercially sensitive.

The questions:

- Who may see which documents? Is the library uniformly visible to any PPL, or
  scoped per investment, per initiative, or per grantee?
- If results are portable — and every other PDIS result is — a downloaded file
  carries another grantee's numbers to wherever it is forwarded. Do results embed
  the cited blocks (checkable offline, but redistributable) or reference them
  (not portable, and the citation cannot be verified from the file)?
- Does the visible set depend on who is running it? If so, Librarian is the first
  tool whose output depends on the user's identity, not only on its inputs.

The card copy already commits to the honest framing — "the iTPPs, cTPPs, and
IPDPs you are permitted to view" — so whatever is decided, the tool must actually
enforce it rather than showing everything.

### 2. The corpus makes this the first stateful tool

PDIS is stateless because the documents are the state: same inputs, same output,
forever. Librarian's authority is a stored library, so the same query answered in
August and in November returns different numbers with no visible reason.

Treat the library snapshot the way Scout treats `published_since`: record on the
result which snapshot was read. Otherwise two PPLs quote different "typical shelf
life" figures and neither can tell why. The parallel is exact — a value read
without knowing its window answers a different question than the one asked.

### 3. Never mix document types — this is the load-bearing rule

An iTPP's target is a class-level ambition. A cTPP's is a specific candidate's
commitment. A number blending them means neither.

This is the same defect that killed the old Aligner analysis: a shape that
averages two different kinds of statement produces an answer that is not wrong so
much as meaningless. So document type is not a filter the user may apply — it is
a **partition of the output**. There is never one "typical dosing schedule"; there
are separate answers per document type, side by side.

Consequence for the config: `source_type` stops being an input and becomes a
dimension of the result. Nothing is uploaded, so there is nothing to declare, yet
the field is more central here than in any other tool.

### 4. The config is the first real amendment to the shared header

Today every tool takes org, intervention class, indication, and document type.
Librarian takes **org and intervention class only.**

| Field | Librarian | Why |
|---|---|---|
| `org` | yes | Scopes which library is read |
| `intervention_class` | yes | Selects the attribute vocabulary; "similar modality" is this field |
| `indication` | **no** | Pathogen-independence is the premise |
| `source_type` | **not an input** | Nothing is read from an upload; it is an output partition instead |
| population | run parameter | infants / adults / pregnant women |
| setting | run parameter | routine immunization / outbreak campaign |

Two things follow:

- `AGENTS.md` says the context bucket is "always one each, every tool." That
  becomes "every tool that reads a document." Amend it rather than bending
  Librarian to fit.
- `available_configs()` returns `(org, source_type, intervention_class)` triples.
  With no document type there is no triple to look up, so config selection reduces
  to org plus intervention class. Decide whether that is a second lookup function
  or a widening of the existing one.

Note that population and setting are load-bearing in a way Scout's date is not.
Scout's window narrows an existing result; these two **define what "comparable"
means**. Pick them too narrowly and the result is one comparator presented as a
range.

### 5. The index is the project; the tool is the part on top

"Vaccine, infants, routine immunization" requires the library to be tagged by
population and setting. If it is not already, something has to read all thirty
documents and extract those facets — Chunker plus a model pass, run once,
versioned, stored. That is a build-time asset, not a per-run cost.

Scope the work that way before committing to a timeline: the per-run tool is
comparatively small, and estimating it as though the index were free will be
wrong by most of the effort.

## Design constraints to carry into the build

- **Small N will read as authority.** Filter thirty documents to vaccine +
  infants + routine and there may be three matches. A central value derived from
  three is the kind of statistic that gets quoted in a governance review. Show N
  and every individual cited value; never synthesize a typical one. This is the
  same discipline as Scout refusing to blend its axes into a score, and it follows
  directly from "nothing is judged."
- **Citations must resolve.** Every value points at an exact block in a named
  source document. That is the property that makes the output checkable and the
  reason it can be trusted without a verdict attached.
- **`RunPanel` requires at least one file.** See the `complete` check in
  `web/components/run-panel.tsx` — it deliberately refuses to enable Run with zero
  attached documents. Librarian needs zero slots to be a valid state, which is a
  small, contained change to that component.
- **New result type.** Librarian needs its own `ANALYSIS_VERSIONS` entry in
  `web/lib/result-file.ts`, its own `assertLibrarianReadable` in
  `web/lib/result-contracts.ts` (the `satisfies` map there will refuse to compile
  without it), and its own legend in `services/assistant/legends.py` — including,
  explicitly, that it reports rather than judges, so Ask does not present a
  reported value as a finding.

## Open product questions

- Does "comparable" ever need to cross intervention classes? Two vaccines for
  different indications are comparable; is a vaccine ever usefully compared to a
  monoclonal for the same population?
- Which attributes are indication-independent for each of the five intervention
  classes? This is a vocabulary question, answered per class in
  `shared/attributes.yaml`, not a branch in the tool. Getting it wrong in one
  direction hides useful comparisons; in the other it presents an
  indication-specific number as though it generalized.
- Are IPDPs in scope for values, or only iTPPs and cTPPs? An IPDP states plan
  commitments rather than product attributes, which may make it a third partition
  rather than a source of attribute values.
- What happens when the library disagrees with itself — two cTPPs in the same
  class committing to incompatible shelf lives? Under "nothing is judged" both are
  shown, but the presentation has to make the disagreement legible rather than
  averaging it away.
- Is there a use for the reverse query: given an attribute value, which programs
  committed to it? Cheap once the index exists; do not build it speculatively.

## Where things are

| Concern | File |
|---|---|
| Card, description, and the no-authority note | `web/lib/tools.ts` |
| Overview group and its copy | `web/lib/tool-sections.ts` |
| Order and placement invariants | `web/lib/tool-sections.test.ts` |
| Icon | `web/components/ui/pdis-icon.tsx` |
| The three-bucket configuration rule to amend | `AGENTS.md`, under Boundaries |
| The founding-split statement to extend | `AGENTS.md`, under Tool contracts |
| Zero-document run panel | `web/components/run-panel.tsx` |
| Result versioning and readability | `web/lib/result-file.ts`, `web/lib/result-contracts.ts` |
| Ask legend | `services/assistant/legends.py` |
