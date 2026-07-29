# Ask

Answer read-only questions from the client-held tool catalog, available
analyses and utility outputs, and their cited source material.

## Background

Ask is stateless. Every turn receives a workspace bundle, source blocks, and
conversation history. Canonical public process and architecture documentation
comes from `shared/product_knowledge.json`, the same source rendered by the web
documentation page. Users may add transient DOCX, PDF, PPTX, or image
attachments; these are parsed into ordinary source blocks and remain
conversation context rather than analysis evidence. Ask cannot mutate analysis
or start a new evidence search. Conversation text, loaded results, source blocks,
and attachments share the web client's in-memory workspace lifecycle.

## Usage

Import `answer`, `answer_stream`, `ChatLLMProtocol`, and
`StreamingChatLLMProtocol` from `services.assistant`.

## Contract

| Direction | Value |
|---|---|
| Input | Workspace/result JSON, context type, source blocks, conversation history, and an injected chat client |
| Output | One answer or a plain-text token stream |

The bounded tool loop can find and read canonical product documentation,
traverse the submitted catalog and result trees, find and page exact document
blocks, inspect retained visuals, and fetch only URLs cited by the submitted
analyses. Product documentation explains PDIS and is never treated as product
evidence. Semantic legends define compact runtime labels even when no eligible
final result is present; they do not expose an active review draft. The API
exposes `POST /api/assistant/ask` and `POST /api/assistant/ask/stream`. The
floating panel and `/ask` page are two views of the same client-held workspace
context and conversation component.

## Development

`agent.py` owns orchestration, `knowledge.py` owns bounded public-documentation
access, `navigator.py` owns result traversal and URL enforcement, `document.py`
owns block access, and `legends.py` owns compact result semantics.
