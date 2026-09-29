# Ask

Answer read-only questions from the client-held tool catalog, available
analyses and utility outputs, and their cited source material.

## Background

Ask is stateless. Every turn receives a workspace bundle, source blocks, and
conversation history. Canonical public process and architecture documentation
comes from `shared/product_knowledge.json`, the same source rendered by the web
documentation page. Users may add transient DOCX, PPTX, or image
attachments; these are parsed into ordinary source blocks and remain
conversation context rather than analysis evidence. Ask cannot mutate analysis
or start a new evidence search. Conversation text, loaded results, source blocks,
and attachments share the web client's in-memory workspace lifecycle.

## Usage

Import `answer_stream`, `StreamingChatLLMProtocol`, and `limits` from
`services.assistant`.

## Contract

| Direction | Value |
|---|---|
| Input | Workspace bundle, source blocks, conversation history, and an injected chat client |
| Output | Typed text/activity chunks; the API frames these as SSE |

Each question builds one workspace index from the bundle and blocks. The system prompt is a fixed prefix (rules, tool inventory, documentation map) followed by a bounded map of the workspace: the legends for held result types, each result and the documents it read, and each document's block count, headings and visual locations. No image is in the prompt. The bounded tool loop reaches everything else by exact ID: product documentation, result trees, document text by block or range, retained visuals through `view_document_visuals` (capped per call and per question), and the full text behind URLs the analyses already cite. Product documentation explains PDIS and is never treated as product evidence. The workspace legend is always present, so the map's own labels are defined even when no final result is held; a tool's legend is added only when the workspace holds a result of that type, and an active Scout review draft adds Scout's legend and the draft's own. A mounted Scout checkpoint supplies its draft and selected item separately as `active_review`, with retained source blocks through the same readers. This context is read-only, is not a final result or skill prerequisite, and disappears when the checkpoint unmounts. It is not added to exported results; the server stores no review session. Draft blocks and their references receive chat-only aliases so revised same-name uploads cannot replace final-result sources; canonical IDs remain in block metadata and stored results are untouched.
Context changes preserve the conversation, attachments and unsent text. Each question
captures a client-held snapshot: an in-flight reply finishes against that snapshot,
and its citations continue to resolve against the same source blocks and URL set.
The next question captures the latest workspace. Earlier turns are marked as historical
in the submitted conversation, never supplied as current evidence; old answers are
also labelled in the UI. Only the current turn's source collection is sent to the API.
New chat releases the conversation snapshots and attachments. Nothing is stored
server-side or added to portable result files. The API
exposes `POST /api/assistant/ask/stream`. The
floating panel and `/ask` page are two views of the same client-held workspace
context and conversation component.

The OpenAI adapter uses Responses for tool-capable chat. It emits the shared
`ChatDelta`/`ChatTurn` contract, so the agent executes completed calls rather than
parsing provider deltas. Completed provider output (including encrypted reasoning)
is carried opaquely between tool steps within the request, with `store=False` and
no provider session IDs. Every image reaches the model labelled `Visual for document block [id]:`, the same label the tool pipelines use (`shared/visuals.py`).

The SSE boundary sends `done` only on success and a sanitized `error` event on
failure. The browser treats a stream ending without `done` as interrupted, and
shows failures outside the answer text; provider diagnostics remain server-side.

## Development

- `workspace.py` — Everything one request holds, indexed once.
- `sources.py` — What every reachable kind of content shares: how it is found, shown and cut short.
- `limits.py` — Every cap the Assistant enforces, in one place.
- `prompt.py` — The Assistant's system prompt: a fixed prefix, then a bounded map of this workspace.
- `protocols.py` — What the Assistant needs from a model client: one streamed, tool-capable turn.
- `registry.py` — The catalog of capabilities: what the Ask agent can reach, one entry per capability with its schema, handler and label.
- `resources.py` — The types a capability is declared with (`Resource`, `Verb`), and what is derived from them: tool schemas, verb lookup and the prompt's inventory.
- `document.py` — The documents source: find, read, page and view parsed blocks by exact ID.
- `navigator.py` — The results source: a compact map of every held result, then exact paths on demand.
- `web_sources.py` — Opening a source an analysis already cites: allow-list and public-address checks, then text.
- `knowledge.py` — Read-only navigation over the canonical public PDIS documentation.
- `skills.py` — Procedures the assistant can follow, declared as files rather than prompt text.
- `legends.py` — Per-result-type semantic legends for the Ask assistant.
- `priorities.py` — One read over a finished result: what its priorities add up to, and what they miss.
- `agent.py` — Ask: a read-only, grounded agent loop over one request's workspace.
