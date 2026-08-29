# Archivist

Read what the Foundation's own product profiles have said before.

## Background

Archivist is the one workspace tool that judges nothing. Inspector holds a document
to a rubric, Scout to external evidence, Aligner to another document, and Screener to a
gate's question bank — each returns a verdict against an authority. Archivist's
authority is the corpus itself, and a corpus is data rather than judgment, so what it
returns is a selection of rows plus counts a reader could recompute from them. There is
no score, no ranking, and no reconciliation between two documents.

The work is split in two, and the split is the whole design:

| | what it is | when it runs |
| --- | --- | --- |
| **Build** | Reads the archive with a model, verifies every reading against the document, and writes a committed artifact | Offline, rarely, reviewed by a person before anyone relies on it |
| **Read** | Filters and groups the committed rows | Per request, with no model call at all |

Static rather than built on demand because every row is a model's reading of a
confidential document. Nobody should be shown "24 months, cited to block b-0042" before
a person has read that line and agreed with it, and a tool that extracted on request
would put an unreviewed reading in front of someone at the moment they trusted it most.

## The corpus

Two collections on two axes that never mix, and nothing denormalized between them:

- `documents` — one entry per source file, carrying exactly the header a run would pick.
- `records` — one entry per document × attribute × bound × condition.

A document's population tag is derivable from its own records, and deriving it on read
is the rule the rest of the suite follows for counts: a stored copy is a second authority
that can disagree with the thing it came from.

The grid is **exhaustive, not sparse**. Every document has a row for every indexed
attribute, including the ones it never mentioned. That is what makes "eleven of twelve
profiles never specified thermostability" answerable, which is often the most useful thing
an archive can say when drafting from scratch. A missing row would read as silence and
mean "we never found out".

### What a row may say

Three planes, and a value from one never lands in another:

```
what question   attribute, bound, condition_attribute, condition_stated
what answer     status, stated, magnitude, unit, tags
where it came   quote, block_id, block_text, section_label
```

`status` is `stated`, `not_stated`, or `uncertain`. The last is the gap a verbatim check
cannot close: a quote that really appears in the block can still be the wrong sentence for
this attribute, so the reading is kept, flagged, and reviewed rather than either trusted or
thrown away.

The **provenance chain** is what makes the artifact unfalsifiable rather than merely
well-reviewed: `stated` sits inside `quote`, which sits inside `block_text`. The outer link
rules out a fabricated sentence; the inner one rules out a paraphrase, which is the likelier
error — a model asked for a shelf life will answer "about two years" from a document that
wrote "24 months", and the two are not interchangeable when the archive is quoted back to a
partner. Both links are checked at build time *and* on every load, so a hand-edited row
cannot be served.

`magnitude` and `unit` are parsed from `stated` in code and **never converted**. "2 years"
is `(2, "years")`, not 24 months: canonicalising would put a number in the corpus that no
document wrote, on an axis nobody declared. Anything ambiguous — a range, a compound
presentation — parses as nothing, and `stated` still carries the full value.

## Indexed attributes

A TPP states thirty-six attributes; the corpus indexes eight. An attribute earns a column
only if a person drafting a new profile would ask "what have we said about this before",
and only if the answer is short enough to compare across documents. `safety` fails the
second test: every document says something, no two say it commensurably, and a column of
paragraphs is nothing a reader can compare.

Each column names the sibling attributes it is **not**, by attribute name rather than as
prose. A field defined only by its name will absorb anything adjacent to it — ask a model
for a shelf life and it will hand back a storage temperature, because both are printed
under "Stability". Naming the siblings means the prompt quotes the shared vocabulary's own
definition of each, and a renamed or deleted sibling fails a test instead of quietly
becoming a stale sentence in a prompt.

A column is filterable exactly when it declares `tags`. That is one axis, not two: a
separate flag saying the same thing would be free to disagree with the vocabulary.

Vaccine only in v1. `MISSING_INDEXED_CLASSES` records the other classes and what choosing
their columns would take — the drug split differs (stability and shelf life are one
attribute there, two here), and shipping a guessed column set would put unreviewed
judgment in a file that reads like a declaration.

## Building

```sh
.venv/bin/python scripts/build_archivist_corpus.py --documents ~/corpus-docs
```

The input is a folder of source documents plus
[`corpus/manifest.yaml`](corpus/manifest.yaml). The manifest declares, per file, only what
a person reads off a cover page and whose error would otherwise be invisible — most of all
`source_type`, because mislabelling a cTPP as an iTPP silently turns one candidate's
commitment into a class-level ambition in every value below it, and no downstream check
would notice. Everything else about a document is extracted from its prose and checked
against a quote.

Three phases, each one flat pool of independent work:

1. **parse** — one job per document, grouped by document type because chunker's batch entry
   point takes one parsing config at a time.
2. **extract** — one job per (document, attribute), the finest independent unit. The eight
   jobs for one document share a cached prompt prefix, which is why the document precedes
   the attribute in the request rather than following it.
3. **classify** — one job per extracted value of a filterable column, reading the value
   alone rather than the document. Separate from extraction so a tag vocabulary can grow
   without re-reading every document.

Flat rather than nested: a pool over attributes inside a pool over documents multiplies
into a concurrency nobody declared, and it is the first thing to hit a provider rate limit.

Everything checkable is checked before a single model call. A build that fails on its
fortieth document because one manifest row named an unparseable document type has spent
real money to learn what a file read would have said. Use `--dry-run` to stop after that
validation.

The build writes `corpus/corpus.json` and `corpus/build_report.json`. **Both are
gitignored today**, and that is a safety guard rather than a change of design: the corpus
carries verbatim quotes and whole blocks of BMGF product documents, so it must not reach a
remote that is not private. Lift the two lines in `.gitignore` once it is, and review
happens in a diff as intended — until then a build stays local and review means diffing
two local builds.

Read the report before trusting the corpus: it carries the two numbers the corpus cannot, because a
discarded reading leaves no row — how many quotes were not found in the document, and how
many values paraphrased their own quote.

## Reading

```python
from services.archivist import CorpusQuery, TagFilter, load_corpus, run_query

answer = run_query(
    load_corpus(),
    CorpusQuery(
        intervention_class="vaccine",
        attributes=("vaccine.shelf_life",),
        tags=(TagFilter("vaccine.target_population", ("infants",)),),
    ),
)
```

A tag filter selects **documents**, not rows: a reader narrowing by population wants the
shelf lives of the profiles written for infants, not only their population row. Tags within
one filter are alternatives; separate filters must all match.

The answer nests by attribute, then by document type, then by state. **Values from
different document types are never merged** — an iTPP states a class-level ambition and a
cTPP states one candidate's commitment, and a number blending them describes neither
product. The nesting is what makes that unrepresentable rather than merely discouraged. For
each attribute, every matched document appears in exactly one of `values`, `uncertain`, or
`silent`, so a count is a count.

## Boundaries

Archivist imports nothing from `services/scout` or `services/searcher`, and a test enforces
it. The resemblance is superficial: both read documents and both cite blocks, but Scout
judges a target against outside evidence and this judges nothing. It also avoids their
nouns — `facet` is Searcher's and `ledger` is Scout's — because sharing a word for a
different mechanism is how two unrelated things come to look like one.

What it does share is the shared vocabulary: `shared/attributes.yaml` declares itself
unowned by any service, and `shared.vocabulary.attribute_definitions` is the one reader of
it, so Scout and Archivist cannot disagree about what an attribute means.
