"""openFDA, the one provider behind the `fda` and `fda_safety` lanes.

Both lanes spend one quota, so its pacing, its key and its answer to "nothing matched" are
stated once, here. openFDA answers a search that matched nothing with a 404 whose body says
`NOT_FOUND`; that is an empty answer, and reading it as a failure would report a lane that
worked as one that broke.
"""

from __future__ import annotations

from typing import Any

from ..calls import provider_request
from ..errors import RetrievalError
from ..models import SearchRuntime, SourceSpec

BASE_URL = "https://api.fda.gov"
#: The rate group, and the key's name in `SearchRuntime.credentials`.
OPENFDA = "openfda"
#: openFDA allows 240 calls a minute with or without a key - one every 0.25 s - and a key
#: raises only the daily cap, from 1,000 to 120,000. Kept just below the per-minute limit.
MIN_REQUEST_INTERVAL_SECONDS = 0.3


def openfda_search(
    runtime: SearchRuntime,
    spec: SourceSpec,
    endpoint: str,
    search: str,
    *,
    limit: int,
    count: str = "",
) -> list[dict[str, Any]]:
    """Return one openFDA endpoint's `results` for a search, in openFDA's order.

    `endpoint` is the path below the API root (`drug/label.json`). `count` asks for a
    term count over that field instead of records, which is how FAERS reports reactions.
    """
    query: dict[str, Any] = {"search": search, "limit": limit}
    if count:
        query["count"] = count
    key = runtime.credential(OPENFDA)
    payload = provider_request(
        runtime,
        spec,
        operation=endpoint.removesuffix(".json"),
        url=f"{BASE_URL}/{endpoint}",
        query=query,
        auth_query={"api_key": key} if key else None,
        no_match_status=404,
    )
    if payload is None:
        return []
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise RetrievalError("openFDA", "invalid_response", "no results list")
    return [record for record in results if isinstance(record, dict)]


def phrase(value: str) -> str:
    """A value as one quoted openFDA phrase, with the characters that would end it removed."""
    return '"' + value.replace("\\", " ").replace('"', " ").strip() + '"'


def first(value: Any) -> str:
    """The first non-blank string of an openFDA field, which is usually a list."""
    for item in strings(value):
        return item
    return ""


def strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [" ".join(item.split()) for item in values if isinstance(item, str) and item.strip()]
