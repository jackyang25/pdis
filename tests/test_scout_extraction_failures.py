"""Extraction failures must not become successful empty reviews."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from shared.openai_client import OpenAIClient
from tests.test_scout_unit_reconciliation import FixtureClient, extract, group, unit
from tests.test_streaming import drain


@pytest.mark.parametrize("content", [None, '{"units": []}'])
def test_output_limit_never_returns_a_partial_or_empty_conclusion(content):
    with patch("openai.OpenAI"):
        client = OpenAIClient(api_key="test")
    client.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(
            content=content, refusal=None))], usage=None,
    )
    with pytest.raises(RuntimeError, match="response limit"):
        client.call_structured("system", "user", 8000, schema_name="test", schema={})


@pytest.mark.parametrize("payload", [
    None, {"units": None},
    {"units": [unit("a", "Timing.", "wrong/block")]},
    {"units": [unit("a", "Timing."), unit("b", "Approval.", "wrong/block")]},
])
def test_invalid_extraction_stops_instead_of_publishing_empty_result(payload):
    client = Mock()
    client.call_structured.return_value = payload
    with pytest.raises(ValueError, match="extraction"):
        extract(client)
    assert client.call_structured.call_count == 2


def test_valid_empty_extraction_is_not_retried():
    client = Mock()
    client.call_structured.return_value = {"units": []}
    assert extract(client) == []
    assert client.call_structured.call_count == 1


def test_progress_reports_extraction_then_identity():
    client = FixtureClient([unit("a", "Timing."), unit("b", "Timing.")],
                           [[group("unit-0", "unit-0", "unit-1")]])
    stages = []
    extract(client, progress_callback=stages.append)
    assert stages == ["units", "unit_reconciliation"]


def test_provider_failure_is_not_retried_as_invalid_extraction():
    client = Mock()
    client.call_structured.side_effect = RuntimeError("response limit")
    with pytest.raises(RuntimeError, match="response limit"):
        extract(client)
    assert client.call_structured.call_count == 1


def test_extraction_failure_uses_existing_stage_error_stream():
    client = Mock()
    client.call_structured.side_effect = RuntimeError("response limit")
    events = drain(lambda progress: extract(client, progress_callback=progress))
    assert events == [
        {"event": "stage", "name": "units"},
        {"event": "error", "detail": "units: response limit"},
    ]
