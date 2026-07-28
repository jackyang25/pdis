# Ask

Answer read-only questions from the client-held tool catalog, available
analyses and utility outputs, and their cited source material.

## Background

Ask is stateless. Every turn receives a workspace bundle, source blocks, and
conversation history. Users may add transient DOCX, PDF, PPTX, or image
attachments; these are parsed into ordinary source blocks and remain
conversation context rather than analysis evidence. Ask cannot mutate analysis
or start a new evidence search.

## Usage

Import `answer`, `answer_stream`, `ChatLLMProtocol`, and
`StreamingChatLLMProtocol` from `services.assistant`.

## Contract

| Direction | Value |
|---|---|
| Input | Workspace/result JSON, context type, source blocks, conversation history, and an injected chat client |
| Output | One answer or a plain-text token stream |

The bounded tool loop can traverse the submitted catalog and result trees, find
and page exact document blocks, inspect retained visuals, and fetch only URLs
cited by the submitted analyses. The API exposes `POST /api/assistant/ask` and
`POST /api/assistant/ask/stream`. The floating panel and `/ask` page are two
views of the same client-held workspace context and conversation component.

## Development

`agent.py` owns orchestration, `navigator.py` owns result traversal and URL
enforcement, `document.py` owns block access, and `legends.py` owns result
semantics.
