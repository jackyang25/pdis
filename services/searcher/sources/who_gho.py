"""WHO Global Health Observatory adapter executed through an injected ToolUniverse connector.

The only lane in the `epidemiology` class, and it answers a different question from every
other lane. The rest report what someone did, claimed or recommended. This reports how
much of the problem there is, and where: confirmed malaria cases in Kenya in 2024, not a
trial or a paper about them.

That is what makes it worth a lane. A target profile stating "reduce cases by thirty per
cent in sub-Saharan Africa" makes a claim about a quantity, and nothing else here supplies
the number the claim is measured against.

Two calls per request, like WHO Guidelines and for the same reason: the search returns
indicator codes and names with no data attached, so a finding built from it alone would
name a statistic without stating it. Both calls are bounded - the indicator set for one
condition is a handful, and the rows are ordered newest first so the bound keeps the most
recent readings rather than an arbitrary slice.

Nothing here interpolates. A country with no row for a year has no row, and a suppressed
value keeps the provider's own text rather than becoming a zero.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..models import (
    Finding,
    IndicatorRecord,
    RetrievalIntent,
    SearchRequest,
    SearchRuntime,
    SourceAttribution,
    SourceSpec,
)
from .literature import active_tracks
from .planning import facet_groups, request_lineage

TOOLUNIVERSE_INTEGRATION = "tooluniverse"
SEARCH_TOOL = "WHOGHO_search_indicators"
DATA_TOOL = "WHOGHO_get_indicator_data"
#: Indicators one condition is read through. GHO names several per disease - confirmed
#: cases, cases treated, deaths - and each costs its own data call, so the first few by
#: the provider's own ordering are the useful set.
MAX_INDICATORS = 3
#: Country-year rows per indicator. Ordered newest first, so this keeps the most recent
#: readings across as many countries as the bound allows rather than an arbitrary slice.
MAX_ROWS = 60

logger = logging.getLogger(__name__)


class WHOGHOSource:
    spec = SourceSpec(
        key="who_gho",
        label="WHO Global Health Observatory",
        worker_limit=2,
        default_enabled=False,
        integration_key=TOOLUNIVERSE_INTEGRATION,
        operations=(SEARCH_TOOL, DATA_TOOL),
        attribution=SourceAttribution(
            label="WHO Global Health Observatory",
            url="https://www.who.int/data/gho",
            prefix="Health statistics provided by",
        ),
        evidence_class="epidemiology",
        # Rows are per country and carry their WHO region, so the lane spans
        # jurisdictions rather than belonging to one.
        jurisdiction="multi",
        # The indicator search takes a disease name and nothing else. Region is
        # deliberately absent: GHO addresses places by ISO3 code, and turning a stated
        # region into codes needs a gazetteer this repository does not have. Every row
        # carries its own place instead, so the reader gets the geography without the
        # request having to name it.
        reads=("text", "condition"),
        feeds=("burden",),
        max_results=MAX_ROWS,
    )

    def plan(self, intent: RetrievalIntent) -> list[SearchRequest]:
        requests: list[SearchRequest] = []
        for scope, queries in facet_groups(
            intent,
            fields=("condition",),
            fallbacks={"condition": intent.indication or intent.topic},
            anchors=("condition",),
            limit=self.spec.max_requests_per_intent,
        ):
            intent_ids, input_queries, document_refs = request_lineage(queries)
            condition = scope["condition"]
            requests.append(
                SearchRequest(
                    scope_ref=intent.scope_ref,
                    source=self.spec.key,
                    query=f"indicator_name_contains:{condition}",
                    tracks=tuple(active_tracks(intent)),
                    document_refs=document_refs,
                    intent_ids=intent_ids,
                    input_queries=input_queries,
                    connector=TOOLUNIVERSE_INTEGRATION,
                    operation=SEARCH_TOOL,
                    options=(
                        ("condition", condition),
                        ("indicator_limit", str(MAX_INDICATORS)),
                        ("row_limit", str(MAX_ROWS)),
                    ),
                )
            )
        return requests

    def search(
        self,
        request: SearchRequest,
        runtime: SearchRuntime,
        *,
        max_tokens: int,
        max_uses: int,
    ) -> list[Finding]:
        connector = runtime.integrations.get(TOOLUNIVERSE_INTEGRATION)
        if connector is None or not callable(getattr(connector, "run", None)):
            raise RuntimeError("ToolUniverse connector is not configured")
        condition = request.option("condition")
        if not condition:
            return []
        indicators = _rows(
            connector.run(
                SEARCH_TOOL,
                {
                    "filter": f"contains(IndicatorName,'{_escaped(condition)}')",
                    "top": int(request.option("indicator_limit", str(MAX_INDICATORS))),
                },
            )
        )
        retrieved_at = datetime.now(timezone.utc)
        findings: list[Finding] = []
        for indicator in indicators[: int(request.option("indicator_limit", str(MAX_INDICATORS)))]:
            code = _text(indicator.get("IndicatorCode"))
            name = _text(indicator.get("IndicatorName"))
            if not code:
                continue
            records = _readings(
                connector,
                code,
                name,
                rows=int(request.option("row_limit", str(MAX_ROWS))),
            )
            if not records:
                # An indicator GHO names but holds no readings for. Skipped rather than
                # emitted as an empty finding, which would report a statistic that does
                # not exist for this condition.
                continue
            findings.append(
                Finding(
                    url=f"https://www.who.int/data/gho/data/indicators/indicator-details/GHO/{code}",
                    title=name or code,
                    query=request.query,
                    retrieved_at=retrieved_at,
                    # The readings are the finding. An excerpt would be a rendering of
                    # them, and a second rendering of a number is where a number changes.
                    excerpt=None,
                    source=self.spec.key,
                    # Structured readings, not a passage to reason over.
                    evidence_role="reference",
                    indicator_records=records,
                )
            )
        return findings


def _readings(
    connector: Any,
    code: str,
    name: str,
    *,
    rows: int,
) -> list[IndicatorRecord]:
    """One indicator's country-year readings, newest first."""
    try:
        payload = connector.run(
            DATA_TOOL,
            {"indicator_code": code, "top": rows, "orderby": "TimeDim desc"},
        )
    except Exception:  # noqa: BLE001 - one indicator failing is not a lane failure
        logger.warning("WHO GHO readings unavailable for %s", code)
        return []
    records: list[IndicatorRecord] = []
    for row in _rows(payload):
        spatial_type = _text(row.get("SpatialDimType")).upper()
        place = _text(row.get("SpatialDim"))
        year = row.get("TimeDim")
        if spatial_type not in {"COUNTRY", "REGION"} or not place:
            continue
        if not isinstance(year, int):
            continue
        numeric = row.get("NumericValue")
        value = float(numeric) if isinstance(numeric, (int, float)) else None
        value_text = _text(row.get("Value"))
        if value is None and not value_text:
            continue
        records.append(
            IndicatorRecord(
                indicator_code=code,
                indicator_name=name,
                place=place,
                spatial_type=spatial_type,
                year=year,
                value=value,
                value_text=value_text,
                parent_place=_text(row.get("ParentLocation")),
            )
        )
    return records


def _rows(payload: Any) -> list[dict[str, Any]]:
    """Unwrap the tool's envelope down to the OData `value` list.

    The tool wraps the provider's own response, which itself wraps the rows, so there are
    two layers rather than one.
    """
    if isinstance(payload, dict):
        if payload.get("status") == "error" or payload.get("error"):
            raise RuntimeError(str(payload.get("error") or "WHO GHO failed"))
        data = payload.get("data", payload)
        if isinstance(data, dict):
            data = data.get("value", [])
        payload = data
    if not isinstance(payload, list):
        raise RuntimeError("WHO GHO returned an unexpected result shape")
    return [row for row in payload if isinstance(row, dict)]


def _escaped(value: str) -> str:
    """Single quotes close an OData string literal, so they are doubled."""
    return value.replace("'", "''")


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str) else ""
