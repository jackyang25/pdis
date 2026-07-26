# Ask

Answer read-only questions from a saved result and its cited source material.

## Background

Ask is stateless. Every turn receives the result, source blocks, and conversation
history. It cannot mutate analysis or start a new evidence search.

## Usage

Import `answer`, `answer_stream`, `ChatLLMProtocol`, and
`StreamingChatLLMProtocol` from `services.assistant`.

## Contract

| Direction | Value |
|---|---|
| Input | Result JSON, result type, source blocks, conversation history, and an injected chat client |
| Output | One answer or a plain-text token stream |

The bounded tool loop can traverse result JSON, find and page exact document
blocks, inspect retained visuals, and fetch only URLs cited by the submitted
result. The API exposes `POST /api/assistant/ask` and
`POST /api/assistant/ask/stream`.

## Development

`agent.py` owns orchestration, `navigator.py` owns result traversal and URL
enforcement, `document.py` owns block access, and `legends.py` owns result
semantics.
