"""One schema-bound model request for every service.

Each service declares its own ``LLMClientProtocol`` — that stays deliberate, so a
service's public contract does not depend on this module. What was duplicated is
the *call* and its retry: build the request, treat anything that is not a payload
object as no answer, and give a stage one more attempt when its answer failed
validation or was cut off. That is here, once, with the call policy a stage states
beside it: the tier, the reasoning effort and the token budget.

Provider clients depend on this module, never the reverse: it names the task
tiers, the efforts, the failures both clients raise, and the one usage line every
call logs. Scout layers its ``AIContract`` unwrapping on top of
:func:`request_validated`.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
from typing import Any, Callable, Literal, Protocol, TypeVar

import anthropic
import openai

from shared.errors import ModelResponseError
from shared.references import ReferenceDecodeError, prepare_references

logger = logging.getLogger(__name__)

ModelTask = Literal["fast", "reasoning"]

#: How hard the model reasons before answering, lowest first. The values both tiers
#: accept through the gateway: the fast tier also takes `none`, the reasoning tier
#: does not, and neither takes `minimal`. `None` at a call site means the provider's
#: default, which is what a stage that has not stated its effort keeps.
Effort = Literal["low", "medium", "high"]
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high")

#: How long the written fields of an answer are. Optional; `None` is the default.
Verbosity = Literal["low", "medium", "high"]

#: The largest output budget either tier serves. The reasoning tier refuses more than
#: 128k completion tokens; the fast tier is held to the same ceiling.
MODEL_OUTPUT_CAP = 128_000

#: The largest budget a truncation retry may grow to, per tier: half the output cap. A
#: stage that still needs more than this is asking for one answer that should be several
#: requests. Both tiers share it today; the table is per tier so either can move alone.
MAX_RETRY_TOKENS: dict[ModelTask, int] = {"fast": 64_000, "reasoning": 64_000}

_T = TypeVar("_T")

NO_ANSWER = "no structured answer was returned"
TRUNCATED = "the answer was cut off at its token limit"


class ResponseTruncatedError(ModelResponseError):
    """The provider stopped at the token budget before the answer was complete.

    It is a failure of one request, not a verdict: a stage may retry it with less
    reasoning or more room, and if it is still raised the run records the code below.
    """

    code = "response_truncated"


class ResponseRefusedError(ModelResponseError):
    """The provider declined the request: a refusal, or a content filter stopping it.

    Never retried. The same prompt meets the same policy, so a second attempt buys a
    second refusal at the same price.
    """

    code = "response_refused"


#: The closed vocabulary a result records beside a stage failure's prose. A
#: consumer reads the code, never the message, to tell the failures apart.
FAILURE_CODES = (
    "response_truncated", "response_refused", "invalid_model_response", "provider_error",
)
FailureCode = Literal[
    "response_truncated", "response_refused", "invalid_model_response", "provider_error",
]


#: What a stage that records its failure instead of stopping the run may catch: a
#: model answer that stayed unusable, or the provider failing after the SDK's own
#: retries. Anything else is a programming error and must still raise.
RECORDABLE_FAILURES: tuple[type[Exception], ...] = (
    ModelResponseError,
    openai.APIError,
    anthropic.APIError,
)


def failure_code(exc: BaseException) -> FailureCode:
    """The code for a stage failure a result records instead of raising.

    A model response that stayed unusable carries its own code; anything else
    reaching a recording site is the provider's failure (network, status, timeout).
    Callers catch only what they mean to record, so programming errors still raise.
    """
    if isinstance(exc, ModelResponseError):
        return exc.code  # type: ignore[return-value]
    return "provider_error"


class StructuredLLMClient(Protocol):
    """The client shape this helper needs.

    Structurally identical to each service's ``LLMClientProtocol``; declared here
    only so this function can type its own parameter without importing a service.
    ``trailing_text`` is sent after the images, so per-item text can follow the
    content that stays the same across a stage's requests. ``effort``, ``verbosity``
    and ``cache_key`` are the stage's call policy; ``None`` leaves the provider's
    default, and a provider without the concept ignores it.
    """

    def call_structured(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int,
        *,
        schema_name: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        trailing_text: str = "",
        task: ModelTask = "reasoning",
        effort: Effort | None = None,
        verbosity: Verbosity | None = None,
        cache_key: str | None = None,
    ) -> dict[str, Any] | None:
        ...


# ---------------------------------------------------------------------------
# Usage, one line per call
# ---------------------------------------------------------------------------

_ATTEMPT: contextvars.ContextVar[int] = contextvars.ContextVar("model_call_attempt", default=1)


def current_attempt() -> int:
    """Which attempt of a validated request the call in flight is, from 1."""
    return _ATTEMPT.get()


def log_model_call(**fields: Any) -> None:
    """The one usage line a provider client writes per call.

    Names, counts and timings only: never a prompt, an answer, or a credential. The
    line is JSON after its tag, as the Assistant's `assistant_question` line is, so
    one query reads both.
    """
    fields.setdefault("attempt", current_attempt())
    logger.info("model_call %s", json.dumps(fields, sort_keys=True, default=str))


def prompt_cache_key(
    schema_name: str, system_prompt: str, user_message: str,
    images: list[dict[str, str]] | None = None,
) -> str:
    """A stable routing key for requests that share a prefix.

    The prefix is everything before ``trailing_text``: the system prompt, the shared
    message and its images. Requests that differ only in what follows it - the next
    rubric unit, question or requirement - get the same key, so the provider sends
    them where that prefix is already cached.
    """
    digest = hashlib.sha256()
    for part in (schema_name, system_prompt, user_message,
                 *(image.get("block_id", "") for image in images or ())):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return f"{schema_name[:40]}:{digest.hexdigest()[:24]}"


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------


def request_structured(
    llm_client: StructuredLLMClient,
    system_prompt: str,
    user_message: str,
    *,
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int,
    images: list[dict[str, str]] | None = None,
    trailing_text: str = "",
    task: ModelTask = "reasoning",
    effort: Effort | None = None,
    verbosity: Verbosity | None = None,
    cache_key: str | None = None,
) -> dict[str, Any] | None:
    """Send one schema-bound request and return its payload object.

    Returns ``None`` when the provider returned no usable object, so callers
    handle absence explicitly rather than guarding a shape at every call site.
    A reply cut off at its budget raises :class:`ResponseTruncatedError`; a refused
    one raises :class:`ResponseRefusedError`. ``cache_key`` defaults to
    :func:`prompt_cache_key` over the request's shared prefix.
    """
    references = prepare_references(schema)
    system_prompt, user_message = references.prompts(system_prompt, user_message)
    payload = llm_client.call_structured(
        system_prompt,
        user_message,
        min(max_tokens, MODEL_OUTPUT_CAP),
        schema_name=schema_name,
        schema=references.schema,
        images=images,
        trailing_text=trailing_text,
        task=task,
        effort=effort,
        verbosity=verbosity,
        cache_key=cache_key or prompt_cache_key(schema_name, system_prompt, user_message, images),
    )
    if not isinstance(payload, dict):
        return None
    try:
        return references.decode(payload)
    except ReferenceDecodeError:
        # Never pass along a partly decoded reply or disguise an invalid citation
        # as no evidence; the caller's validation treats it as no answer.
        return None


def _default_repair(error: str) -> str:
    return f"\n\nYour prior answer failed validation: {error}. Answer again."


def after_truncation(
    task: ModelTask, effort: Effort | None, budget: int,
) -> tuple[Effort | None, int] | None:
    """The next attempt's effort and budget after a reply was cut off, or None.

    A stage that stated its effort is asked again at the next lower one with the same
    budget: a reply cut off mid-reasoning usually spent the budget thinking, and more
    room at the same effort only buys more thinking. At the lowest effort, or when no
    effort was stated, the budget doubles - never past the tier's retry ceiling or the
    model's output cap. None when neither can change, so the cut-off is final.
    """
    if effort is not None and effort != EFFORTS[0]:
        return EFFORTS[EFFORTS.index(effort) - 1], budget
    grown = min(budget * 2, MAX_RETRY_TOKENS[task], MODEL_OUTPUT_CAP)
    return (effort, grown) if grown > budget else None


def request_validated(
    llm_client: StructuredLLMClient,
    system_prompt: str,
    user_message: str,
    *,
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int,
    parse: Callable[[dict[str, Any] | None], _T],
    failure: str,
    repair: Callable[[str], str] = _default_repair,
    images: list[dict[str, str]] | None = None,
    trailing_text: str = "",
    task: ModelTask = "reasoning",
    effort: Effort | None = None,
    verbosity: Verbosity | None = None,
    cache_key: str | None = None,
    attempts: int = 2,
) -> _T:
    """Request, validate with ``parse``, and retry a bounded number of times.

    ``parse`` receives the payload (``None`` when no object came back) and either
    returns the stage's value or raises ``ValueError`` naming what was wrong; that
    message reaches the next attempt through ``repair``, appended after the
    request's last text. A truncated reply is retried as :func:`after_truncation`
    says, with no repair note, because nothing in it was wrong — it was unfinished.
    A refusal is never retried.

    When every attempt fails, raises :class:`ModelResponseError` as
    ``"{failure}: {last error}"`` — or :class:`ResponseTruncatedError` when the
    last attempt was cut off, so the recorded code says which.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    error, budget, note, truncated = NO_ANSWER, min(max_tokens, MODEL_OUTPUT_CAP), "", False
    for attempt in range(1, attempts + 1):
        token = _ATTEMPT.set(attempt)
        try:
            payload = request_structured(
                llm_client,
                system_prompt,
                user_message if trailing_text else user_message + note,
                schema_name=schema_name,
                schema=schema,
                max_tokens=budget,
                images=images,
                trailing_text=trailing_text + note if trailing_text else "",
                task=task,
                effort=effort,
                verbosity=verbosity,
                cache_key=cache_key,
            )
        except ResponseTruncatedError:
            error, note, truncated = TRUNCATED, "", True
            _log_retry(schema_name, attempt, error)
            following = after_truncation(task, effort, budget)
            if following is None:
                break
            effort, budget = following
            continue
        finally:
            _ATTEMPT.reset(token)
        truncated = False
        try:
            return parse(payload)
        except ValueError as exc:
            error = str(exc) or NO_ANSWER
            _log_retry(schema_name, attempt, error)
            note = repair(error)
    exception = ResponseTruncatedError if truncated else ModelResponseError
    raise exception(f"{failure}: {error}")


def _log_retry(schema_name: str, attempt: int, reason: str) -> None:
    """Why one attempt was not accepted, beside the call's own `model_call` line.

    The usage log counted retries without their causes: a live Scout run showed 46 of 370
    measurement mappings answered twice, and nothing said which check the first answer
    failed, so the prompt or schema could not be fixed. The reason is the validator's
    message - a structural complaint, not the reply's content - and is clipped.
    """
    logger.info("model_retry %s", json.dumps({"schema_name": schema_name, "attempt": attempt, "reason": reason[:300]}))
