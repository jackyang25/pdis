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

Import `answer_stream`, `ChatLLMProtocol`, and
`StreamingChatLLMProtocol` from `services.assistant`.

## Contract

| Direction | Value |
|---|---|
| Input | Workspace/result JSON, context type, source blocks, conversation history, and an injected chat client |
| Output | Typed text/activity chunks; the API frames these as SSE |

The bounded tool loop can find and read canonical product documentation,
traverse the submitted catalog and result trees, find and page exact document
blocks, inspect retained visuals, and fetch only URLs cited by the submitted
analyses. Product documentation explains PDIS and is never treated as product
evidence. Semantic legends define compact runtime labels even when no eligible
final result is present; they do not expose an active review draft. The API
exposes `POST /api/assistant/ask/stream`. The
floating panel and `/ask` page are two views of the same client-held workspace
context and conversation component.

The OpenAI adapter uses Responses for tool-capable chat. It emits the shared
`ChatDelta`/`ChatTurn` contract, so the agent executes completed calls rather than
parsing provider deltas. Completed provider output (including encrypted reasoning)
is carried opaquely between tool steps within the request, with `store=False` and
no provider session IDs. The tool registry and document-block labels are unchanged.

The SSE boundary sends `done` only on success and a sanitized `error` event on
failure. The browser treats a stream ending without `done` as interrupted, and
shows failures outside the answer text; provider diagnostics remain server-side.

## Development

`agent.py` owns orchestration, `knowledge.py` owns bounded public-documentation
access, `navigator.py` owns result traversal and URL enforcement, `document.py`
owns block access, and `legends.py` owns compact result semantics.
