"""The one validated, retried schema-bound request every stage uses."""

from __future__ import annotations

import unittest

import json
import logging

from shared.ai import (
    FAILURE_CODES,
    MAX_RETRY_TOKENS,
    ResponseRefusedError,
    ResponseTruncatedError,
    after_truncation,
    failure_code,
    log_model_call,
    prompt_cache_key,
    request_validated,
)
from shared.errors import ModelResponseError


class _Client:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def call_structured(self, system_prompt, user_message, max_tokens, **kwargs):
        self.calls.append({"user": user_message, "max_tokens": max_tokens, **kwargs})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _parse(payload):
    if not payload or "value" not in payload:
        raise ValueError("value is required")
    return payload["value"]


def _request(client, **overrides):
    arguments = dict(
        schema_name="s", schema={"type": "object"}, max_tokens=100,
        parse=_parse, failure="Stage could not decide",
    )
    arguments.update(overrides)
    return request_validated(client, "system", "document", **arguments)


class RequestValidatedTests(unittest.TestCase):
    def test_a_valid_first_answer_is_returned_without_retry(self) -> None:
        client = _Client({"value": 1})
        self.assertEqual(_request(client), 1)
        self.assertEqual(len(client.calls), 1)

    def test_a_validation_failure_is_retried_with_its_error(self) -> None:
        client = _Client({}, {"value": 2})
        self.assertEqual(_request(client), 2)
        self.assertIn("value is required", client.calls[1]["user"])

    def test_the_repair_note_follows_trailing_text_when_there_is_one(self) -> None:
        client = _Client({}, {"value": 2})
        _request(client, trailing_text="question")
        self.assertEqual(client.calls[1]["user"], "document")
        self.assertTrue(client.calls[1]["trailing_text"].startswith("question"))
        self.assertIn("value is required", client.calls[1]["trailing_text"])

    def test_truncation_is_retried_with_more_room_and_no_repair_note(self) -> None:
        client = _Client(ResponseTruncatedError("cut off"), {"value": 3})
        self.assertEqual(_request(client), 3)
        self.assertEqual([call["max_tokens"] for call in client.calls], [100, 200])
        self.assertEqual(client.calls[1]["user"], "document")

    def test_a_stage_that_states_its_effort_is_retried_at_a_lower_one_with_the_same_budget(self) -> None:
        """More room at the same effort only buys more reasoning; a live Drafter
        suggestion spent 16k and then 32k reasoning tokens that way."""
        client = _Client(ResponseTruncatedError("cut off"), {"value": 3})
        self.assertEqual(_request(client, effort="medium"), 3)
        self.assertEqual([(call["effort"], call["max_tokens"]) for call in client.calls],
                         [("medium", 100), ("low", 100)])

    def test_at_the_lowest_effort_the_budget_grows_but_never_past_its_tier_ceiling(self) -> None:
        self.assertEqual(after_truncation("fast", "low", 1000), ("low", 2000))
        ceiling = MAX_RETRY_TOKENS["fast"]
        self.assertEqual(after_truncation("fast", "low", ceiling - 1), ("low", ceiling))
        self.assertIsNone(after_truncation("fast", "low", ceiling))
        self.assertIsNone(after_truncation("reasoning", None, MAX_RETRY_TOKENS["reasoning"]))

    def test_a_cut_off_that_cannot_be_retried_differently_is_final(self) -> None:
        ceiling = MAX_RETRY_TOKENS["reasoning"]
        client = _Client(ResponseTruncatedError("cut off"), {"value": 3})
        with self.assertRaises(ResponseTruncatedError):
            _request(client, effort="low", max_tokens=ceiling)
        self.assertEqual(len(client.calls), 1, "the same request again would be cut off again")

    def test_a_refusal_is_never_retried(self) -> None:
        client = _Client(ResponseRefusedError("declined"), {"value": 1})
        with self.assertRaises(ResponseRefusedError) as raised:
            _request(client)
        self.assertEqual(raised.exception.code, "response_refused")
        self.assertEqual(len(client.calls), 1)

    def test_the_call_policy_reaches_the_client(self) -> None:
        client = _Client({"value": 1})
        _request(client, task="fast", effort="low", verbosity="low", cache_key="k")
        call = client.calls[0]
        self.assertEqual((call["task"], call["effort"], call["verbosity"], call["cache_key"]),
                         ("fast", "low", "low", "k"))

    def test_requests_sharing_a_prefix_share_a_cache_key(self) -> None:
        client = _Client({"value": 1}, {"value": 2}, {"value": 3})
        _request(client, trailing_text="first question")
        _request(client, trailing_text="second question")
        request_validated(client, "system", "another document", schema_name="s",
                          schema={"type": "object"}, max_tokens=100, parse=_parse, failure="x")
        keys = [call["cache_key"] for call in client.calls]
        self.assertEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0], keys[2])
        self.assertTrue(keys[0].startswith("s:"))
        self.assertEqual(keys[0], prompt_cache_key("s", "system", "document"))

    def test_repeated_truncation_keeps_its_code(self) -> None:
        client = _Client(ResponseTruncatedError("cut off"), ResponseTruncatedError("cut off"))
        with self.assertRaises(ResponseTruncatedError) as raised:
            _request(client)
        self.assertEqual(raised.exception.code, "response_truncated")
        self.assertIn("Stage could not decide", str(raised.exception))

    def test_exhausted_validation_is_an_invalid_model_response(self) -> None:
        client = _Client(None, {})
        with self.assertRaises(ModelResponseError) as raised:
            _request(client)
        self.assertNotIsInstance(raised.exception, ResponseTruncatedError)
        self.assertEqual(raised.exception.code, "invalid_model_response")
        self.assertIn("value is required", str(raised.exception))

    def test_provider_errors_are_not_retried(self) -> None:
        client = _Client(RuntimeError("network"), {"value": 1})
        with self.assertRaisesRegex(RuntimeError, "network"):
            _request(client)
        self.assertEqual(len(client.calls), 1)


class UsageLineTests(unittest.TestCase):
    def test_a_usage_line_names_the_attempt_it_belongs_to(self) -> None:
        lines: list[str] = []

        class Recording:
            def call_structured(self, *_args, **_kwargs):
                log_model_call(schema_name="s")
                return {} if not lines[1:] else {"value": 1}

        handler = logging.Handler()
        handler.emit = lambda record: lines.append(record.getMessage())  # type: ignore[method-assign]
        logger = logging.getLogger("shared.ai")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            _request(Recording())
        finally:
            logger.removeHandler(handler)
        attempts = [json.loads(line.removeprefix("model_call "))["attempt"] for line in lines if line.startswith("model_call ")]
        self.assertEqual(attempts, [1, 2])
        # The first answer was refused, and the log says why, so a retry rate can be traced
        # to the check that caused it.
        retries = [json.loads(line.removeprefix("model_retry ")) for line in lines if line.startswith("model_retry ")]
        self.assertEqual([(retry["schema_name"], retry["attempt"]) for retry in retries], [("s", 1)])
        self.assertTrue(retries[0]["reason"])


class FailureCodeTests(unittest.TestCase):
    def test_codes_come_from_the_closed_vocabulary(self) -> None:
        self.assertEqual(failure_code(ResponseTruncatedError("x")), "response_truncated")
        self.assertEqual(failure_code(ModelResponseError("x")), "invalid_model_response")
        self.assertEqual(failure_code(RuntimeError("x")), "provider_error")
        self.assertEqual(failure_code(ResponseRefusedError("x")), "response_refused")
        for exc in (ResponseTruncatedError("x"), ModelResponseError("x"), OSError("x")):
            self.assertIn(failure_code(exc), FAILURE_CODES)


if __name__ == "__main__":
    unittest.main()
