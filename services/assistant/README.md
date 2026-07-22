# Ask

Read-only, grounded chat over an existing Inspector, Aligner, or Scout result
and its parsed source document or documents.

## Contract

| | |
|---|---|
| Input | Result JSON, result type, parsed `ContentBlock[]`, conversation history, injected chat client |
| Output | One answer string or a plain-text token stream |

Ask is stateless. The client sends the complete analysis context and
conversation history on every turn. Ask never mutates a result and never starts
a new evidence search.

## Available navigation

The internal tool loop can:

- inspect a JSON subtree by path;
- find keys/values in the analysis;
- find and page exact source-document blocks;
- read ordered document ranges;
- receive retained visuals labeled with exact block IDs; and
- fetch full text only for URLs already present in the result.

The source URL allowlist is derived deterministically from the submitted result.
`fetch_source` cannot open an arbitrary URL and is not a search tool.

## Streaming

The API exposes:

- `POST /api/assistant/ask` — JSON response;
- `POST /api/assistant/ask/stream` — plain-text streaming response.

Tool calls remain server-side. Only final answer tokens stream to the browser,
where the AI SDK client manages message state.

## Files

| File | Purpose |
|---|---|
| `agent.py` | Bounded tool-calling loop, multimodal context, and streaming. |
| `navigator.py` | Read-only JSON navigation and cited-source URL enforcement. |
| `document.py` | Bounded search and paging over parsed blocks. |
| `legends.py` | Result-type semantics supplied to the model. |
| `__init__.py` | Public package contract. |

## Public contract

Consumers import only `answer`, `answer_stream`, `ChatLLMProtocol`, and
`StreamingChatLLMProtocol` from `services.assistant`.
