# Priority card: one AI reading over the whole result

## Why

The old card copied items out of each result through a hand-written selector per tool
(`*-priorities.ts`), then asked a model to summarise the copy and nominate what it missed.
Each copy rebuilt names, quotes and sentences the tool's page already renders, and the
copies drifted: Scout named fields differently from its own Fields tab and quoted a
constructed label as document text, Inspector dropped the section, Aligner's IDs could
collide, and the card sat outside the source provider so its passage links opened nothing.
The tools' own sections already are the deterministic, ordered list; a second copy added
nothing a reader could not see below.

## What the card is now

When a result is opened, one schema-bound model call reads every finding in it and returns:

```json
{
  "summary": "what the result amounts to, naming the authority it was judged against",
  "points": [
    { "title": "short headline", "statement": "why it matters", "finding_ids": ["<id>", "..."] }
  ]
}
```

- `finding_ids` is a closed list of the result's own finding IDs (shared `reference_array`),
  at least one per point. A point is a pointer at findings, never a copy of one.
- At most five points; none is a valid answer for a result with nothing to raise.
- The card renders each point's linked findings by the names and verdict labels the tool's
  page already uses, and one source trigger over the passages those findings cite.
- Derived on open, held for the session, never stored or exported. Ask receives it.
- A failure is reported quietly with "Try again"; it is not retried on its own.

## Shared plumbing, per-tool lens

| Piece | Where | Owns |
|---|---|---|
| `PriorityFinding` shape, request builder | `web/lib/priorities.ts` | the one shape every tool maps into |
| per-tool lens | `web/lib/<tool>-priorities.ts` | which findings exist, named with the page's own label helpers, and one focus sentence |
| store + hook | `web/lib/priority-reading.ts` | one read per result per session, retry |
| card | `web/components/ui/priority-panel.tsx` | rendering only |
| reader | `services/assistant/priorities.py` | one prompt for every tool, schema, validation |
| route | `POST /api/assistant/priorities` | no tool table; everything tool-specific arrives in the request |

A finding is `{ id, subject, group, verdicts[], statements[], notes[], quote, blockIds }`:

| Tool | One finding is | `group` | `verdicts` | `statements` | `notes` (code-derived) |
|---|---|---|---|---|---|
| Inspector | rubric unit (selected rubric only) | section | verdict label | statement | — |
| Aligner | requirement | comparison | verdict label | statement | chain warning, when an earlier comparison flagged the passage |
| Scout | field | — | grounding, relation counts, precedent, each calibration target, each as its own entry | grounding reason, contradicting insights, precedent reason | — |
| Screener | gate question | discipline | state, requirement | statement, missing | — |

Scout's axes stay separate entries in `verdicts`; nothing blends them. Code-derived text
(Aligner's chain warning, Scout's comparator count) is a verdict or a note, never a statement,
so the model and the reader can tell what a model wrote.

All four tools show the card. Screener's old reason for declining (a gate question does not
fit the copied-item shape) no longer applies because nothing is copied.

## Removed

`PriorityItem`, `PRIORITY_LIMIT`, every `select*Priorities` selector, the order notes and
empty messages for the card, `priority_item_ids`, nominations, the digest-only prompt, and
`/api/assistant/priority-digest`.

## Unchanged

Pipelines, result shapes, analysis versions, saved and exported files, and each tool's own
sections (which remain the authoritative, code-ordered record).
