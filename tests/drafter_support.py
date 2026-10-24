"""Shared fixtures for Drafter's tests: a scripted model and a few parsed blocks."""

from __future__ import annotations

from services.chunker import ContentBlock


class ScriptedClient:
    """Answers by matching a marker in the user message; records every call.

    `script` maps a substring of the user message to a list of replies, consumed in order,
    so a test can say "the first answer about efficacy is invalid, the second is fine".
    """

    def __init__(self, script: dict[str, list]):
        self.script = {marker: list(replies) for marker, replies in script.items()}
        self.calls: list[tuple[str, str, dict]] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        self.calls.append((system_prompt, user_message, {"max_tokens": max_tokens, **kwargs}))
        for marker, replies in self.script.items():
            if marker in user_message and replies:
                reply = replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply
        raise AssertionError(f"no scripted reply for: {user_message[:200]}")


def block(identifier: str, content: str, block_type: str = "paragraph") -> ContentBlock:
    return ContentBlock(
        id=identifier, doc_id=identifier.split("/")[0], ordinal=int(identifier.rsplit("-", 1)[-1]),
        block_type=block_type, content=content, heading_stack=[], structural_meta={}, style_hint={},
        source_format="docx",
    )


class StageClient:
    """Answers by stage (the request's schema name), letting a test script a whole run."""

    def __init__(self, **stages):
        self.stages = stages
        self.calls: list[tuple[str, str]] = []
        self.tasks: dict[str, set[str]] = {}

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        name = kwargs["schema_name"]
        self.calls.append((name, user_message))
        self.tasks.setdefault(name, set()).add(kwargs.get("task", "reasoning"))
        answer = self.stages[name]
        reply = answer(user_message) if callable(answer) else answer
        if isinstance(reply, Exception):
            raise reply
        return reply

    def count(self, name: str) -> int:
        return sum(1 for called, _ in self.calls if called == name)


def variable_in(message: str, intervention_class: str = "vaccine") -> str:
    """The variable name a stage's user message is about.

    Planning names the attribute key and its phrase; reading and suggesting name only the
    phrase, which is mapped back to the key here.
    """
    from shared.vocabulary import attribute_definitions, searchable_attribute_phrase

    for line in message.splitlines():
        if line.startswith("Variable: "):
            named = line.removeprefix("Variable: ")
            if " (" in named:
                return named.split(" (", 1)[0]
            return next(definition.name for definition in attribute_definitions(intervention_class)
                        if searchable_attribute_phrase(definition.name) == named)
    raise AssertionError("message names no variable")
