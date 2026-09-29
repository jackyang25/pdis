# Assistant context harness: unified indexing and on-demand retrieval

Status: draft for review · 2026-09-29

## Intent

The PDIS Assistant (Ask) answers slowly when the workspace holds image-heavy documents —
most visibly Screener runs over several slide decks. The goal is an assistant harness that
stays fast and faithful however many documents, results and conversation turns the
workspace holds: a small map in the prompt, everything else reached by exact ID through one
registry, and one implementation of each mechanic rather than one per content kind.

Success means:

- Prompt size is bounded by the number of held results and documents, never by the length of
  a document or the number of images in it.
- Every passage and image the request carries remains reachable by its exact ID; citations
  resolve exactly as they do today.
- Several documents and several results stay distinct; a review draft stays separate from a
  final result.
- One source interface, one limits module, one image-labelling helper, one registry.
- Measured before/after: model calls, input tokens, and images viewed per question.

## Scope boundary

This is a change to the Assistant alone: `services/assistant/`, the Ask route and schemas in
`api/`, the chat panel and its libraries in `web/`, and the documentation that describes them.
No tool pipeline, configuration, result shape, saved-result contract, or tool page changes.
The one shared file touched, `shared/openai_client.py`, gains the ability to carry images in a
tool output and has its image-labelling code extracted into a helper whose output for the tool
pipelines is unchanged and pinned by a test.

## What is wrong today

Findings from the audit of `services/assistant`, `api/routes/assistant.py`, `shared/`
and `web/components/assistant`.

1. **Every image, every call.** `agent.py:_initial_messages` (≈164-204) attaches every image
   block in the request at `detail: "high"` before any tool runs. The loop re-sends the whole
   working list on up to 7 calls per question (`MAX_STEPS = 6` plus the forced final answer).
   No tool returns an image; `read_document` on a visual block returns the `"[image]"`
   placeholder. Text, by contrast, is reached only through capped tools.
2. **Duplicate images.** `web/lib/assistant-review-context.ts` renames draft block IDs to
   `review:<owner>/<id>`, so a Scout review and a final result over the same document send the
   same images twice. The block map in `workspace-ask.tsx` deduplicates only identical IDs.
3. **Per-tool legends never reach the model.** The web always sends `result_type:
   "workspace"`, so `legend_for` returns only `WORKSPACE_LEGEND`. `SCREENER_LEGEND`,
   `INSPECTOR_LEGEND`, `ALIGNER_LEGEND` and `SCOUT_LEGEND` are unreachable, and with them the
   exact meaning of each tool's states. Two are also stale: Aligner is described as symmetric,
   and Screener as DOCX/PPTX only.
4. **Four copies of one mechanic.** `navigator`, `document`, `knowledge` and `skills` each
   implement overview / find / read with their own hit caps, snippet windows, truncation
   markers and "unavailable" messages.
5. **Limits in about eight places.** `agent.py`, `navigator.py`, `document.py`,
   `knowledge.py`, `registry.py` (`maximum: 25` beside `MAX_RANGE_BLOCKS`), the web's four
   literal `5`s for attachments, and `session.ts`.
6. **Two image-labelling functions** with different wording: `agent.py` and
   `shared/openai_client.py:_user_content`. AGENTS.md requires every multimodal call to label
   an image with its exact block ID.
7. **Unreachable code.** The non-workspace prompt branch, per-tool suggestion sets, `ChatLLMProtocol.chat` / `OpenAIClient.chat`, the `!hasResult` UI branches,
   the Inspector top-level `priority_digest` that is always undefined.
8. **Safety and limits.** `AskMessage.role` is a free string forwarded to the provider, so a
   client can inject `system` or `developer` messages. No request body, block, or image limits.
   The SSE stream sends nothing during a long reasoning step or a 20 s `fetch_source`.
9. **Structure.** `agent.py` holds provider protocols, the loop and the prompt builder, with a
   mid-file import of the private `_VERBS`. `navigator.py` mixes JSON navigation with outbound
   HTTP. `knowledge.load()` and `skills.available_skills()` re-read files on every call. The Ask
   prompt is not published in `shared/prompt_reference.json`.
10. **Documentation says otherwise.** `shared/product_knowledge.json`,
    `services/assistant/README.md` and AGENTS.md describe images as read on demand.
11. **Old conversation snapshots pin old workspaces.** `ask.tsx` stores an `AskContext` per
    question; when the workspace changes mid-chat, the old snapshot keeps the old blocks and
    image bytes alive until New chat, only to validate the old answer's links.

## Design

Four layers, each with one job.

```text
request (bundle + blocks)
  → 1. WorkspaceIndex        what exists: documents, results, visuals, deduplicated
  → 2. Map (system prompt)   what the model always sees: bounded, stable prefix first
  → 3. Sources → Registry    what the model can reach: one interface, one tool catalog
  → 4. Loop + adapter        how turns, tool outputs and images travel; budgets enforced
```

### 1. WorkspaceIndex — built once per request

New module `services/assistant/workspace.py`. Pure, built from the request's analysis bundle
and block list, never persisted.

- **Documents**, keyed by each block's `doc_id`, in first-appearance order, each holding its
  blocks in ordinal order.
- **Blocks** by exact ID. A repeated ID is kept once.
- **Visuals**: every block with an image, with its location (`structural_meta.page` or
  `slide`), `visual_scope`, and `image.sha256`. Image bytes are held once per `sha256`;
  several blocks may point at one image. This is what removes the review duplicate without
  changing its renamed IDs, which stay distinct addresses.
- **Results**: each `results[]` entry's id, `result_type`, label, and the documents its
  `document_block_ids` fall in. `active_review`, when present, is a result-like entry marked
  as a draft. `conversation_attachments[]` are marked as user-supplied documents.
- **Held result types**, computed once (today computed twice).

The index answers the questions the map and the sources ask. Nothing else walks the raw bundle.

### 2. The map — the bounded system prompt

The system prompt is rebuilt from named sections, ordered so the part that never changes
comes first. Provider prompt caching reuses an identical prefix across the loop's calls and
across questions.

Static prefix (identical for every request):

1. Role and grounding rules (today's text, with the non-workspace branch removed).
2. Answering and citation rules.
3. Tool inventory, generated from the registry.
4. Product documentation table of contents.

Per-request tail:

5. **Legends for held result types only**, plus the review legend when a draft is present.
   The legends are corrected: Aligner is directional per declared edge; Inspector holds peer
   reviews; Screener accepts PDF as well; blocks live in the document collection, not the
   analysis. `WORKSPACE_LEGEND` keeps the bundle shape and loses its per-tool summaries, which
   the legends now own.
6. Skills index for the held types.
7. **Workspace map** from the index:
   - each result: tool, label, draft or final, and the documents it read, followed by its
     analysis tree's structure two levels deep (field names and list sizes), capped at
     `MAP_LINES_PER_RESULT` lines. Today's overview walks every nested list of every held
     result, so a large Scout run alone puts hundreds of lines in every call; deeper
     structure is reached with `find_result` and `read_result`;
   - each document: block count, visual count, visual locations as compressed ranges
     ("slides 1–42, 45"), extraction warnings, headings capped at 20.

Nothing in the map grows with a document's length except the compressed visual ranges, which
grow with the number of gaps, not the number of slides. No image enters the prompt.

### 3. Sources and the registry — one interface, one catalog

New module `services/assistant/sources.py` defines the interface every reachable kind of
content implements:

```python
class Source(Protocol):
    key: str                                   # "results" | "documents" | "product_docs" | "skills"
    def overview(self, index: WorkspaceIndex) -> str: ...
    def find(self, index: WorkspaceIndex, query: str) -> Hits: ...
    def read(self, index: WorkspaceIndex, ids: list[str], **options) -> ToolOutput: ...
```

- Hits, snippets, truncation markers, empty-query and "unavailable" messages are produced by
  shared helpers in `sources.py`, from one limits module. Each source supplies data, not
  formatting.
- The existing `navigator`, `document`, `knowledge` and `skills` modules become the four
  sources. `fetch_source` moves out of `navigator` into `web_sources.py`, so outbound HTTP lives
  apart from JSON navigation.
- `knowledge` and `skills` load their files once per process.
- `registry.py` keeps its role — each capability declared once, schemas, activity labels and
  inventory generated — but its handlers call sources, and argument coercion uses one helper.

Tools after the change (names kept where they exist, so skills and tests stay valid):

| Source | Tools |
|---|---|
| results | `find_result`, `read_result` |
| documents | `find_document`, `read_document`, `read_document_range`, **`view_document_visuals`** (new) |
| product docs | `find_product_docs`, `read_product_docs` |
| skills | `find_skill`, `read_skill` |
| web sources already cited | `fetch_source` |

`view_document_visuals(block_ids)` returns the images for up to `MAX_VISUALS_PER_CALL`
blocks, each labelled with its exact block ID, together with the block's text and location so
the model reads image and text together. A request for a non-visual block returns its text
and says it has no image. A block ID not in the index is reported, never guessed.

### 4. The loop, tool outputs and images

- Handlers return a provider-neutral `ToolOutput(text: str, images: list[LabelledImage])`.
- One shared helper, `shared/visuals.py:labelled_image_parts`, builds the label and image part.
  It is extracted from `shared/openai_client._user_content` with that function's existing
  wording ("Visual for document block [id]:") unchanged, so every tool pipeline's model input
  stays byte-for-byte identical; a test pins the exact output. The Ask path adopts it, and its
  own wording ("Source-document visual for block [id]:") goes.
- The OpenAI adapter serialises a `ToolOutput` into `function_call_output`. If the Responses
  API refuses image content there, the adapter instead returns the text as the tool output and
  appends one user message with the labelled images before the next call. The choice is made
  and tested inside the adapter; the agent does not know which path ran. Verification against
  the direct OpenAI endpoint is the first implementation step.
- **Budgets**, enforced in the loop from the limits module: at most `MAX_VISUALS_PER_CALL`
  images per tool call and `MAX_VISUALS_PER_QUESTION` per question. A call that would exceed the
  question budget returns what fits and states how many were withheld, so the model says which
  slides it viewed rather than implying it saw them all.
- `agent.py` splits into `protocols.py` (provider protocols), `prompt.py` (the map), and
  `agent.py` (the loop). No mid-file imports; nothing imports a private name across modules.

### Limits — one module

`services/assistant/limits.py` holds every cap: steps per question, output tokens, find hits
per source, snippet window, characters per block and per call, blocks per range, visuals per
call and per question, fetch size and timeout. Schemas read from it (the `maximum: 25` literal
goes). The web's attachment limit becomes one named constant in `web/lib/document-formats.ts`.

### Conversation and the browser

- The server stays stateless. Each question sends the current workspace; history is text,
  with earlier turns marked historical, as today.
- Lookups are not carried between questions; the model looks again when a follow-up needs it.
- **Snapshot garbage:** the per-question `AskContext` keeps only what an earlier answer needs
  to render and validate its links — the cited-block lookup (IDs, text excerpt, location) and
  the URL allow-list — not the block list with image bytes. The current question alone holds
  the full workspace.

### Request validation and safety

- `AskMessage.role` becomes `Literal["user", "assistant"]`.
- `AskRequest` gains limits from the limits module: message count, block count, image count
  and total image bytes. Exceeding one returns 413 with a plain reason before the stream opens,
  per the rule that an invalid request fails the request rather than arriving as an error event.
- The SSE stream emits a comment heartbeat (`: ping`) every 15 s, matching `api/streaming.py`,
  so a long reasoning step or fetch never looks like a dead connection. The browser's reader in
  `web/lib/assistant-transport.ts` ignores comment lines, and a test pins that it does.
- `fetch_source` keeps its allow-list and public-address checks unchanged.

### Observability

One structured log line per question: model calls, input and output tokens as reported by the
provider, cached input tokens, visuals viewed, visuals withheld by budget, tools called. No
content, no block text, no user text.

### Documentation

- `shared/product_knowledge.json` and `services/assistant/README.md` describe the harness as it
  now is: map, sources, on-demand visuals, budgets.
- AGENTS.md's Ask section states the rule this spec introduces: the prompt carries a bounded map;
  every source document block, including each image, is reached by exact ID through the
  registry; no image enters the prompt unrequested.
- Stale docstrings noted in the audit are corrected (`agent.py` header, the non-existent `/ask`
  route, `AskRequest.result_type`, `OpenAIClient` class docstring).

### Dead code removed

The non-workspace prompt branch and `legend_for`'s fallback; `ChatLLMProtocol.chat` and
`OpenAIClient.chat`; `ask.tsx`'s per-tool `SUGGESTIONS`,
`DEFAULT_SUGGESTIONS`, the `!hasResult` branches and the single-result placeholder; the
Inspector top-level digest fields in `workspace-ask.tsx`; the unreachable `except
HTTPException` in the digest route; `resources.activity_for` rebuilding the dispatch table.

## Combinations the design must hold

| Workspace | Map shows | Model reaches |
|---|---|---|
| Nothing held | "No results held"; catalog | Product docs, skills index |
| Attachments only | Attachments as user-supplied documents | Documents source |
| One result, one document | Result, its document, visual ranges | All sources; visuals on request |
| Screener over four decks, plus Inspector on one of them | Two results; four documents listed once; each result lists its documents | Shared document reached once by ID |
| Scout review draft plus final Scout result on the same document | Draft and final as separate entries | Distinct block IDs; one copy of each image by `sha256` |
| "What does the chart on slide 12 show?" | — | `view_document_visuals` on that block |
| "Summarise every slide" | — | Text by range; visuals up to the question budget, withheld count stated |
| Follow-up question | Same map from the current workspace | Looks up again as needed |
| Workspace changes mid-chat | New map | Old answers keep their citation lookup only |

## Testing

Python (`tests/`):

- The initial messages contain no image part, for any workspace.
- The map for a 200-slide document is within a fixed size and lists visual ranges.
- A workspace mixing Screener over several decks, Inspector over one of them, and a Scout
  draft: every block and image is reachable by exact ID; each result maps to the right
  documents; draft and final stay separate; an image shared by a draft and a final result is
  held once.
- `view_document_visuals` labels every image with its exact block ID, reports unknown IDs,
  and enforces both budgets with a stated withheld count.
- Legends present equal the held result types; the corrected legend texts.
- Each source's find and read use the shared caps and markers.
- `AskMessage.role` outside user/assistant is refused; oversize requests return 413 before
  streaming; the heartbeat is emitted.
- The adapter serialises `ToolOutput` with images both ways (native output and fallback).
- Existing tests that import private names move to the public surface.

Web (`web/lib/*.test.ts`):

- An earlier question's snapshot holds no image bytes and still resolves its citations.
- The attachment limit comes from one constant.
- The SSE reader ignores heartbeat comment lines without producing a text or activity part.
- Existing conversation, continuity, review-context and citation tests still pass.

Verification before completion: Python suite, all web `test:*` scripts, typecheck, production
build, `git diff --check`, and one measured before/after run of a Screener multi-deck question
using the observability log.

## Out of scope

- Moving the priority digest from Chat Completions to Responses, and its error sanitisation.
- Placing Ask, the digest and `/context` under `run_slot` capacity.
- Avoiding the browser's per-question upload of image bytes. Doing so needs server state, which
  the stateless rule forbids; the model-side cost is the one this spec removes.
- Routing `/context` uploads through `api/uploads.document_upload_parts` and its `doc_id` scheme.
- Publishing the Ask system prompt in `shared/prompt_reference.json`. It needs a prompt catalog
  entry wired into the documentation page's workflow graph and anchors, which is its own change.
- Pinning `fetch_source`'s connection to the address it validated (a possible DNS-rebinding gap
  the audit flagged as unverified). Separate security hardening.

## Open questions

1. Does the Responses API accept image content in `function_call_output` on the direct
   endpoint? Verified first; the fallback is designed either way.
2. Values for `MAX_VISUALS_PER_CALL` and `MAX_VISUALS_PER_QUESTION`. Proposed starting values:
   6 and 16, revisited against the measured log.
