# Assistant Context Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Assistant reads a bounded map up front and reaches every result, passage and image by exact ID through one registry, so prompt size no longer grows with document length or image count.

**Architecture:** One `WorkspaceIndex` is built per request from the bundle and blocks. The system prompt is a static prefix plus a bounded per-request map. Four sources (results, documents, product docs, skills) share one set of helpers and one limits module; the registry derives every tool from them, including a new `view_document_visuals`. Tool outputs are provider-neutral `ToolOutput`s that may carry images, and the OpenAI adapter decides how they travel.

**Tech Stack:** Python 3.11, FastAPI, OpenAI Responses API; Next.js 16 / TypeScript, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-29-assistant-context-harness-design.md`

## Global Constraints

- Scope: `services/assistant/`, `api/routes/assistant.py`, `api/schemas.py` (Ask models only), `api/streaming.py` (one added helper), `shared/chat.py`, `shared/visuals.py` (new), `shared/openai_client.py`, `web/components/assistant/`, `web/lib/assistant-*.ts`, `web/lib/document-formats.ts`, docs. No tool pipeline, config, result shape or tool page changes.
- Every tool pipeline's model input stays byte-for-byte identical. The image label text is exactly `Visual for document block [<id>]:`.
- Tool names that exist today keep their names: `find_result`, `read_result`, `fetch_source`, `find_document`, `read_document`, `read_document_range`, `find_product_docs`, `read_product_docs`, `find_skill`, `read_skill`.
- No image part enters the initial messages of any Ask request.
- Server stays stateless: nothing is stored between requests.
- Limits: `MAX_VISUALS_PER_CALL = 6`, `MAX_VISUALS_PER_QUESTION = 16`, `MAP_LINES_PER_RESULT = 40`, `MAP_HEADINGS_PER_DOCUMENT = 20`, heartbeat every 15 s (`api/streaming.HEARTBEAT_SECONDS`).
- Do not commit. The user handles git; leave changes in the working tree.
- Python tests run in a container (the machine has no Python 3.11). Define once per shell:

```bash
cd /Users/jackyang/Desktop/pdis
PYTEST() { docker run --rm -v "$PWD":/src -w /src -v pdis-test-venv:/tmp/venv \
  -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e PYTHONPATH=/src python:3.11-slim \
  sh -c "pip install -q uv 2>/dev/null && uv sync --frozen --all-groups -q && uv run --frozen pytest $*"; }
```

  The named volume `pdis-test-venv` keeps the environment between runs. Web tests run locally from `web/` with `npm test`, `npm run -s test:<name>`, `npx tsc --noEmit`, `npm run build`.

## Review Focus

1. A workspace holding no documents at all (catalog only): the map must say so and every document tool must answer "not available", never raise.
2. A block whose `image` has bytes but no `sha256` (older saved results): the index must compute the hash rather than drop the image or collide on an empty key.
3. A model calling `view_document_visuals` with the same block ID twice, or with more IDs than the per-call cap: duplicates collapse, extras are reported, the budget counts each image once.
4. Two tool calls in one turn both returning images, on the follow-up fallback path: images must follow *all* the turn's `function_call_output` items, never sit between them.
5. The client disconnecting mid-answer while the heartbeat thread runs: the provider stream must still be closed.

Each is pinned by a test in the task that owns the code: 1 and 3 in Task 4, 2 in Task 3, 4 in Task 2, 5 in Task 7.

---

### Task 1: Limits module and shared source helpers

**Files:**
- Create: `services/assistant/limits.py`
- Create: `services/assistant/sources.py`
- Test: `tests/test_assistant_sources.py`

**Interfaces:**
- Produces: `limits.*` constants below; `sources.Hit(id, snippet, label="", note="")`; `sources.search_term(raw) -> str | None`; `sources.snippet(text, index, length) -> str`; `sources.render_hits(hits, cap) -> str`; `sources.truncate(text, limit, hint) -> str`; `sources.unavailable(what) -> str`; constants `EMPTY_QUERY`, `NO_MATCHES`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assistant_sources.py
"""One formatting for every source, so the four readers cannot drift apart again."""

import unittest

from services.assistant import limits, sources


class SourceHelperTests(unittest.TestCase):
    def test_empty_search_term_is_named_once(self):
        self.assertIsNone(sources.search_term("   "))
        self.assertIsNone(sources.search_term(None))
        self.assertEqual(sources.search_term("  Dose "), "Dose")

    def test_snippet_marks_elided_text_on_both_sides(self):
        text = "a" * 500 + "NEEDLE" + "b" * 500
        found = text.find("NEEDLE")
        snippet = sources.snippet(text, found, len("NEEDLE"))
        self.assertTrue(snippet.startswith("…") and snippet.endswith("…"))
        self.assertIn("NEEDLE", snippet)
        self.assertLessEqual(len(snippet), limits.SNIPPET_BEFORE + limits.SNIPPET_AFTER + 10)

    def test_hits_render_one_line_each_and_report_overflow(self):
        hits = [sources.Hit(id=f"b-{i}", snippet="text", label="Heading") for i in range(5)]
        rendered = sources.render_hits(hits, cap=3)
        self.assertEqual(rendered.count("\n- ["), 2)
        self.assertTrue(rendered.startswith("- [b-0] Heading: text"))
        self.assertIn("2 more matches", rendered)
        self.assertEqual(sources.render_hits([], cap=3), sources.NO_MATCHES)

    def test_truncation_says_how_to_continue(self):
        self.assertEqual(sources.truncate("short", 10, "narrow it"), "short")
        cut = sources.truncate("x" * 20, 10, "narrow it")
        self.assertTrue(cut.startswith("x" * 10))
        self.assertIn("[truncated; narrow it]", cut)

    def test_unavailable_names_what_is_missing(self):
        self.assertEqual(
            sources.unavailable("Source document"),
            "(Source document is not available in this workspace)",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST tests/test_assistant_sources.py -q`
Expected: FAIL with `ImportError: cannot import name 'limits'`

- [ ] **Step 3: Write the implementation**

```python
# services/assistant/limits.py
"""Every cap the Assistant enforces, in one place.

Schemas, readers, the loop and the API's request checks all read from here, so a
limit changes in one line and cannot disagree with its own schema.
"""

# The loop
MAX_STEPS = 6
MAX_OUTPUT_TOKENS = 4000

# Finding
MAX_FIND_HITS = 40
MAX_PRODUCT_DOC_HITS = 12
SNIPPET_BEFORE = 140
SNIPPET_AFTER = 220

# Reading
MAX_RESULT_CHARS = 12_000
MAX_BLOCK_CHARS = 60_000
MAX_READ_CHARS = 120_000
MAX_PRODUCT_DOC_CHARS = 16_000
MAX_RANGE_BLOCKS = 25

# Visuals. Per call bounds one tool result; per question bounds what one answer can cost.
MAX_VISUALS_PER_CALL = 6
MAX_VISUALS_PER_QUESTION = 16

# Cited web sources
MAX_FETCH_CHARS = 20_000
MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT_SECONDS = 20

# The map
MAP_LINES_PER_RESULT = 40
MAP_HEADINGS_PER_DOCUMENT = 20

# What one request may carry. Generous: they stop abuse, not real workspaces.
MAX_REQUEST_MESSAGES = 200
MAX_REQUEST_BLOCKS = 50_000
MAX_REQUEST_IMAGES = 5_000
MAX_REQUEST_IMAGE_CHARS = 300_000_000
```

```python
# services/assistant/sources.py
"""What every reachable kind of content shares: how it is found, shown and cut short.

Four sources implement the same three operations - results, documents, product
documentation and skills - each over a `WorkspaceIndex`:

    overview(index) -> str                 its lines in the map
    find(index, query) -> str              matches with exact IDs
    read(index, ids, ...) -> str | ToolOutput

The helpers below are the only place a hit, a snippet, a truncation or an absence is
worded, so the model meets one convention whichever source it reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import limits

EMPTY_QUERY = "(empty search term)"
NO_MATCHES = "(no matches)"


@dataclass(frozen=True)
class Hit:
    id: str
    snippet: str
    label: str = ""
    note: str = ""


def search_term(raw: Any) -> str | None:
    """A usable search term, or None when there is nothing to search for."""
    term = str(raw).strip() if raw is not None else ""
    return term or None


def snippet(text: str, index: int, length: int) -> str:
    """The text around a match, whitespace collapsed, with elisions marked."""
    begin = max(0, index - limits.SNIPPET_BEFORE)
    end = min(len(text), index + length + limits.SNIPPET_AFTER)
    body = " ".join(text[begin:end].split())
    return f"{'…' if begin else ''}{body}{'…' if end < len(text) else ''}"


def render_hits(hits: list[Hit], cap: int) -> str:
    if not hits:
        return NO_MATCHES
    lines = []
    for hit in hits[:cap]:
        line = f"- [{hit.id}]" + (f" {hit.label}" if hit.label else "")
        if hit.snippet:
            line += f": {hit.snippet}"
        if hit.note:
            line += f" ({hit.note})"
        lines.append(line)
    if len(hits) > cap:
        lines.append(f"…[{len(hits) - cap} more matches; search a narrower term]")
    return "\n".join(lines)


def truncate(text: str, limit: int, hint: str) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n…[truncated; {hint}]"


def unavailable(what: str) -> str:
    return f"({what} is not available in this workspace)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST tests/test_assistant_sources.py -q`
Expected: 5 passed

---

### Task 2: Provider-neutral tool outputs, one image label, usage

**Files:**
- Modify: `shared/chat.py`
- Create: `shared/visuals.py`
- Modify: `shared/openai_client.py` (`chat` removed; `_chat_input`, `_chat_turn`, `_user_content`)
- Test: `tests/test_openai_chat.py`, `tests/test_shared_visuals.py` (new)

**Interfaces:**
- Produces: `shared.chat.LabelledImage(block_id, media_type, data_base64)` with `.data_url`; `shared.chat.ToolOutput(text, images=())`; `shared.chat.Usage(input_tokens=0, cached_input_tokens=0, output_tokens=0)`; `ChatTurn.usage: Usage` (defaulted); `shared.visuals.labelled_image_parts(pairs: Iterable[tuple[str, str]]) -> list[dict]`; `shared.openai_client.TOOL_IMAGES: Literal["native", "follow_up"]`.
- A tool message in the working list is `{"role": "tool", "tool_call_id": str, "content": str, "images": tuple[LabelledImage, ...]}`; `images` may be absent.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_shared_visuals.py
"""The image label every model call uses. Tool pipelines depend on its exact text."""

import unittest

from shared.openai_client import _user_content
from shared.visuals import labelled_image_parts


class LabelledImageTests(unittest.TestCase):
    def test_label_names_the_exact_block_and_keeps_high_detail(self):
        self.assertEqual(labelled_image_parts([("deck/b-0004", "data:image/png;base64,AAAA")]), [
            {"type": "text", "text": "Visual for document block [deck/b-0004]:"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ])

    def test_tool_pipeline_payload_is_unchanged(self):
        # Byte-for-byte what `_user_content` produced before the helper was extracted.
        self.assertEqual(
            _user_content("Assess", [{"block_id": "d/b-1", "data_url": "data:image/png;base64,QQ"}]),
            [
                {"type": "text", "text": "Assess"},
                {"type": "text", "text": "Visual for document block [d/b-1]:"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QQ", "detail": "high"}},
            ],
        )
        self.assertEqual(_user_content("Assess", None), "Assess")
```

In `tests/test_openai_chat.py`:

1. Replace the second half of `test_tool_roundtrip_preserves_reasoning_call_ids_and_optional_schema` (from `provider.responses.create.return_value = ...` to the end of the test) with:

```python
        provider.responses.stream.return_value = ProviderStream(response(text_item("The title")))
        reply = list(client.chat_stream(messages + [
            {"role": "assistant", "content": "", "continuation": turn.continuation},
            {"role": "tool", "tool_call_id": "call_1", "content": "The title"},
        ]))[-1].turn
        self.assertEqual(reply.text, "The title")
        self.assertEqual(provider.responses.stream.call_args.kwargs["input"], [
            messages[0], reasoning, call,
            {"type": "function_call_output", "call_id": "call_1", "output": "The title"},
        ])
```

2. Replace `test_images_keep_their_exact_block_label_and_bytes` with:

```python
    def test_images_keep_their_exact_block_label_and_bytes(self):
        client, provider, _ = self.client(response(text_item("A plot")))
        list(client.chat_stream([{"role": "user", "content": [
            {"type": "text", "text": "Visual for [doc:block:3]"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA", "detail": "high"}},
        ]}]))
        self.assertEqual(provider.responses.stream.call_args.kwargs["input"][0]["content"], [
            {"type": "input_text", "text": "Visual for [doc:block:3]"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAAA", "detail": "high"},
        ])
```

3. Add these tests to `OpenAIChatTests`:

```python
    def tool_turn(self, *images_per_call):
        from shared.chat import LabelledImage
        messages = [{"role": "user", "content": "Look"}]
        for index, block_ids in enumerate(images_per_call):
            messages.append({
                "role": "tool", "tool_call_id": f"call_{index}", "content": f"out {index}",
                "images": tuple(LabelledImage(block_id, "image/png", "QQ") for block_id in block_ids),
            })
        return messages

    def test_tool_images_travel_inside_the_tool_output_natively(self):
        from shared import openai_client
        from shared.openai_client import _chat_input
        original = openai_client.TOOL_IMAGES
        openai_client.TOOL_IMAGES = "native"
        try:
            items = _chat_input(self.tool_turn(["d/b-1"]))
        finally:
            openai_client.TOOL_IMAGES = original
        self.assertEqual(items[1]["output"], [
            {"type": "input_text", "text": "out 0"},
            {"type": "input_text", "text": "Visual for document block [d/b-1]:"},
            {"type": "input_image", "image_url": "data:image/png;base64,QQ", "detail": "high"},
        ])

    def test_follow_up_images_come_after_every_output_of_the_turn(self):
        from shared import openai_client
        from shared.openai_client import _chat_input
        original = openai_client.TOOL_IMAGES
        openai_client.TOOL_IMAGES = "follow_up"
        try:
            items = _chat_input(self.tool_turn(["d/b-1"], ["d/b-2"]))
        finally:
            openai_client.TOOL_IMAGES = original
        self.assertEqual([item.get("type") for item in items[1:3]], ["function_call_output"] * 2)
        self.assertEqual(items[1]["output"], "out 0")
        follow_up = items[3]
        self.assertEqual(follow_up["role"], "user")
        labels = [part["text"] for part in follow_up["content"] if part["type"] == "input_text"]
        self.assertIn("Visual for document block [d/b-1]:", labels)
        self.assertIn("Visual for document block [d/b-2]:", labels)
        self.assertEqual(len(items), 4)

    def test_tool_output_without_images_stays_a_plain_string(self):
        from shared.openai_client import _chat_input
        items = _chat_input([{"role": "tool", "tool_call_id": "c", "content": "text"}])
        self.assertEqual(items, [{"type": "function_call_output", "call_id": "c", "output": "text"}])

    def test_usage_is_reported_with_the_turn(self):
        final = response(text_item("Hi"))
        final.usage = SimpleNamespace(
            input_tokens=1200, output_tokens=40,
            input_tokens_details=SimpleNamespace(cached_tokens=1024),
        )
        client, _, _ = self.client(final)
        turn = list(client.chat_stream([{"role": "user", "content": "Hi"}]))[-1].turn
        self.assertEqual((turn.usage.input_tokens, turn.usage.cached_input_tokens, turn.usage.output_tokens),
                         (1200, 1024, 40))

    def test_client_offers_no_non_streaming_chat(self):
        self.assertFalse(hasattr(OpenAIClient, "chat"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests/test_shared_visuals.py tests/test_openai_chat.py -q`
Expected: FAIL (`ModuleNotFoundError: shared.visuals`, `ImportError: LabelledImage`)

- [ ] **Step 3: Implement**

Append to `shared/chat.py`, and give `ChatTurn` a defaulted `usage`:

```python
@dataclass(frozen=True)
class Usage:
    """What one model call cost, as the provider reported it."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LabelledImage:
    """One retained document visual, never separated from the block it belongs to."""

    block_id: str
    media_type: str
    data_base64: str

    @property
    def data_url(self) -> str:
        return f"data:{self.media_type};base64,{self.data_base64}"


@dataclass(frozen=True)
class ToolOutput:
    """What a tool returns: text, and any images the model asked to see."""

    text: str
    images: tuple[LabelledImage, ...] = ()
```

`ChatTurn` becomes:

```python
@dataclass(frozen=True)
class ChatTurn:
    text: str
    tool_calls: tuple[ToolCall, ...]
    continuation: Any
    usage: Usage = Usage()
```

(Move the `Usage` class above `ChatTurn` so the default resolves.)

```python
# shared/visuals.py
"""The one way a document visual is labelled for a model.

AGENTS.md requires every multimodal call to label an image with its exact block ID.
Tool pipelines and the Assistant both build their image parts here, so the label has
one wording everywhere. Tool pipelines' prompts depend on this exact text.
"""

from __future__ import annotations

from typing import Any, Iterable


def labelled_image_parts(images: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    """`(block_id, data_url)` pairs as label-then-image content parts."""
    return [
        part
        for block_id, data_url in images
        for part in (
            {"type": "text", "text": f"Visual for document block [{block_id}]:"},
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
        )
    ]
```

In `shared/openai_client.py`:

- Delete the `chat` method (lines `def chat(` … `return _chat_turn(response)`).
- Change the class docstring to `"""OpenAI wrapper: structured calls, streamed tool chat, and web search."""`.
- Add near the top, after `DEFAULT_BASE_URL`:

```python
#: How images returned by a tool reach the model. "native" puts them inside the
#: function_call_output; "follow_up" sends the text there and the images in one user
#: message after the turn's outputs. Set by verification against the live endpoint.
TOOL_IMAGES: Literal["native", "follow_up"] = "native"
```

  (`Literal` is already importable from `typing`; add it to the import if absent.)

- Replace `_chat_input` with:

```python
def _chat_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate application messages once; replay completed provider items intact."""
    items: list[dict[str, Any]] = []
    pending: list[Any] = []  # follow-up images for the current run of tool outputs

    def flush() -> None:
        if pending:
            items.append({"role": "user", "content": [
                {"type": "input_text", "text": "Visuals returned by the tool calls above:"},
                *(_chat_content(part) for part in _image_parts(pending)),
            ]})
            pending.clear()

    for message in messages:
        if message["role"] == "tool" and message.get("continuation") is None:
            images = tuple(message.get("images") or ())
            output: Any = message["content"]
            if images and TOOL_IMAGES == "native":
                output = [{"type": "input_text", "text": message["content"]},
                          *(_chat_content(part) for part in _image_parts(images))]
            elif images:
                pending.extend(images)
            items.append({"type": "function_call_output",
                          "call_id": message["tool_call_id"], "output": output})
            continue
        flush()
        if message.get("continuation") is not None:
            items.extend(message["continuation"])
        else:
            content = message["content"]
            if isinstance(content, list):
                content = [_chat_content(part) for part in content]
            items.append({"role": message["role"], "content": content})
    flush()
    return items


def _image_parts(images: Iterable[Any]) -> list[dict[str, Any]]:
    return labelled_image_parts((image.block_id, image.data_url) for image in images)
```

- In `_chat_turn`, build usage and pass it:

```python
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    return ChatTurn(
        text=text, tool_calls=calls, continuation=output,
        usage=Usage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            cached_input_tokens=int(getattr(details, "cached_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        ),
    )
```

- Replace the body of `_user_content`'s list with the helper:

```python
    return [
        {"type": "text", "text": user_message},
        *labelled_image_parts((image["block_id"], image["data_url"]) for image in images),
    ]
```

- Imports: `from shared.chat import ChatDelta, ChatTurn, ToolCall, Usage`, `from shared.visuals import labelled_image_parts`, `from typing import ..., Iterable, Literal`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_shared_visuals.py tests/test_openai_chat.py -q`
Expected: all pass.

- [ ] **Step 5: Verify native tool images against the live endpoint**

This spends one small API call with the key in `.env`. Run inside the container with `.env` loaded:

```bash
docker run --rm -v "$PWD":/src -w /src -v pdis-test-venv:/tmp/venv --env-file .env \
  -e UV_PROJECT_ENVIRONMENT=/tmp/venv -e PYTHONPATH=/src python:3.11-slim sh -c \
  'pip install -q uv 2>/dev/null && uv sync --frozen -q && uv run --frozen python - <<EOF
import base64, io
from shared.openai_client import OpenAIClient
from shared.chat import LabelledImage
png = base64.b64encode(bytes.fromhex(
  "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
  "1f15c4890000000d49444154789c6360f8cfc0000003010100c9fe92ef0000000049454e44ae426082")).decode()
client = OpenAIClient()
tools = [{"type": "function", "function": {"name": "view", "description": "view",
          "parameters": {"type": "object", "properties": {}}}}]
first = list(client.chat_stream([{"role": "user", "content": "Call the view tool once."}], tools=tools))[-1].turn
call = first.tool_calls[0]
reply = list(client.chat_stream([
  {"role": "user", "content": "Call the view tool once."},
  {"role": "assistant", "content": "", "continuation": first.continuation},
  {"role": "tool", "tool_call_id": call.id, "content": "One image.",
   "images": (LabelledImage("probe/b-0001", "image/png", png),)},
]))[-1].turn
print("NATIVE OK:", reply.text[:80])
EOF'
```

Expected: `NATIVE OK: …`. If the provider rejects the request with an error about the `output` type, set `TOOL_IMAGES = "follow_up"` in `shared/openai_client.py`, rerun the command, and expect `NATIVE OK` again (the name refers to the probe, not the mode). Record which mode shipped in the comment above `TOOL_IMAGES`.

---

### Task 3: The workspace index

**Files:**
- Create: `services/assistant/workspace.py`
- Test: `tests/test_assistant_workspace.py`

**Interfaces:**
- Consumes: `shared.chat.LabelledImage`.
- Produces: `Visual(block_id, doc_id, location, sha256)`, `Document(doc_id, block_ids, visuals, headings, user_supplied)`, `ResultEntry(id, result_type, label, draft, doc_ids)`, `WorkspaceIndex` with fields `bundle, blocks, documents, results, held_result_types, allowed_urls, has_review` and methods `block(id)`, `document(doc_id)`, `blocks_of(doc_id)`, `image(block_id) -> LabelledImage | None`; `build_index(bundle: dict | None, blocks: list[dict] | None) -> WorkspaceIndex`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assistant_workspace.py
"""One index per request: every block, image and result reachable, nothing merged that differs."""

import hashlib
import unittest

from services.assistant.workspace import build_index


def block(doc, n, *, image=None, slide=None, page=None, heading=None):
    meta = {}
    if slide is not None:
        meta["slide"] = slide
    if page is not None:
        meta["page"] = page
    return {
        "id": f"{doc}/b-{n:04d}", "doc_id": doc, "ordinal": n, "block_type": "image" if image else "paragraph",
        "content": "[image]" if image else f"text {n}", "heading_stack": [heading] if heading else [],
        "section_label": None, "structural_meta": meta, "style_hint": {}, "image": image,
    }


def png(data="QQ", sha="s1"):
    return {"media_type": "image/png", "data_base64": data, "sha256": sha, "source_media_type": "image/png"}


def mixed_workspace():
    decks = [block("deckA", i, image=png(sha=f"a{i}"), slide=i) for i in range(1, 4)]
    decks += [block("deckB", i, image=png(sha=f"b{i}"), slide=i) for i in range(1, 3)]
    review = [dict(block("deckA", 1, image=png(sha="a1"), slide=1),
                   id="review:scout/deckA/b-0001", doc_id="Review draft · deckA")]
    bundle = {
        "catalog": [],
        "results": [
            {"id": "s1", "result_type": "screener", "label": "Gate", "analysis": {},
             "document_block_ids": [b["id"] for b in decks]},
            {"id": "i1", "result_type": "inspector", "label": "Inspect", "analysis": {"url": "https://x.org/a"},
             "document_block_ids": ["deckA/b-0001"]},
        ],
        "active_review": {"result_type": "scout", "phase": "target_review", "analysis": {},
                          "document_block_ids": [review[0]["id"]]},
    }
    return build_index(bundle, decks + review + [decks[0]])  # a repeated block


class WorkspaceIndexTests(unittest.TestCase):
    def test_every_block_is_reachable_once_by_exact_id(self):
        index = mixed_workspace()
        self.assertEqual(len(index.blocks), 6)
        self.assertEqual(index.block("deckB/b-0002")["doc_id"], "deckB")

    def test_documents_keep_their_order_and_locations(self):
        index = mixed_workspace()
        self.assertEqual([d.doc_id for d in index.documents], ["deckA", "deckB", "Review draft · deckA"])
        self.assertEqual([v.location for v in index.document("deckA").visuals], ["slide 1", "slide 2", "slide 3"])

    def test_each_result_maps_to_the_documents_it_read(self):
        index = mixed_workspace()
        by_id = {r.id: r for r in index.results}
        self.assertEqual(by_id["s1"].doc_ids, ("deckA", "deckB"))
        self.assertEqual(by_id["i1"].doc_ids, ("deckA",))
        self.assertEqual(index.held_result_types, frozenset({"screener", "inspector"}))

    def test_a_review_draft_stays_separate_from_final_results(self):
        index = mixed_workspace()
        draft = [r for r in index.results if r.draft]
        self.assertEqual([(r.id, r.doc_ids) for r in draft], [("active_review", ("Review draft · deckA",))])
        self.assertTrue(index.has_review)
        self.assertNotIn("scout", index.held_result_types)

    def test_an_image_shared_by_draft_and_final_is_held_once(self):
        index = mixed_workspace()
        final = index.image("deckA/b-0001")
        draft = index.image("review:scout/deckA/b-0001")
        self.assertEqual(final.block_id, "deckA/b-0001")
        self.assertEqual(draft.block_id, "review:scout/deckA/b-0001")
        self.assertIs(index.images_by_hash["a1"], index.images_by_hash["a1"])
        self.assertEqual(len(index.images_by_hash), 5)

    def test_a_missing_hash_is_computed_not_dropped(self):
        image = png(data="QUJD", sha="")
        index = build_index({"results": []}, [block("old", 1, image=image, page=4)])
        expected = hashlib.sha256(b"QUJD").hexdigest()
        self.assertEqual(index.document("old").visuals[0].sha256, expected)
        self.assertEqual(index.document("old").visuals[0].location, "page 4")
        self.assertIsNotNone(index.image("old/b-0001"))

    def test_attachments_are_marked_user_supplied(self):
        bundle = {"results": [], "conversation_attachments": [{"doc_id": "notes", "block_ids": ["notes/b-0001"]}]}
        index = build_index(bundle, [block("notes", 1)])
        self.assertTrue(index.document("notes").user_supplied)

    def test_cited_urls_come_from_analyses_only(self):
        index = mixed_workspace()
        self.assertEqual(index.allowed_urls, frozenset({"https://x.org/a"}))

    def test_an_empty_workspace_builds(self):
        index = build_index(None, None)
        self.assertEqual((index.documents, index.results, index.blocks), ((), (), {}))
        self.assertIsNone(index.image("anything"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST tests/test_assistant_workspace.py -q`
Expected: FAIL with `ModuleNotFoundError: services.assistant.workspace`

- [ ] **Step 3: Implement**

```python
# services/assistant/workspace.py
"""Everything one request holds, indexed once.

Built from the client's bundle and block list at the start of each question and never
kept. The map and every source read from here; nothing else walks the raw bundle.

Blocks are kept once by exact ID and images once by content hash, so a review draft's
renamed copy of a final result's document costs no second image. Documents are kept by
`doc_id`, which is why that draft stays a separate document: its blocks carry a
different one, so draft and final never blur.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from shared.chat import LabelledImage

REVIEW_PHASES = {"target_review", "evidence_review"}


@dataclass(frozen=True)
class Visual:
    block_id: str
    doc_id: str
    location: str
    sha256: str


@dataclass(frozen=True)
class Document:
    doc_id: str
    block_ids: tuple[str, ...]
    visuals: tuple[Visual, ...]
    headings: tuple[str, ...]
    user_supplied: bool


@dataclass(frozen=True)
class ResultEntry:
    id: str
    result_type: str
    label: str
    draft: bool
    doc_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceIndex:
    bundle: dict[str, Any]
    blocks: dict[str, dict[str, Any]]
    documents: tuple[Document, ...]
    results: tuple[ResultEntry, ...]
    held_result_types: frozenset[str]
    allowed_urls: frozenset[str]
    has_review: bool
    images_by_hash: dict[str, tuple[str, str]]
    _visual_hash: dict[str, str]

    def block(self, block_id: str) -> dict[str, Any] | None:
        return self.blocks.get(block_id)

    def document(self, doc_id: str) -> Document | None:
        return next((doc for doc in self.documents if doc.doc_id == doc_id), None)

    def blocks_of(self, doc_id: str) -> list[dict[str, Any]]:
        doc = self.document(doc_id)
        return [self.blocks[block_id] for block_id in doc.block_ids] if doc else []

    def image(self, block_id: str) -> LabelledImage | None:
        digest = self._visual_hash.get(block_id)
        if digest is None:
            return None
        media_type, data = self.images_by_hash[digest]
        return LabelledImage(block_id, media_type, data)


def build_index(bundle: dict[str, Any] | None, blocks: list[dict[str, Any]] | None) -> WorkspaceIndex:
    bundle = bundle if isinstance(bundle, dict) else {}
    by_id: dict[str, dict[str, Any]] = {}
    for block in blocks or []:
        block_id = str(block.get("id") or "")
        if block_id and block_id not in by_id:
            by_id[block_id] = block

    attachments = {
        str(entry.get("doc_id"))
        for entry in bundle.get("conversation_attachments") or []
        if isinstance(entry, dict) and entry.get("doc_id")
    }
    images: dict[str, tuple[str, str]] = {}
    visual_hash: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for block in by_id.values():
        grouped.setdefault(_doc_id(block), []).append(block)

    documents = []
    for doc_id, members in grouped.items():
        visuals = []
        headings: dict[str, None] = {}
        for block in members:
            if block.get("heading_stack"):
                headings[" > ".join(block["heading_stack"])] = None
            image = block.get("image")
            if not isinstance(image, dict) or not image.get("data_base64") or not image.get("media_type"):
                continue
            digest = str(image.get("sha256") or "") or hashlib.sha256(
                str(image["data_base64"]).encode()
            ).hexdigest()
            images.setdefault(digest, (str(image["media_type"]), str(image["data_base64"])))
            visual_hash[str(block["id"])] = digest
            visuals.append(Visual(str(block["id"]), doc_id, _location(block), digest))
        documents.append(Document(
            doc_id=doc_id,
            block_ids=tuple(str(block["id"]) for block in members),
            visuals=tuple(visuals),
            headings=tuple(headings),
            user_supplied=doc_id in attachments,
        ))

    results = [
        _entry(entry, by_id, draft=False)
        for entry in bundle.get("results") or []
        if isinstance(entry, dict) and entry.get("result_type")
    ]
    review = bundle.get("active_review")
    has_review = isinstance(review, dict) and review.get("phase") in REVIEW_PHASES
    if has_review:
        results.append(_entry({**review, "id": "active_review",
                               "label": f"Scout review draft ({review['phase']})"}, by_id, draft=True))

    return WorkspaceIndex(
        bundle=bundle,
        blocks=by_id,
        documents=tuple(documents),
        results=tuple(results),
        held_result_types=frozenset(r.result_type for r in results if not r.draft),
        allowed_urls=frozenset(_urls([e.get("analysis") for e in bundle.get("results") or []
                                      if isinstance(e, dict)] + [review.get("analysis") if has_review else None])),
        has_review=has_review,
        images_by_hash=images,
        _visual_hash=visual_hash,
    )


def _doc_id(block: dict[str, Any]) -> str:
    return str(block.get("doc_id") or "document")


def _location(block: dict[str, Any]) -> str:
    meta = block.get("structural_meta") or {}
    for key in ("slide", "page"):
        value = meta.get(key)
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return f"{key} {int(value)}"
    return ""


def _entry(entry: dict[str, Any], by_id: dict[str, dict[str, Any]], *, draft: bool) -> ResultEntry:
    doc_ids: dict[str, None] = {}
    for block_id in entry.get("document_block_ids") or []:
        block = by_id.get(str(block_id))
        if block is not None:
            doc_ids[_doc_id(block)] = None
    result_type = str(entry.get("result_type"))
    return ResultEntry(
        id=str(entry.get("id") or result_type),
        result_type=result_type,
        label=str(entry.get("label") or result_type),
        draft=draft,
        doc_ids=tuple(doc_ids),
    )


def _urls(nodes: list[Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.startswith(("http://", "https://")):
            found.add(node)

    for node in nodes:
        walk(node)
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST tests/test_assistant_workspace.py -q`
Expected: 9 passed

---

### Task 4: The four sources over the index

**Files:**
- Modify: `services/assistant/document.py` (becomes the documents source; gains `view`)
- Modify: `services/assistant/navigator.py` (becomes the results source; `fetch_source` moves out)
- Create: `services/assistant/web_sources.py` (`fetch_source` and its guards, moved verbatim)
- Modify: `services/assistant/knowledge.py` (cached load, shared helpers)
- Modify: `services/assistant/skills.py` (cached load)
- Test: `tests/test_assistant_sources.py` (extend), `tests/test_document_extraction_context.py`, `tests/test_scout_lineage.py:1651-1672`, `tests/test_assistant_knowledge.py`

**Interfaces:**
- Consumes: `WorkspaceIndex`, `sources.*`, `limits.*`, `ToolOutput`, `LabelledImage`.
- Produces:
  - `document.overview(index) -> str`, `document.find(index, query) -> str`, `document.get(index, block_ids, *, start_char=0) -> str`, `document.get_range(index, doc_id, *, start=0, count=limits.MAX_RANGE_BLOCKS) -> str`, `document.view(index, block_ids, budget) -> ToolOutput`, `document.visual_ranges(visuals) -> str`.
  - `navigator.overview(index) -> str` (results map lines), `navigator.find(index, query) -> str`, `navigator.get(index, path) -> str`.
  - `web_sources.fetch_source(url, allowed_urls) -> str`.
  - `knowledge.load()` cached; `knowledge.overview()`, `knowledge.find(query)`, `knowledge.read(ids)` unchanged in signature.
  - `skills.available_skills()` cached.
  - `VisualBudget` lives in `document.py`: `VisualBudget(remaining=limits.MAX_VISUALS_PER_QUESTION, viewed=0, withheld=0)` with `take(n) -> int`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_assistant_sources.py`:

```python
from services.assistant import document, knowledge, navigator
from services.assistant.document import VisualBudget
from services.assistant.workspace import build_index
from tests.test_assistant_workspace import block, mixed_workspace, png


class DocumentSourceTests(unittest.TestCase):
    def test_no_documents_reads_as_unavailable(self):
        index = build_index({"results": []}, None)
        for text in (document.find(index, "x"), document.get(index, ["a"]), document.get_range(index, "d"),
                     document.view(index, ["a"], VisualBudget()).text):
            self.assertIn("not available in this workspace", text)

    def test_visual_ranges_compress_runs(self):
        index = build_index({"results": []}, [block("d", n, image=png(sha=f"h{n}"), slide=n) for n in (1, 2, 3, 5)])
        self.assertEqual(document.visual_ranges(index.document("d").visuals), "slides 1–3, 5")

    def test_view_returns_labelled_images_with_text(self):
        index = mixed_workspace()
        output = document.view(index, ["deckA/b-0002", "deckA/b-0002", "deckB/b-0001"], VisualBudget())
        self.assertEqual([image.block_id for image in output.images], ["deckA/b-0002", "deckB/b-0001"])
        self.assertIn("[deckA/b-0002]", output.text)
        self.assertIn("slide 2", output.text)

    def test_view_reports_unknown_and_non_visual_blocks(self):
        index = build_index({"results": []}, [block("d", 1)])
        output = document.view(index, ["d/b-0001", "d/b-9999"], VisualBudget())
        self.assertEqual(output.images, ())
        self.assertIn("(no retained image)", output.text)
        self.assertIn("[d/b-9999] (block not found)", output.text)

    def test_view_caps_per_call_and_per_question(self):
        blocks = [block("d", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 21)]
        index = build_index({"results": []}, blocks)
        budget = VisualBudget(remaining=8)
        first = document.view(index, [b["id"] for b in blocks[:10]], budget)
        self.assertEqual(len(first.images), 6)                  # per-call cap
        self.assertIn("4 more block ids ignored", first.text)
        second = document.view(index, [b["id"] for b in blocks[10:16]], budget)
        self.assertEqual(len(second.images), 2)                 # question budget left
        self.assertIn("image withheld", second.text)
        self.assertEqual((budget.viewed, budget.withheld), (8, 4))

    def test_find_uses_the_shared_hit_format(self):
        index = mixed_workspace()
        self.assertTrue(document.find(index, "text").startswith("- [") or document.find(index, "text") == "(no matches)")
        self.assertEqual(document.find(index, "  "), "(empty search term)")


class ResultSourceTests(unittest.TestCase):
    def test_overview_is_bounded_per_result(self):
        big = {"results": [{"id": "r", "result_type": "scout", "label": "Scout", "document_block_ids": [],
                            "analysis": {f"field_{i}": [{"name": str(j)} for j in range(50)] for i in range(200)}}]}
        lines = navigator.overview(build_index(big, None)).splitlines()
        self.assertLessEqual(len(lines), 3 + 40)

    def test_find_and_get_read_the_bundle(self):
        index = build_index({"results": [{"id": "r", "result_type": "screener", "analysis": {"gate_id": "EOP2"}}]}, None)
        self.assertIn("results[0].analysis.gate_id", navigator.find(index, "eop2"))
        self.assertEqual(navigator.get(index, "results[0].analysis.gate_id"), '"EOP2"')


class CachedLoadTests(unittest.TestCase):
    def test_documentation_and_skills_load_once(self):
        from services.assistant import skills
        self.assertIs(knowledge.load(), knowledge.load())
        self.assertIs(skills.available_skills(), skills.available_skills())
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTEST tests/test_assistant_sources.py -q`
Expected: FAIL (`ImportError: cannot import name 'VisualBudget'`)

- [ ] **Step 3: Implement `document.py`**

Replace the module body (keep its module docstring, updated to "The documents source: find, read, page and view parsed blocks by exact ID.") with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.chat import LabelledImage, ToolOutput
from shared.document_metadata import extraction_context

from . import limits, sources
from .workspace import Visual, WorkspaceIndex

UNAVAILABLE = sources.unavailable("Source document")


@dataclass
class VisualBudget:
    """How many images one question may still view."""

    remaining: int = limits.MAX_VISUALS_PER_QUESTION
    viewed: int = 0
    withheld: int = 0

    def take(self, wanted: int) -> int:
        granted = max(0, min(wanted, self.remaining))
        self.remaining -= granted
        self.viewed += granted
        self.withheld += wanted - granted
        return granted


def overview(index: WorkspaceIndex) -> str:
    if not index.documents:
        return "No source documents are held."
    lines = [f"{len(index.blocks)} parsed blocks across {len(index.documents)} document(s)."]
    for doc in index.documents:
        members = index.blocks_of(doc.doc_id)
        tag = " (user-supplied attachment)" if doc.user_supplied else ""
        visuals = f"; {len(doc.visuals)} visual(s): {visual_ranges(doc.visuals)}" if doc.visuals else ""
        lines.append(f"- {doc.doc_id}{tag}: {len(members)} blocks{visuals}")
        for limitation in dict.fromkeys(
            extraction_context(block.get("structural_meta") or {}, include_page=False) for block in members
        ):
            if limitation:
                lines.append(f"  extraction: {limitation}")
        if doc.headings:
            shown = doc.headings[: limits.MAP_HEADINGS_PER_DOCUMENT]
            more = len(doc.headings) - len(shown)
            lines.append(f"  headings: {' | '.join(shown)}" + (f" … +{more} more" if more else ""))
    return "\n".join(lines)


def visual_ranges(visuals: tuple[Visual, ...]) -> str:
    """Where a document's visuals are, as compressed ranges: "slides 1–3, 5; 2 unplaced"."""
    by_kind: dict[str, list[int]] = {}
    unplaced = 0
    for visual in visuals:
        kind, _, number = visual.location.partition(" ")
        if number.isdigit():
            by_kind.setdefault(kind, []).append(int(number))
        else:
            unplaced += 1
    parts = []
    for kind, numbers in by_kind.items():
        runs, numbers = [], sorted(set(numbers))
        start = prev = numbers[0]
        for n in numbers[1:] + [None]:
            if n is not None and n == prev + 1:
                prev = n
                continue
            runs.append(str(start) if start == prev else f"{start}–{prev}")
            if n is not None:
                start = prev = n
        parts.append(f"{kind}s {', '.join(runs)}")
    if unplaced:
        parts.append(f"{unplaced} unplaced")
    return "; ".join(parts)


def find(index: WorkspaceIndex, query: Any) -> str:
    if not index.blocks:
        return UNAVAILABLE
    term = sources.search_term(query)
    if term is None:
        return sources.EMPTY_QUERY
    hits = []
    for block in index.blocks.values():
        heading = " > ".join(block.get("heading_stack") or [])
        text = f"{heading}\n{block.get('content') or ''}"
        found = text.lower().find(term.lower())
        if found >= 0:
            hits.append(sources.Hit(
                id=str(block["id"]), label=heading, snippet=sources.snippet(text, found, len(term)),
                note=extraction_context(block.get("structural_meta") or {}),
            ))
    return sources.render_hits(hits, limits.MAX_FIND_HITS)


def get(index: WorkspaceIndex, block_ids: list[str], *, start_char: int = 0) -> str:
    if not index.blocks:
        return UNAVAILABLE
    requested = list(dict.fromkeys(str(value) for value in block_ids if value))
    if not requested:
        return "(no block ids supplied)"
    start_char, output, used = max(0, start_char), [], 0
    for block_id in requested:
        block = index.block(block_id)
        if block is None:
            output.append(f"[{block_id}] (block not found)")
            continue
        content = str(block.get("content") or "")
        chunk = content[start_char : start_char + limits.MAX_BLOCK_CHARS]
        rendered = f"{_header(block)}\n{chunk}"
        if start_char + len(chunk) < len(content):
            rendered += f"\n…[block continues; call again with start_char={start_char + len(chunk)}]"
        if output and used + len(rendered) > limits.MAX_READ_CHARS:
            output.append("…[tool output budget reached; request remaining block ids separately]")
            break
        output.append(rendered)
        used += len(rendered)
    return "\n\n".join(output)


def get_range(index: WorkspaceIndex, doc_id: str, *, start: int = 0, count: int = limits.MAX_RANGE_BLOCKS) -> str:
    if not index.blocks:
        return UNAVAILABLE
    members = index.blocks_of(doc_id)
    if not members:
        return f"(document not found: {doc_id})"
    start, count = max(0, start), max(1, min(count, limits.MAX_RANGE_BLOCKS))
    selected = members[start : start + count]
    rendered = get(index, [str(block["id"]) for block in selected])
    if start + len(selected) < len(members):
        rendered += f"\n\n…[document continues; call again with start={start + len(selected)}]"
    return rendered


def view(index: WorkspaceIndex, block_ids: list[str], budget: VisualBudget) -> ToolOutput:
    """Return the retained images for blocks, each labelled with its exact ID, with its text."""
    if not index.blocks:
        return ToolOutput(UNAVAILABLE)
    requested = list(dict.fromkeys(str(value) for value in block_ids if value))
    if not requested:
        return ToolOutput("(no block ids supplied)")
    ignored = requested[limits.MAX_VISUALS_PER_CALL :]
    lines: list[str] = []
    wanted: list[tuple[dict[str, Any], LabelledImage]] = []
    for block_id in requested[: limits.MAX_VISUALS_PER_CALL]:
        block = index.block(block_id)
        if block is None:
            lines.append(f"[{block_id}] (block not found)")
            continue
        image = index.image(block_id)
        if image is None:
            lines.append(f"{_header(block)}\n(no retained image)\n{sources.truncate(str(block.get('content') or ''), limits.MAX_BLOCK_CHARS, 'use read_document')}")
            continue
        wanted.append((block, image))
    granted = budget.take(len(wanted))
    images = []
    for position, (block, image) in enumerate(wanted):
        if position < granted:
            images.append(image)
            lines.append(f"{_header(block)}\n(image attached)")
        else:
            lines.append(f"{_header(block)}\n(image withheld: this question's budget of "
                         f"{limits.MAX_VISUALS_PER_QUESTION} images is spent; say which you viewed)")
    if ignored:
        lines.append(f"…[{len(ignored)} more block ids ignored; at most {limits.MAX_VISUALS_PER_CALL} per call]")
    return ToolOutput("\n\n".join(lines), tuple(images))


def _header(block: dict[str, Any]) -> str:
    heading = " > ".join(block.get("heading_stack") or [])
    header = f"[{block['id']}]" + (f" heading={heading}" if heading else "")
    extraction = extraction_context(block.get("structural_meta") or {})
    return header + (f" | {extraction}" if extraction else "")
```

`extraction_context(meta)` already includes the page/slide location when present; `test_view_returns_labelled_images_with_text` depends on that. If it does not render `slide N`, append `location` from the index to `_header` instead (look it up via the visual list).

- [ ] **Step 3b: Versions, readers, and searches no document can crowd out**

The browser tags every version of a same-named document with a fingerprint (`cTPP@3f9a1c`, Task 8). The documents source makes that legible and keeps a multi-document search honest.

In `sources.py`, give `render_hits` an optional overflow line (the default wording is unchanged):

```python
def render_hits(hits: list[Hit], cap: int, overflow: str | None = None) -> str:
    ...
    if len(hits) > cap:
        lines.append(overflow or f"…[{len(hits) - cap} more matches; search a narrower term]")
```

In `document.py`, add:

```python
import re
from collections import Counter

_VERSION = re.compile(r"^(?P<base>.+)@[0-9a-f]{6}$")


def _readers(index: WorkspaceIndex, doc_id: str) -> list[str]:
    return [f"{entry.result_type} ({entry.label})" for entry in index.results if doc_id in entry.doc_ids]


def _version_note(index: WorkspaceIndex, doc_id: str) -> str:
    match = _VERSION.match(doc_id)
    if not match:
        return ""
    siblings = sum(1 for doc in index.documents if (m := _VERSION.match(doc.doc_id)) and m["base"] == match["base"])
    return f" (one of {siblings} versions of {match['base']})"
```

and the per-document line in `overview` becomes:

```python
        readers = _readers(index, doc.doc_id)
        line = f"- {doc.doc_id}{_version_note(index, doc.doc_id)}{tag}: {len(members)} blocks{visuals}"
        lines.append(line + (f"; read by: {', '.join(readers)}" if readers else ""))
```

`find` takes an optional document and reports what the cap held back, per document:

```python
def find(index: WorkspaceIndex, query: Any, doc_id: str | None = None) -> str:
    if not index.blocks:
        return UNAVAILABLE
    term = sources.search_term(query)
    if term is None:
        return sources.EMPTY_QUERY
    if doc_id is not None and index.document(doc_id) is None:
        return f"(document not found: {doc_id})"
    scope = index.blocks_of(doc_id) if doc_id is not None else list(index.blocks.values())
    hits, owners = [], []
    for block in scope:
        heading = " > ".join(block.get("heading_stack") or [])
        text = f"{heading}\n{block.get('content') or ''}"
        found = text.lower().find(term.lower())
        if found >= 0:
            hits.append(sources.Hit(
                id=str(block["id"]), label=heading, snippet=sources.snippet(text, found, len(term)),
                note=extraction_context(block.get("structural_meta") or {}),
            ))
            owners.append(str(block.get("doc_id") or "document"))
    overflow = None
    if len(hits) > limits.MAX_FIND_HITS:
        rest = Counter(owners[limits.MAX_FIND_HITS :])
        overflow = ("…[" + ", ".join(f"{count} more in {owner}" for owner, count in rest.items())
                    + "; narrow with doc_id]")
    return sources.render_hits(hits, limits.MAX_FIND_HITS, overflow=overflow)
```

Add to `DocumentSourceTests` in `tests/test_assistant_sources.py`:

```python
    def test_overview_names_versions_and_readers(self):
        blocks = [block("cTPP@aaaaaa", 1), block("cTPP@bbbbbb", 1)]
        bundle = {"results": [
            {"id": "i", "result_type": "inspector", "label": "Inspect", "document_block_ids": ["cTPP@aaaaaa/b-0001"]},
            {"id": "s", "result_type": "screener", "label": "Gate", "document_block_ids": ["cTPP@bbbbbb/b-0001"]},
        ]}
        text = document.overview(build_index(bundle, blocks))
        self.assertIn("cTPP@aaaaaa (one of 2 versions of cTPP)", text)
        self.assertIn("read by: inspector (Inspect)", text)
        self.assertIn("read by: screener (Gate)", text)

    def test_find_narrows_by_document_and_counts_what_the_cap_held_back(self):
        blocks = [dict(block("deckA", n), content="dose") for n in range(1, 51)]
        blocks += [dict(block("deckB", n), content="dose") for n in range(1, 11)]
        index = build_index({"results": []}, blocks)
        self.assertIn("…[10 more in deckA, 10 more in deckB; narrow with doc_id]", document.find(index, "dose"))
        narrowed = document.find(index, "dose", doc_id="deckB")
        self.assertEqual(narrowed.count("- [deckB/"), 10)
        self.assertNotIn("deckA", narrowed)
        self.assertEqual(document.find(index, "dose", doc_id="nope"), "(document not found: nope)")
```

- [ ] **Step 4: Implement `navigator.py` and `web_sources.py`**

Move `fetch_source`, `_strip_html`, `_is_public_http_url` and `_PublicRedirectHandler` verbatim into `services/assistant/web_sources.py`, replacing `MAX_FETCH_CHARS`, `FETCH_TIMEOUT_SECONDS` and the literal `2_000_000` with `limits.MAX_FETCH_CHARS`, `limits.FETCH_TIMEOUT_SECONDS`, `limits.MAX_FETCH_BYTES`. Give it the docstring `"""Opening a source an analysis already cites: allow-list and public-address checks, then text."""`.

In `navigator.py`, delete those moved names and `collect_urls` (the index owns URL collection), delete `MAX_GET_CHARS`, `MAX_FIND_HITS`, `MAX_FETCH_CHARS`, `FETCH_TIMEOUT_SECONDS`, and change the three public functions to take the index:

```python
def overview(index: WorkspaceIndex) -> str:
    """Each held result and the draft: what it is, what it read, and its top two levels."""
    if not index.results:
        return "No results are held."
    # Walk the bundle's own list so each path is the entry's real position there; the
    # index's results are the same entries, in the same order, minus any without a type.
    raw = [
        (position, entry)
        for position, entry in enumerate(index.bundle.get("results") or [])
        if isinstance(entry, dict) and entry.get("result_type")
    ]
    finals = [entry for entry in index.results if not entry.draft]
    rows = [(f"results[{position}]", entry, raw_entry.get("analysis"))
            for (position, raw_entry), entry in zip(raw, finals)]
    if index.has_review:
        draft = next(entry for entry in index.results if entry.draft)
        rows.append(("active_review", draft, index.bundle["active_review"].get("analysis")))
    lines = []
    for path, entry, analysis in rows:
        state = "draft" if entry.draft else "final"
        reads = ", ".join(entry.doc_ids) or "no documents"
        lines.append(f"- [{entry.id}] {entry.result_type} · {entry.label} · {state} · reads: {reads} · path: {path}")
        lines.extend(f"  {line}" for line in _structure(analysis, limits.MAP_LINES_PER_RESULT))
    return "\n".join(lines)


def _structure(node: Any, cap: int) -> list[str]:
    """Field names and list sizes two levels deep, capped."""
    lines: list[str] = []

    def describe(value: Any) -> str:
        if isinstance(value, list):
            return f"list ({len(value)} items)"
        if isinstance(value, dict):
            return f"object ({len(value)} fields)"
        text = str(value)
        return text if len(text) <= 60 else text[:60] + "…"

    if isinstance(node, dict):
        for key, value in node.items():
            lines.append(f"{key}: {describe(value)}")
            if isinstance(value, dict):
                lines.extend(f"  {child}: {describe(grand)}" for child, grand in value.items())
    total = len(lines)
    if total > cap:
        lines = lines[:cap] + [f"…[{total - cap} more fields; use find_result]"]
    return lines


def get(index: WorkspaceIndex, path: str) -> str:
    node = _traverse(index.bundle, path.strip())
    return sources.truncate(json.dumps(node, indent=2, default=str, ensure_ascii=False),
                            limits.MAX_RESULT_CHARS, "narrow the path")


def find(index: WorkspaceIndex, query: Any) -> str:
    term = sources.search_term(query)
    if term is None:
        return sources.EMPTY_QUERY
    needle, hits = term.lower(), []

    def walk(node: Any, path: str) -> None:
        if len(hits) > limits.MAX_FIND_HITS:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else key
                if needle in str(key).lower():
                    hits.append(sources.Hit(id=child, snippet=""))
                walk(value, child)
        elif isinstance(node, list):
            for position, value in enumerate(node):
                walk(value, f"{path}[{position}]")
        elif isinstance(node, str) and needle in node.lower():
            hits.append(sources.Hit(id=path, snippet=sources.snippet(node, node.lower().find(needle), len(needle))))

    walk(index.bundle, "")
    return sources.render_hits(hits, limits.MAX_FIND_HITS)
```

Keep `_traverse` and `_PATH_TOKEN`. Update the module docstring's function list to `overview(index)`, `get(index, path)`, `find(index, query)` and drop the `fetch_source` line. Imports: `json`, `re`, `from typing import Any`, `from . import limits, sources`, `from .workspace import WorkspaceIndex`. The `read_result` path convention is unchanged: paths start at the bundle root (`results[0].analysis…`).

- [ ] **Step 5: Implement cached loads**

In `knowledge.py`: add `from functools import lru_cache`; decorate `load` with `@lru_cache(maxsize=1)`; replace `MAX_FIND_HITS`/`MAX_READ_CHARS` with `limits.MAX_PRODUCT_DOC_HITS`/`limits.MAX_PRODUCT_DOC_CHARS`; rewrite `find` to build `sources.Hit(id=section["id"], label=section["title"], snippet=sources.snippet(text, found, len(term)))` hits and return `sources.render_hits(hits, limits.MAX_PRODUCT_DOC_HITS)` (empty term → `sources.EMPTY_QUERY`); and end `read` with `return sources.truncate(text, limits.MAX_PRODUCT_DOC_CHARS, "request fewer sections")`.

In `skills.py`: decorate `available_skills` with `@lru_cache(maxsize=1)` and return `tuple(...)` instead of a list (update its annotation to `tuple[Skill, ...]`).

- [ ] **Step 6: Update existing tests to the index**

In `tests/test_document_extraction_context.py` and `tests/test_scout_lineage.py` (≈1651-1672), wherever a test calls `document.find(blocks, …)`, `document.get(blocks, …)`, `document.get_range(blocks, …)` or `document.overview(blocks)`, build the index first and pass it:

```python
from services.assistant.workspace import build_index
index = build_index({"results": []}, blocks)
document.find(index, "keyword")
```

Assertions on `find` output that parsed JSON (`json.loads(...)`) change to substring checks on the rendered hit lines (`"- [block-id]"`, the snippet text, and the extraction note in parentheses). In `tests/test_assistant_knowledge.py`, replace any assertion on `"(no documentation matches)"` with `"(no matches)"` and on `"(empty keyword)"` with `"(empty search term)"`.

- [ ] **Step 7: Run tests**

Run: `PYTEST tests/test_assistant_sources.py tests/test_document_extraction_context.py tests/test_scout_lineage.py tests/test_assistant_knowledge.py -q`
Expected: all pass.

---

### Task 5: Registry over sources, the visuals tool, and budgets

**Files:**
- Modify: `services/assistant/registry.py`, `services/assistant/resources.py`
- Test: `tests/test_assistant_resources.py`

**Interfaces:**
- Consumes: sources from Task 4, `VisualBudget`, `ToolOutput`.
- Produces: `ToolContext(index: WorkspaceIndex, budget: VisualBudget)`; `REGISTRY`, `TOOLS`, `VERBS` (public, replaces `_VERBS`); `run_tool(call: ToolCall, context: ToolContext) -> ToolOutput`; `resources.Handler = Callable[..., str | ToolOutput]`; `resources.activity_for(table: dict[str, Verb], name) -> str`. `held_result_types` is removed from `registry.py` (the index owns it).

- [ ] **Step 1: Write the failing tests** — add to `tests/test_assistant_resources.py`:

```python
from shared.chat import ToolCall, ToolOutput
from services.assistant.document import VisualBudget
from services.assistant.registry import REGISTRY, TOOLS, VERBS, ToolContext, run_tool
from services.assistant.workspace import build_index
from tests.test_assistant_workspace import mixed_workspace


class VisualToolTests(unittest.TestCase):
    def call(self, name, **args):
        import json
        return ToolCall(id="c1", name=name, arguments=json.dumps(args))

    def test_view_document_visuals_is_offered_with_its_cap(self):
        schema = next(t for t in TOOLS if t["function"]["name"] == "view_document_visuals")
        self.assertEqual(schema["function"]["parameters"]["properties"]["block_ids"]["maxItems"], 6)

    def test_every_tool_returns_a_tool_output(self):
        context = ToolContext(index=mixed_workspace(), budget=VisualBudget())
        for name in VERBS:
            output = run_tool(self.call(name), context)
            self.assertIsInstance(output, ToolOutput, name)

    def test_visuals_come_back_labelled(self):
        context = ToolContext(index=mixed_workspace(), budget=VisualBudget())
        output = run_tool(self.call("view_document_visuals", block_ids=["deckB/b-0002"]), context)
        self.assertEqual([image.block_id for image in output.images], ["deckB/b-0002"])

    def test_bad_arguments_are_reported_not_raised(self):
        context = ToolContext(index=build_index(None, None), budget=VisualBudget())
        self.assertEqual(run_tool(ToolCall("c", "read_result", "{bad"), context).text, "Invalid tool arguments.")
        self.assertEqual(run_tool(ToolCall("c", "nope", "{}"), context).text, "Unknown tool: nope")

    def test_range_schema_reads_the_shared_limit(self):
        schema = next(t for t in TOOLS if t["function"]["name"] == "read_document_range")
        self.assertEqual(schema["function"]["parameters"]["properties"]["count"]["maximum"], 25)

    def test_document_search_can_be_narrowed_to_one_document(self):
        schema = next(t for t in TOOLS if t["function"]["name"] == "find_document")
        self.assertIn("doc_id", schema["function"]["parameters"]["properties"])
        self.assertEqual(schema["function"]["parameters"]["required"], ["keyword"])
        context = ToolContext(index=mixed_workspace(), budget=VisualBudget())
        output = run_tool(self.call("find_document", keyword="text", doc_id="nope"), context)
        self.assertEqual(output.text, "(document not found: nope)")
```

Also update this file's existing tests: replace imports of `_VERBS` with `VERBS`, of `held_result_types` from `registry` with `build_index(bundle, None).held_result_types`, and any `ToolContext(result=…, allowed_urls=…, document=…, held_result_types=…)` with `ToolContext(index=build_index(result, document), budget=VisualBudget())`. Where a test calls `verb.handler(context, args)` and compares a string, compare `run_tool(...).text` instead.

- [ ] **Step 2: Run to verify failure**

Run: `PYTEST tests/test_assistant_resources.py -q`
Expected: FAIL (`ImportError: cannot import name 'VERBS'`)

- [ ] **Step 3: Implement**

In `resources.py`: `Handler = Callable[..., "str | ToolOutput"]` (import `ToolOutput` under `TYPE_CHECKING`), and change `activity_for` to take the prebuilt table:

```python
def activity_for(table: dict[str, Verb], verb_name: str) -> str:
    """What a reader is told while `verb_name` runs."""
    verb = table.get(verb_name)
    return verb.activity if verb else "Working"
```

In `registry.py`:

- `ToolContext` becomes:

```python
@dataclass(frozen=True)
class ToolContext:
    """Everything a verb may read, and the question's visual budget."""

    index: WorkspaceIndex
    budget: VisualBudget
```

- Handlers call the sources with `ctx.index` (drop every `if ctx.document else "Source document unavailable."` guard — the documents source answers that itself):
  - `find_product_docs`: `knowledge.find(args.get("keyword"))`
  - `read_product_docs`: `knowledge.read(_string_list(args.get("section_ids")))`
  - `find_result`: `navigator.find(ctx.index, args.get("keyword"))`
  - `read_result`: `navigator.get(ctx.index, str(args.get("path", "")))`
  - `fetch_source`: `web_sources.fetch_source(str(args.get("url", "")), set(ctx.index.allowed_urls))`
  - `find_document`: `document_reader.find(ctx.index, args.get("keyword"), doc_id=str(args["doc_id"]) if args.get("doc_id") else None)`, and its schema gains an optional `"doc_id": {"type": "string", "description": "Search only this document, by the doc_id the map shows."}`; add to its description: "When matches exceed the cap, the result says how many more each document holds; pass doc_id to search one."
  - `read_document`: `document_reader.get(ctx.index, _string_list(args.get("block_ids")), start_char=_int(args.get("start_char"), 0))`
  - `read_document_range`: `document_reader.get_range(ctx.index, str(args.get("doc_id", "")), start=_int(args.get("start"), 0), count=_int(args.get("count"), limits.MAX_RANGE_BLOCKS))`, with `"maximum": limits.MAX_RANGE_BLOCKS` in its schema
  - `find_skill`: `skills.catalog(ctx.index.held_result_types)`
  - `read_skill`: `skills.read_skill(str(args.get("name", "")))`
- Add the verb to the `document` resource, after `read_document_range`:

```python
            resources.Verb(
                name="view_document_visuals",
                description=(
                    "Look at the retained images of document blocks by exact block ID: slides, "
                    "pages, figures. Each image comes back labelled with its block ID, with the "
                    f"block's text and location. At most {limits.MAX_VISUALS_PER_CALL} per call and "
                    f"{limits.MAX_VISUALS_PER_QUESTION} per question: choose blocks from the map's "
                    "visual locations or find_document, and say which ones you viewed."
                ),
                activity="Looking at the document visuals",
                parameters={
                    "type": "object",
                    "properties": {"block_ids": {"type": "array", "items": {"type": "string"},
                                                 "maxItems": limits.MAX_VISUALS_PER_CALL}},
                    "required": ["block_ids"],
                },
                handler=lambda ctx, args: document_reader.view(
                    ctx.index, _string_list(args.get("block_ids")), ctx.budget),
            ),
```

- Add helpers and the dispatcher; rename `_VERBS` to `VERBS`; delete `held_result_types`:

```python
def _int(raw: Any, default: int) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else default


TOOLS: list[dict[str, Any]] = resources.tool_schemas(REGISTRY)
VERBS = resources.verbs_by_name(REGISTRY)


def run_tool(call: ToolCall, context: ToolContext) -> ToolOutput:
    """Route one model tool call to the verb that declared it."""
    verb = VERBS.get(call.name)
    if verb is None:
        return ToolOutput(f"Unknown tool: {call.name}")
    try:
        args = json.loads(call.arguments or "{}")
    except json.JSONDecodeError:
        return ToolOutput("Invalid tool arguments.")
    if not isinstance(args, dict):
        return ToolOutput("Invalid tool arguments.")
    output = verb.handler(context, args)
    return output if isinstance(output, ToolOutput) else ToolOutput(str(output))
```

- Imports: `json`, `from shared.chat import ToolCall, ToolOutput`, `from . import limits, web_sources`, `from .document import VisualBudget`, `from .workspace import WorkspaceIndex`.

- [ ] **Step 3b: Keep `agent.py` importable until Task 6 rewrites it**

`agent.py` imports `_VERBS` and `held_result_types` from the registry and builds the old `ToolContext`. Adapt it minimally, without touching its prompt code: import `TOOLS, VERBS, ToolContext, run_tool` and `from .workspace import build_index`; in `answer_stream` build `index = build_index(result, document)` and `context = ToolContext(index=index, budget=VisualBudget())`; replace its `_run_tool(call, context)` with `run_tool(call, context).text` and delete `_run_tool`; replace `resources.activity_for(REGISTRY, call.name)` with `resources.activity_for(VERBS, call.name)`; replace `held_result_types(result)` with `index.held_result_types` (pass the index into `_system_prompt` if needed, or call `build_index(result, document).held_result_types` there). `_system_prompt` calls `navigator.overview(result)` and `document_reader.overview(document or [])`; change them to `navigator.overview(build_index(result, document))` and `document_reader.overview(build_index(result, document))`. Task 6 replaces all of this.

- [ ] **Step 4: Run tests**

Run: `PYTEST tests/test_assistant_resources.py -q`
Expected: all pass.

---

### Task 6: The prompt, the loop, legends, and the question log

**Files:**
- Create: `services/assistant/protocols.py`, `services/assistant/prompt.py`
- Modify: `services/assistant/agent.py`, `services/assistant/legends.py`, `services/assistant/__init__.py`
- Test: `tests/test_assistant_prompt.py` (new); update `tests/test_assistant_resources.py`, `tests/test_assistant_knowledge.py`, `tests/test_assistant_review_context.py`, `tests/test_assistant_stream.py`; `web/lib/citation.test.ts` (reads the prompt text)

**Interfaces:**
- Consumes: `build_index`, `run_tool`, `TOOLS`, `VERBS`, `REGISTRY`, `VisualBudget`, `ToolContext`.
- Produces: `protocols.StreamingChatLLMProtocol` (`chat_stream` only); `prompt.system_prompt(index) -> str`; `prompt.STATIC_PREFIX: str`; `legends.legends_for(held: frozenset[str], has_review: bool) -> str`; `agent.answer_stream(client, result, messages, *, document=None, max_tokens=limits.MAX_OUTPUT_TOKENS) -> Iterator[Chunk]` (no `result_type`); `agent.Chunk` unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assistant_prompt.py
"""The prompt is a stable prefix and a bounded map; no image enters it unasked."""

import json
import unittest
from types import SimpleNamespace

from shared.chat import ChatDelta, ChatTurn, ToolCall, Usage
from services.assistant import answer_stream
from services.assistant.prompt import STATIC_PREFIX, system_prompt
from services.assistant.workspace import build_index
from tests.test_assistant_workspace import block, mixed_workspace, png


class RecordingClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def chat_stream(self, messages, *, tools=None, max_tokens=4000):
        self.calls.append([dict(m) for m in messages])
        turn = self.turns.pop(0)
        if turn.text:
            yield ChatDelta(text=turn.text)
        yield ChatDelta(turn=turn)


def final(text="Answer."):
    return ChatTurn(text=text, tool_calls=(), continuation=(), usage=Usage(100, 80, 10))


class PromptTests(unittest.TestCase):
    def test_prompt_starts_with_the_same_prefix_for_every_workspace(self):
        self.assertTrue(system_prompt(build_index(None, None)).startswith(STATIC_PREFIX))
        self.assertTrue(system_prompt(mixed_workspace()).startswith(STATIC_PREFIX))

    def test_legends_match_the_held_results(self):
        text = system_prompt(mixed_workspace())
        self.assertIn("This is a SCREENER result", text)
        self.assertIn("This is an INSPECTOR result", text)
        self.assertNotIn("This is an ALIGNER result", text)
        self.assertIn("ACTIVE REVIEW DRAFT", text)

    def test_corrected_legends(self):
        text = system_prompt(mixed_workspace())
        self.assertIn("DOCX, PPTX or text-based PDF", text)
        self.assertNotIn("judges the iTPP, cTPP, and IPDP against each other", text)

    def test_map_does_not_grow_with_document_length(self):
        def prompt_for(slides):
            deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, slides + 1)]
            return system_prompt(build_index({"results": []}, deck))
        long, short = prompt_for(200), prompt_for(2)
        self.assertIn("200 visual(s): slides 1–200", long)
        self.assertLess(len(long) - len(short), 200)

    def test_the_prefix_says_what_to_do_with_two_versions(self):
        self.assertIn("more than one version of a document", STATIC_PREFIX)

    def test_no_image_is_sent_up_front(self):
        client = RecordingClient([final()])
        deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 4)]
        list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Hi"}], document=deck))
        for message in client.calls[0]:
            self.assertNotIsInstance(message.get("content"), list)

    def test_viewed_images_join_the_working_list_once(self):
        call = ToolCall("c1", "view_document_visuals", json.dumps({"block_ids": ["deck/b-0002"]}))
        client = RecordingClient([ChatTurn("", (call,), ()), final()])
        deck = [block("deck", n, image=png(sha=f"h{n}"), slide=n) for n in range(1, 4)]
        chunks = list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Slide 2?"}], document=deck))
        tool_messages = [m for m in client.calls[1] if m["role"] == "tool"]
        self.assertEqual([i.block_id for i in tool_messages[0]["images"]], ["deck/b-0002"])
        self.assertEqual([c.kind for c in chunks], ["activity", "text"])

    def test_one_log_line_per_question(self):
        client = RecordingClient([final()])
        with self.assertLogs("services.assistant.agent", level="INFO") as logs:
            list(answer_stream(client, {"results": []}, [{"role": "user", "content": "Hi"}]))
        record = json.loads(logs.output[0].split("assistant_question ", 1)[1])
        self.assertEqual(record["model_calls"], 1)
        self.assertEqual(record["input_tokens"], 100)
        self.assertEqual(record["cached_input_tokens"], 80)
        self.assertEqual(record["visuals_viewed"], 0)
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTEST tests/test_assistant_prompt.py -q`
Expected: FAIL (`ModuleNotFoundError: services.assistant.prompt`)

- [ ] **Step 3: Implement `protocols.py`**

```python
# services/assistant/protocols.py
"""What the Assistant needs from a model client: one streamed, tool-capable turn."""

from __future__ import annotations

from typing import Any, Iterator, Protocol

from shared.chat import ChatDelta


class StreamingChatLLMProtocol(Protocol):
    """Satisfied by `shared.openai_client.OpenAIClient.chat_stream`."""

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4000,
    ) -> Iterator[ChatDelta]:
        ...
```

- [ ] **Step 4: Implement `legends.py` changes**

- `SCREENER_LEGEND`: "This is an SCREENER result" → "This is a SCREENER result"; "Screener accepts any supported DOCX/PPTX document" → "Screener accepts any supported DOCX, PPTX or text-based PDF document"; replace the line starting `- blocks[]: the parsed content and retained images from all supplied documents.` with `- The parsed content and retained images of all supplied documents are in the workspace's document collection, not in this tree; reach them with the document tools by the cited block IDs.`
- `ALIGNER_LEGEND`: replace the paragraph starting `- blocks[]: every parsed block from every document, readable through the same document tools` up to `...safe to reproduce verbatim.` with: `- The parsed blocks of every document are in the workspace's document collection, not in this tree, and are read with the document tools. A finding's two citation lists point into different documents: reference_spans into the one that sets the bar, comparison_spans into the one being measured. Never present one as the other. Each span carries the quoted line and the block it came from; the quote was copied from the block by code, not typed by a model, so it is safe to reproduce verbatim.`
- `WORKSPACE_LEGEND`: replace the final paragraph (`Use each entry's result_type to interpret its analysis: Inspector judges … identify which result supports each statement.`) with: `Use each entry's result_type to interpret its analysis with that type's legend below, where one is given. Chunker results expose parsed source blocks; Searcher results contain direct normalized retrieval findings. Compare entries only when the question calls for it, and identify which result supports each statement.`
- Replace `_LEGENDS` and `legend_for` with:

```python
_BY_TYPE = (
    ("inspector", INSPECTOR_LEGEND),
    ("aligner", ALIGNER_LEGEND),
    ("scout", SCOUT_LEGEND),
    ("screener", SCREENER_LEGEND),
)


def legends_for(held: frozenset[str], has_review: bool) -> str:
    """The workspace legend, then one legend per held result type, then the draft's."""
    parts = [WORKSPACE_LEGEND]
    parts += [legend for result_type, legend in _BY_TYPE if result_type in held]
    if has_review:
        parts.append(SCOUT_REVIEW_LEGEND)
    return "\n\n".join(parts)
```

  Update the module docstring's last line to "Adding a result type with its own vocabulary = add one legend and one `_BY_TYPE` entry."

- [ ] **Step 5: Implement `prompt.py`**

Move `_system_prompt`'s section texts from `agent.py` into `prompt.py`, keeping every rule sentence and its explanatory `#` comments, with these changes:

- `role`: always the workspace wording: `"You are Ask: a read-only assistant that answers questions about the client-held workspace catalog, its available final analysis results, any explicitly supplied active review draft, and the parsed source documents behind them. You are grounded: answer ONLY from this submitted context, the canonical public PDIS product documentation, and the full text behind sources it already cites. You never run new web searches and never change anything."`
- `document_access` and `grounding_rules`: unconditional (drop the `if has_doc` branches and the `+ (", or the source document" if has_doc else "")` fragment — always include it). In `document_access`, replace `"- You may inspect, quote, compare, and cite parsed text and retained visuals using their block IDs.\n"` with `"- You may inspect, quote, compare, and cite parsed text using block IDs. Retained visuals are not in this prompt: look at one with view_document_visuals when a question depends on what a slide, page or figure shows.\n"` and prefix the first bullet with "When the workspace holds documents, ".
- `answering`: append `"- When the map lists more than one version of a document and the question does not say which, ask which one, or answer for each version and name it. A result's own citations already point at the version it read.\n"`.
- `reach`: unchanged text, minus the `has_doc` suffix; add `"- Visuals cost the most to read. View only the blocks a question needs, and never claim to have seen a visual you did not view.\n"` after the inventory.
- `context_meaning`/`review_meaning` become one tail section: `f"WHAT THIS CONTEXT IS:\n{legends_for(index.held_result_types, index.has_review)}"`.
- `overview` becomes `f"WORKSPACE MAP - results:\n{navigator.overview(index)}"` and `document_map` becomes `f"WORKSPACE MAP - documents (the authors' claims; cite exact block IDs):\n{document_reader.overview(index)}"`.

```python
# services/assistant/prompt.py (structure)
"""The Assistant's system prompt: a fixed prefix, then a bounded map of this workspace.

The prefix is identical for every request, so the provider's prompt cache serves it on
every call of the loop and across questions. Everything that varies comes after it, and
none of it grows with a document's length: images are never here, and each result and
document contributes a bounded number of lines.
"""

from __future__ import annotations

from . import document as document_reader
from . import knowledge, navigator, resources, skills
from .legends import legends_for
from .registry import REGISTRY
from .workspace import WorkspaceIndex

ROLE = "..."            # as above
DOCUMENT_ACCESS = "..." # as above
GROUNDING = "..."       # moved verbatim, unconditional
ANSWERING = "..."       # moved verbatim
REACH = (
    "WHAT YOU CAN REACH:\n"
    f"{resources.inventory(REGISTRY)}\n"
    "..."               # moved lines, plus the visuals line
)

STATIC_PREFIX = "\n\n".join((
    ROLE, DOCUMENT_ACCESS, GROUNDING, ANSWERING, REACH,
    "PRODUCT DOCUMENTATION MAP (public PDIS behavior and architecture; not analysis evidence):\n"
    + knowledge.overview(),
))


def system_prompt(index: WorkspaceIndex) -> str:
    tail = (
        f"WHAT THIS CONTEXT IS:\n{legends_for(index.held_result_types, index.has_review)}",
        f"SKILLS AVAILABLE:\n{skills.catalog(index.held_result_types)}\n"
        "Read one with read_skill before answering a question it covers.",
        f"WORKSPACE MAP - results:\n{navigator.overview(index)}",
        "WORKSPACE MAP - documents (the authors' claims; cite exact block IDs):\n"
        + document_reader.overview(index),
    )
    return "\n\n".join((STATIC_PREFIX, *tail))
```

The `"..."` markers above stand for the section strings moved from `agent.py:_system_prompt` with the listed edits; move them verbatim, do not paraphrase.

- [ ] **Step 6: Implement `agent.py`**

Replace the module with the loop only:

```python
"""Ask: a read-only, grounded agent loop over one request's workspace.

Build the index, send the bounded prompt, run any tools the model calls, repeat until it
answers. The loop knows nothing about what the tools do; the registry does.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator, Literal

from shared.chat import ChatTurn

from . import limits, resources
from .document import VisualBudget
from .prompt import system_prompt
from .protocols import StreamingChatLLMProtocol
from .registry import TOOLS, VERBS, ToolContext, run_tool
from .workspace import build_index

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    # keep the existing docstring
    kind: Literal["text", "activity"]
    text: str


@dataclass
class QuestionStats:
    model_calls: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    tools_called: list[str] = field(default_factory=list)
    visuals_viewed: int = 0
    visuals_withheld: int = 0

    def add(self, turn: ChatTurn) -> None:
        self.model_calls += 1
        self.input_tokens += turn.usage.input_tokens
        self.cached_input_tokens += turn.usage.cached_input_tokens
        self.output_tokens += turn.usage.output_tokens


def answer_stream(
    client: StreamingChatLLMProtocol,
    result: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    document: list[dict[str, Any]] | None = None,
    max_tokens: int = limits.MAX_OUTPUT_TOKENS,
) -> Iterator[Chunk]:
    """Stream the final grounded answer while keeping tool turns server-side."""
    index = build_index(result, document)
    context = ToolContext(index=index, budget=VisualBudget())
    work: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(index)}, *messages]
    stats = QuestionStats()
    try:
        for _ in range(limits.MAX_STEPS):
            turn = yield from _stream_turn(client, work, TOOLS, max_tokens, stats)
            if not turn.tool_calls:
                return
            # The provider owns continuation syntax. Carry it back unchanged, within
            # this request only, so reasoning and tool-call lineage survive each step.
            work.append({"role": "assistant", "content": turn.text, "continuation": turn.continuation})
            for call in turn.tool_calls:
                yield Chunk("activity", resources.activity_for(VERBS, call.name))
                output = run_tool(call, context)
                stats.tools_called.append(call.name)
                work.append({"role": "tool", "tool_call_id": call.id,
                             "content": output.text, "images": output.images})
        work.append({"role": "user", "content": "Answer now using what you've gathered."})
        turn = yield from _stream_turn(client, work, None, max_tokens, stats)
        if turn.tool_calls:
            raise RuntimeError("Assistant did not complete its final answer")
    finally:
        stats.visuals_viewed = context.budget.viewed
        stats.visuals_withheld = context.budget.withheld
        logger.info("assistant_question %s", json.dumps(asdict(stats)))


def _stream_turn(client, work, tools, max_tokens, stats) -> Iterator[Chunk]:
    turn = None
    for delta in client.chat_stream(work, tools=tools, max_tokens=max_tokens):
        if delta.text:
            yield Chunk("text", delta.text)
        if delta.turn is not None:
            turn = delta.turn
    if turn is None:
        raise RuntimeError("Assistant provider stream ended before completing a turn")
    stats.add(turn)
    return turn
```

Note the forced final call now passes `tools=None` explicitly, as it did before (it was called without `tools`).

- [ ] **Step 7: Update `__init__.py`**

Export `Chunk`, `StreamingChatLLMProtocol` (from `.protocols`), `answer_stream`, the digest names as today, and `limits`. Remove `ChatLLMProtocol`. Update the docstring to list `limits` as public.

- [ ] **Step 7b: Keep the route runnable**

In `api/routes/assistant.py`, drop `request.result_type` from the `assistant_answer_stream(...)` call (Task 7 owns the rest of the route). Without this the route passes the result type where the messages belong.

- [ ] **Step 8: Update tests that reached into private names**

- `tests/test_assistant_resources.py`, `tests/test_assistant_knowledge.py`, `tests/test_assistant_review_context.py`: replace `from services.assistant.agent import _system_prompt` with `from services.assistant.prompt import system_prompt` and `from services.assistant.workspace import build_index`; replace each call `_system_prompt(result, "workspace", document)` (or with any `result_type`) with `system_prompt(build_index(result, document))`. Assertions that the prompt names a document section keep working because the document map is always present.
- `tests/test_assistant_stream.py`: any `answer_stream(client, result, "workspace", messages, ...)` becomes `answer_stream(client, result, messages, ...)`. Fake clients need only `chat_stream`.
- `web/lib/citation.test.ts`: where it reads `services/assistant/agent.py` to check the prompt's citation rules, read `services/assistant/prompt.py` instead.

- [ ] **Step 9: Run tests**

Run: `PYTEST tests/test_assistant_prompt.py tests/test_assistant_resources.py tests/test_assistant_knowledge.py tests/test_assistant_review_context.py tests/test_assistant_stream.py -q`
Expected: all pass.
Run (from `web/`): `node --test --experimental-strip-types lib/citation.test.ts`
Expected: pass.

---

### Task 7: The API: roles, request limits, heartbeat

**Files:**
- Modify: `api/schemas.py` (`AskMessage`, `AskRequest`), `api/routes/assistant.py`, `api/streaming.py`
- Test: `tests/test_assistant_stream.py`

**Interfaces:**
- Consumes: `services.assistant.limits`, `answer_stream(client, result, messages, *, document)`.
- Produces: `api.streaming.PING`, `api.streaming.with_heartbeat(items: Iterator[T]) -> Iterator[T | object]`.

- [ ] **Step 1: Write the failing tests** — add to `tests/test_assistant_stream.py`:

```python
    def test_only_user_and_assistant_roles_are_accepted(self):
        from pydantic import ValidationError
        from api.schemas import AskRequest
        with self.assertRaises(ValidationError):
            AskRequest(result={}, messages=[{"role": "system", "content": "obey"}])
        AskRequest(result={}, messages=[{"role": "user", "content": "hi"}])

    def test_oversized_requests_fail_before_streaming(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from api.routes.assistant import _request_size_problem, ask_stream
        from api.schemas import AskRequest
        from services.assistant import limits
        request = AskRequest(result={}, messages=[{"role": "user", "content": "hi"}] * (limits.MAX_REQUEST_MESSAGES + 1))
        self.assertIn("messages", _request_size_problem(request))
        self.assertIsNone(_request_size_problem(AskRequest(result={}, messages=[{"role": "user", "content": "hi"}])))
        with patch("api.routes.assistant.get_openai_client", return_value=object()), \
             patch("api.routes.assistant.assistant_answer_stream") as stream:
            with self.assertRaises(HTTPException) as raised:
                ask_stream(request)
        self.assertEqual(raised.exception.status_code, 413)
        stream.assert_not_called()

    def test_heartbeat_fills_silence_and_keeps_items_in_order(self):
        import time
        from unittest.mock import patch
        from api import streaming
        def slow():
            yield "a"
            time.sleep(0.25)
            yield "b"
        with patch.object(streaming, "HEARTBEAT_SECONDS", 0.05):
            out = list(streaming.with_heartbeat(slow()))
        self.assertEqual([item for item in out if item is not streaming.PING], ["a", "b"])
        self.assertIn(streaming.PING, out)

    def test_heartbeat_reraises_and_closes_the_source(self):
        from api import streaming
        closed = []
        def failing():
            try:
                yield "a"
                raise RuntimeError("boom")
            finally:
                closed.append(True)
        with self.assertRaises(RuntimeError):
            list(streaming.with_heartbeat(failing()))
        self.assertEqual(closed, [True])

    def test_abandoning_the_stream_closes_the_source(self):
        import time
        from api import streaming
        closed = []
        def endless():
            try:
                while True:
                    yield "x"
                    time.sleep(0.01)
            finally:
                closed.append(True)
        stream = streaming.with_heartbeat(endless())
        next(stream)
        stream.close()
        time.sleep(0.2)
        self.assertEqual(closed, [True])

    def test_sse_frames_the_heartbeat_as_a_comment(self):
        from unittest.mock import patch
        from api import streaming
        from api.routes.assistant import sse
        from services.assistant import Chunk
        with patch.object(streaming, "with_heartbeat", lambda items: iter([streaming.PING, *items])):
            frames = list(sse(iter([Chunk("text", "hi")])))
        self.assertEqual(frames[0], ": ping\n\n")
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTEST tests/test_assistant_stream.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`api/schemas.py`:

```python
class AskMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AskRequest(BaseModel):
    """The client's current workspace bundle and the conversation so far."""

    result: dict[str, Any]
    messages: list[AskMessage]
    # The parsed blocks behind the workspace's results and attachments.
    document: list[ContentBlockOut] | None = None
```

(`Literal` import from `typing` if absent. `result_type` is removed; an old client still sending it is accepted, because extra fields are ignored.)

`api/streaming.py`, append:

```python
PING = object()


def with_heartbeat(items: Iterator[Any]) -> Iterator[Any]:
    """Yield `items`, and `PING` whenever `HEARTBEAT_SECONDS` pass with nothing to send.

    The source runs in a worker thread so a silent step (model reasoning, a fetch) cannot
    starve the connection. An exception in the source is re-raised here. When the consumer
    stops early, the worker stops at the source's next item and closes it, so a provider
    stream is not left running.
    """
    events: "queue.Queue[tuple[str, Any]]" = queue.Queue()
    stop = threading.Event()

    def pump() -> None:
        try:
            for item in items:
                if stop.is_set():
                    break
                events.put(("item", item))
        except Exception as exc:  # noqa: BLE001
            events.put(("error", exc))
        finally:
            close = getattr(items, "close", None)
            if close is not None:
                close()
            events.put(("end", None))

    threading.Thread(target=pump, daemon=True).start()
    try:
        while True:
            try:
                kind, value = events.get(timeout=HEARTBEAT_SECONDS)
            except queue.Empty:
                yield PING
                continue
            if kind == "end":
                return
            if kind == "error":
                raise value
            yield value
    finally:
        stop.set()
```

Add `Iterator` to the `typing` import.

`api/routes/assistant.py`:

- `sse(chunks)`: iterate `for chunk in streaming.with_heartbeat(chunks):`; if `chunk is streaming.PING`, `yield ": ping\n\n"` and continue; otherwise frame as today. Import `from api import streaming`.
- `ask_stream`: after building the client, reject oversize requests:

```python
    problem = _request_size_problem(request)
    if problem:
        raise HTTPException(status_code=413, detail=problem)
```

```python
def _request_size_problem(request: AskRequest) -> str | None:
    """Why a request is too large to answer, or None. Checked before the stream opens."""
    blocks = request.document or []
    images = [block.image for block in blocks if block.image is not None]
    checks = (
        (len(request.messages), limits.MAX_REQUEST_MESSAGES, "messages"),
        (len(blocks), limits.MAX_REQUEST_BLOCKS, "document blocks"),
        (len(images), limits.MAX_REQUEST_IMAGES, "images"),
        (sum(len(image.data_base64) for image in images), limits.MAX_REQUEST_IMAGE_CHARS, "image data"),
    )
    for size, cap, what in checks:
        if size > cap:
            return f"This conversation carries too many {what} ({size} > {cap}). Start a new chat or remove results."
    return None
```

- The `assistant_answer_stream(...)` call drops `request.result_type`.
- Docstring of `ask_stream`: replace "The request contract intentionally matches /ask so saved results, source documents, and stateless conversation history keep the same semantics." with "Each request carries the current workspace and the conversation; nothing is kept between requests."
- Delete the unreachable `except HTTPException: raise` in the digest route.
- Import `from services.assistant import limits`.

- [ ] **Step 4: Run tests**

Run: `PYTEST tests/test_assistant_stream.py -q`
Expected: all pass.

---

### Task 8: The browser: one mode, pruned history, shared constants

**Files:**
- Modify: `web/components/assistant/ask.tsx`, `web/components/assistant/workspace-ask.tsx`, `web/lib/assistant-conversation.ts`, `web/lib/document-formats.ts`
- Create: `web/lib/assistant-suggestions.ts`, `web/lib/workspace-documents.ts`
- Test: `web/lib/assistant-conversation.test.ts`, `web/lib/assistant-transport.test.ts`, `web/lib/assistant-suggestions.test.ts` (rewrite), `web/lib/workspace-documents.test.ts` (new)

**Interfaces:**
- Produces: `MAX_ATTACHMENTS` in `document-formats.ts`; `openers(state: { reviewPhase?: string; attachments: number; results: number }): [string, string]` in `assistant-suggestions.ts`; `AskContext = { result: unknown; document: ContentBlock[]; sources: CitationSources }`; `assistantRequest(messages, fallback, contexts)` returns `{ result, document, messages }`; `retainCited(context: AskContext, answers: string[]): AskContext`.

- [ ] **Step 1: Write the failing tests**

Add to `web/lib/assistant-conversation.test.ts`:

```typescript
import { retainCited } from "./assistant-conversation.ts";

test("an earlier question keeps only the passages its answer cites", () => {
  const block = (id: string, image = false) => ({
    id, doc_id: "d", ordinal: 0, block_type: "p", content: id, heading_stack: [], section_label: null,
    structural_meta: {}, style_hint: {},
    image: image ? { media_type: "image/png", data_base64: "QQ", sha256: id, source_media_type: "image/png" } : null,
  });
  const context = { result: { big: true }, document: [block("d/b-1", true), block("d/b-2", true)], sources: new Set(["https://x.org"]) };
  const kept = retainCited(context as never, ["See [slide](<block:d/b-2>)."]);
  assert.deepEqual(kept.document.map((b) => b.id), ["d/b-2"]);
  assert.equal(kept.result, null);
  assert.equal(kept.sources, context.sources);
});

test("the request carries no result_type", () => {
  const body = assistantRequest([], { result: {}, document: [], sources: new Set() } as never, new Map());
  assert.equal("result_type" in body, false);
});
```

Add to `web/lib/assistant-transport.test.ts`:

```typescript
test("a heartbeat comment produces nothing", () => {
  assert.equal(readEvent(": ping"), null);
});
```

Replace `web/lib/assistant-suggestions.test.ts` with:

```typescript
import assert from "node:assert/strict";
import test from "node:test";
import { openers } from "./assistant-suggestions.ts";

test("every state offers exactly two questions", () => {
  for (const state of [
    { attachments: 0, results: 0 }, { attachments: 0, results: 1 }, { attachments: 0, results: 3 },
    { attachments: 2, results: 0 }, { attachments: 2, results: 2 }, { reviewPhase: "target_review", attachments: 0, results: 1 },
  ]) {
    const pair = openers(state);
    assert.equal(pair.length, 2);
    for (const opener of pair) assert.match(opener, /[?.]$/);
  }
});

test("an empty workspace asks about the tools, not a result", () => {
  assert.deepEqual(openers({ attachments: 0, results: 0 }), ["Which tool should I use?", "What skills can you use here?"]);
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `web/`): `node --test --experimental-strip-types lib/assistant-conversation.test.ts lib/assistant-transport.test.ts lib/assistant-suggestions.test.ts`
Expected: FAIL (`retainCited` not exported; `./assistant-suggestions.ts` missing).

- [ ] **Step 3: Implement**

`web/lib/document-formats.ts`, beside the attachment constants:

```typescript
/** How many files one conversation may attach. */
export const MAX_ATTACHMENTS = 5;
```

`web/lib/assistant-suggestions.ts`:

```typescript
/**
 * The two questions the empty chat offers, for what the workspace holds right now.
 *
 * Asked as questions, never as a list of skills: the agent answers from the catalog in
 * its own prompt, so adding a skill changes no text here.
 */
export function openers(state: { reviewPhase?: string; attachments: number; results: number }): [string, string] {
  if (state.reviewPhase) return ["Explain the selected review item.", "What evidence should I check before deciding?"];
  if (state.attachments > 0 && state.results > 0) return ["Summarize the attached context.", "Compare the attachment with my results."];
  if (state.attachments > 0) return ["Summarize the attached context.", "What important details does it contain?"];
  if (state.results > 1) return ["What skills can you use here?", "Where do the results agree or differ?"];
  if (state.results === 1) return ["Summarize the available result.", "What skills can you use here?"];
  return ["Which tool should I use?", "What skills can you use here?"];
}
```

`web/lib/assistant-conversation.ts`:

- `AskContext` loses `resultType`.
- `assistantRequest` returns `{ result: current.result, document: current.document, messages: … }` (no `result_type`).
- Add:

```typescript
const BLOCK_LINK = /<block:([^>]+)>/g;

/** What an earlier question still needs once the workspace has moved on: the passages its
 * answer cites and the links it may open. The rest of that workspace, image bytes
 * included, is released rather than held for the life of the chat. */
export function retainCited(context: AskContext, answers: string[]): AskContext {
  const cited = new Set(answers.flatMap((answer) => [...answer.matchAll(BLOCK_LINK)].map((match) => match[1])));
  return { result: null, document: context.document.filter((block) => cited.has(block.id)), sources: context.sources };
}
```

`web/components/assistant/ask.tsx`:

- Remove the `resultType` prop, its type, the `SUGGESTIONS` and `DEFAULT_SUGGESTIONS` constants and their comments, and the misplaced JSDoc above `latestActivity`.
- `result` becomes a required, non-null prop; delete `hasResult` and every branch on it (`{!hasResult && …}`, `!hasResult ||`, `|| !hasResult`, `hasResult &&`).
- Suggestions: `const suggestions = openers({ reviewPhase, attachments: attachments.length, results: resultCount });`.
- Placeholder: `"Ask about tools or results…"`.
- Attachments: replace the literal `5`s with `MAX_ATTACHMENTS` (the slice, the disabled check, and the hint `Up to {MAX_ATTACHMENTS} {ATTACHMENT_FORMAT_HINT}`).
- The context memo drops `resultType`.
- On send, before `contexts.current.set(contextId, context)`, release what earlier questions no longer need:

```typescript
    for (const [id, previous] of contexts.current) {
      if (previous === context || previous.result === null) continue;
      const answers = conversationTurns(messages, contexts.current)
        .filter((turn) => turn.context === previous && turn.message.role === "assistant")
        .map((turn) => messageText(turn.message));
      contexts.current.set(id, retainCited(previous, answers));
    }
```

`web/components/assistant/workspace-ask.tsx`:

- Stop passing `resultType="workspace"`.
- `addResult` gains a final parameter `panel = true`; attach `priority_digest`/`priority_item_ids` only when `panel` is true. The Inspector call passes `false` (its digests live on each review).

- [ ] **Step 3b: Document identity by content, decided once**

A passage's address is `<filename stem>/b-<ordinal>`, so two runs over different versions of `cTPP.docx` share addresses, and the bundle kept whichever run arrived first (`workspace-ask.tsx`, `if (!blocks.has(block.id))`). One rule fixes it, here and nowhere else — the browser also renders citations, so the model and the popovers share this one address space. The server trusts it and does not re-check.

Write the failing test first, `web/lib/workspace-documents.test.ts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";
import type { ContentBlock } from "./api";
import { resolveDocumentVersions } from "./workspace-documents.ts";

const block = (doc: string, n: number, content: string): ContentBlock => ({
  id: `${doc}/b-${String(n).padStart(4, "0")}`, doc_id: doc, ordinal: n, block_type: "paragraph", content,
  heading_stack: [], section_label: null, structural_meta: {}, style_hint: {}, image: null,
});
const run = (id: string, text: string) => ({
  id,
  blocks: [block("cTPP", 1, text), block("cTPP", 2, "shared")],
  analysis: { cited_block_ids: ["cTPP/b-0001"], reference_doc_id: "cTPP", note: "cTPP/b-0001 is quoted" },
});

test("the same document read by two runs stays one document", () => {
  const [a, b] = resolveDocumentVersions([run("a", "same"), run("b", "same")]);
  assert.deepEqual(a.blocks.map((x) => x.id), ["cTPP/b-0001", "cTPP/b-0002"]);
  assert.deepEqual(b.blocks.map((x) => x.id), ["cTPP/b-0001", "cTPP/b-0002"]);
});

test("two versions under one name are both kept, each run citing its own", () => {
  const [a, b] = resolveDocumentVersions([run("a", "v1"), run("b", "v2")]);
  assert.notEqual(a.blocks[0].doc_id, b.blocks[0].doc_id);
  for (const version of [a, b]) {
    assert.match(version.blocks[0].doc_id, /^cTPP@[0-9a-f]{6}$/);
    assert.equal(version.blocks[0].id, `${version.blocks[0].doc_id}/b-0001`);
    const analysis = version.analysis as { cited_block_ids: string[]; reference_doc_id: string; note: string };
    assert.deepEqual(analysis.cited_block_ids, [version.blocks[0].id]);
    assert.equal(analysis.reference_doc_id, version.blocks[0].doc_id);
    assert.equal(analysis.note, "cTPP/b-0001 is quoted"); // prose is never rewritten
  }
});

test("the addresses do not depend on the order runs arrive in", () => {
  const forward = resolveDocumentVersions([run("a", "v1"), run("b", "v2")]);
  const backward = resolveDocumentVersions([run("b", "v2"), run("a", "v1")]);
  assert.deepEqual(forward[0].blocks.map((x) => x.id), backward[1].blocks.map((x) => x.id));
});
```

Then `web/lib/workspace-documents.ts`:

```typescript
import type { ContentBlock } from "./api";

/**
 * Which document a run read, decided by content rather than by filename.
 *
 * A block's address is `<filename stem>/b-<ordinal>`, so two runs over different versions
 * of `cTPP.docx` produce the same addresses. Each run's document is fingerprinted from its
 * blocks; one fingerprint per name is one document shared by every run that read it. More
 * than one fingerprint under a name tags every version - `cTPP@3f9a1c` - so each run's
 * citations open the text it actually read, whatever order the runs arrive in.
 *
 * Only reference fields are rewritten: a string that is exactly a renamed block ID, and a
 * `doc_id` / `*_doc_id` field that is exactly a renamed document. Prose is never touched.
 */
export type WorkspaceRun = { id: string; blocks: ContentBlock[]; analysis: unknown };

export function resolveDocumentVersions<T extends WorkspaceRun>(runs: T[]): T[] {
  const fingerprints = runs.map((run) => {
    const byDoc = new Map<string, ContentBlock[]>();
    for (const block of run.blocks) byDoc.set(block.doc_id, [...(byDoc.get(block.doc_id) ?? []), block]);
    return new Map([...byDoc].map(([doc, blocks]) => [doc, fingerprint(blocks)]));
  });
  const versions = new Map<string, Set<string>>();
  for (const prints of fingerprints) {
    for (const [doc, print] of prints) versions.set(doc, (versions.get(doc) ?? new Set()).add(print));
  }
  return runs.map((run, index) => {
    const docRenames = new Map<string, string>();
    for (const [doc, print] of fingerprints[index]) {
      if ((versions.get(doc)?.size ?? 0) > 1) docRenames.set(doc, `${doc}@${print.slice(0, 6)}`);
    }
    if (docRenames.size === 0) return run;
    const blockRenames = new Map<string, string>();
    const blocks = run.blocks.map((block) => {
      const doc = docRenames.get(block.doc_id);
      if (!doc) return block;
      const suffix = block.id.startsWith(`${block.doc_id}/`) ? block.id.slice(block.doc_id.length + 1) : block.id;
      const id = `${doc}/${suffix}`;
      blockRenames.set(block.id, id);
      return { ...block, id, doc_id: doc };
    });
    return { ...run, blocks, analysis: rewrite(run.analysis, blockRenames, docRenames, "") };
  });
}

function rewrite(value: unknown, blocks: Map<string, string>, docs: Map<string, string>, key: string): unknown {
  if (typeof value === "string") {
    if (blocks.has(value)) return blocks.get(value);
    if ((key === "doc_id" || key.endsWith("_doc_id")) && docs.has(value)) return docs.get(value);
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => rewrite(item, blocks, docs, key));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([child, item]) => [child, rewrite(item, blocks, docs, child)]));
  }
  return value;
}

/** A stable 53-bit hash (cyrb53) of a document's block IDs, text and image hashes. */
function fingerprint(blocks: ContentBlock[]): string {
  const text = blocks.map((block) => `${block.id}\u0000${block.content}\u0000${block.image?.sha256 ?? ""}`).join("\u0001");
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ code, 2654435761);
    h2 = Math.imul(h2 ^ code, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
}
```

In `web/components/assistant/workspace-ask.tsx`, stop adding results one at a time. Collect every final run first as `{ id, resultType, label, value, panel }`, split each with `splitResultContext(value)` into `{ id, blocks: context.document ?? [], analysis: context.analysis }`, pass the list through `resolveDocumentVersions`, and only then fill `results` and the shared `blocks` map from the resolved runs (`document_block_ids` from each resolved run's block IDs; the existing `if (!blocks.has(block.id))` stays and is now only ever true for identical text). Review drafts and attachments do not go through it: a draft already carries its own `Review draft · …` document names, and attachments carry unique `attachment-…` IDs.

Run: `node --test --experimental-strip-types lib/workspace-documents.test.ts`
Expected: 3 passed.

- [ ] **Step 4: Run web checks**

Run (from `web/`): `npx tsc --noEmit && npm test && npm run -s test:motion`
Expected: typecheck clean, all tests pass (the old `assistant-suggestions` source-parsing test is gone; `assistant-continuity` tests still pass).

---

### Task 9: Documentation that matches the harness

**Files:**
- Modify: `services/assistant/README.md`, `shared/product_knowledge.json`, `AGENTS.md`
- Test: `tests/test_product_knowledge_contract.py`, `web/lib/product-knowledge.test.ts` (existing)

- [ ] **Step 1: `services/assistant/README.md`**

- In the input row, replace "Workspace/result JSON, context type, source blocks, conversation history" with "Workspace bundle, source blocks, conversation history".
- Replace the paragraph beginning "The bounded tool loop can find and read canonical product documentation" through "…fetch only URLs cited by the submitted analyses." with: "Each question builds one workspace index from the bundle and blocks. The system prompt is a fixed prefix (rules, tool inventory, documentation map) followed by a bounded map of the workspace: the legends for held result types, each result and the documents it read, and each document's block count, headings and visual locations. No image is in the prompt. The bounded tool loop reaches everything else by exact ID: product documentation, result trees, document text by block or range, retained visuals through `view_document_visuals` (capped per call and per question), and the full text behind URLs the analyses already cite."
- Development section: list `workspace.py`, `sources.py`, `limits.py`, `prompt.py`, `protocols.py`, `registry.py`, `resources.py`, `document.py`, `navigator.py`, `web_sources.py`, `knowledge.py`, `skills.py`, `legends.py`, `priorities.py` with one line each on its job.

- [ ] **Step 2: `shared/product_knowledge.json`**

Edit with a JSON load/dump that preserves the file's format (`indent=2`, `ensure_ascii=False`, trailing newline):

- `sections[4].content[0].items[5].description` → `"Assistant can find and read the exact parsed text behind available results and the active review, and look at a retained image block when a question depends on what it shows."`
- `sections[4].content[1].text` → `"Assistant starts from a compact map of the workspace and uses bounded tools to read only the relevant documentation section, result subtree, document blocks, retained visuals, or cited source. It does not place every available artifact, or any image, into every model prompt."`

- [ ] **Step 3: `AGENTS.md`**

In "Results, Ask, and API", after the paragraph that begins "Ask is stateless and read-only.", add:

```markdown
- Ask's prompt carries a bounded map, never the workspace itself: a fixed prefix, the
  legends for held result types, and per result and per document a bounded number of
  lines. Every result subtree, source block and retained image is reached by exact ID
  through the registry; no image enters a prompt unrequested, and visuals are capped per
  call and per question in `services/assistant/limits.py`. A new kind of reachable content
  is a source over the workspace index plus its registry entries, never a new prompt section.
```

- [ ] **Step 4: Run the documentation contracts**

Run: `PYTEST tests/test_product_knowledge_contract.py -q` and (from `web/`) `node --test --experimental-strip-types lib/product-knowledge.test.ts`
Expected: pass.

---

### Task 10: Whole-change verification and the measured before/after

- [ ] **Step 1: Full Python suite**

Run: `PYTEST tests -q`
Expected: all pass (baseline before this plan: 1,094 passed, 9 skipped).

- [ ] **Step 2: Full web checks**

Run (from `web/`): `npx tsc --noEmit && npm test && for s in test:preview test:block-reference test:evidence-map test:comparator-plot test:quantitative-review test:scout-review test:result-file test:projection-roles test:safety-observations test:document-trace test:motion; do npm run -s $s; done && npm run build`
Expected: all pass, build succeeds.

- [ ] **Step 3: Whitespace**

Run: `git diff --check`
Expected: no output.

- [ ] **Step 4: Measure one real question**

Start the API with the key in `.env` (`docker compose up -d --build api web`), load a Screener result over two or more PPTX decks, and ask one question about a specific slide and one general question. Read the two `assistant_question` log lines (`docker compose logs api | grep assistant_question`). Record `model_calls`, `input_tokens`, `cached_input_tokens`, `visuals_viewed` for each, and compare `input_tokens` against the pre-change estimate (≈1,100 tokens per slide image × images held × model calls). Report both numbers to the user.
