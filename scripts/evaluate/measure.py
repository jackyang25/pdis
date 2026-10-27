"""The harness's pure parts: the case manifest, the signals read from a result, the
comparison with a baseline report, usage read from model-call log lines, and the
markdown summary. Nothing here calls a model, reads a document, or imports a service.

Every signal is read from a result field, never from prose. Signals come in four
shapes so the comparison needs no tool-specific code:

- ``facts``: one label per name (a status), compared for equality;
- ``counts``: one integer per name, compared by difference;
- ``distributions``: label counts per name, compared label by label;
- ``maps``: a label per stable key (a rubric unit, a gate question, a field),
  compared by agreement over the keys both runs hold.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

TOOLS = ("inspector", "aligner", "screener", "scout", "drafter")
TOKEN_FIELDS = ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")

_COMMON = {"name", "tool", "org", "intervention_class", "indication"}
# Keys each tool requires and allows beyond the common ones. `documents` is a list of
# filenames, except Aligner's, which maps each document type to its filename.
_REQUIRED = {
    "inspector": {"source_type", "documents"},
    "aligner": {"documents"},
    "screener": {"gate", "documents"},
    "scout": {"source_type", "documents"},
    "drafter": set(),
}
_OPTIONAL = {
    "inspector": {"folder", "applicability_facts"},
    "aligner": {"folder"},
    "screener": {"folder"},
    "scout": {"folder", "published_since"},
    "drafter": {"intended_use"},
}


class ManifestError(ValueError):
    """The case manifest is malformed; every problem is listed in the message."""


@dataclass(frozen=True)
class Case:
    name: str
    tool: str
    org: str
    intervention_class: str
    indication: str
    source_type: str = ""
    gate: str = ""
    published_since: str = ""
    intended_use: str = ""
    applicability_facts: dict[str, str] = field(default_factory=dict)
    # (document type, path relative to the documents directory). The type is set
    # only for Aligner, where it says which declared comparisons the file joins.
    documents: tuple[tuple[str, str], ...] = ()

    def context(self) -> dict[str, Any]:
        keys = ("org", "intervention_class", "indication", "source_type", "gate",
                "published_since", "intended_use", "applicability_facts")
        return {key: getattr(self, key) for key in keys if getattr(self, key)}


def load_manifest(path: Path) -> list[Case]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    entries = raw.get("cases") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ManifestError(f"{path}: expected a non-empty `cases` list")
    problems: list[str] = []
    cases: list[Case] = []
    for index, entry in enumerate(entries):
        label = entry.get("name", f"#{index + 1}") if isinstance(entry, dict) else f"#{index + 1}"
        found = _case_problems(entry)
        problems.extend(f"case {label}: {problem}" for problem in found)
        if not found:
            cases.append(_case(entry))
    names = Counter(case.name for case in cases)
    problems.extend(f"case {name}: name is used {n} times" for name, n in names.items() if n > 1)
    if problems:
        raise ManifestError(f"{path}:\n  " + "\n  ".join(problems))
    return cases


def _case_problems(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return ["must be a mapping"]
    tool = entry.get("tool")
    if tool not in TOOLS:
        return [f"tool must be one of {', '.join(TOOLS)}"]
    required = _COMMON | _REQUIRED[tool]
    problems = [f"missing {key}" for key in sorted(required - set(entry))]
    problems += [f"unknown key {key}" for key in sorted(set(entry) - required - _OPTIONAL[tool])]
    for key in sorted(set(entry) & (required | _OPTIONAL[tool]) - {"documents", "applicability_facts"}):
        if not isinstance(entry[key], str) or not entry[key].strip():
            problems.append(f"{key} must be non-empty text")
    documents = entry.get("documents")
    if tool == "aligner" and "documents" in entry:
        if not (isinstance(documents, dict) and len(documents) >= 2
                and all(isinstance(value, str) and value for value in documents.values())):
            problems.append("documents must map at least two document types to filenames")
    elif tool == "inspector" and "documents" in entry:
        if not (isinstance(documents, list) and len(documents) == 1):
            problems.append("documents must list exactly one filename")
    elif "documents" in entry:
        if not (isinstance(documents, list) and documents
                and all(isinstance(value, str) and value for value in documents)):
            problems.append("documents must list at least one filename")
    facts = entry.get("applicability_facts", {})
    if not (isinstance(facts, dict) and all(isinstance(v, str) for v in facts.values())):
        problems.append("applicability_facts must map fact keys to text")
    return problems


def _case(entry: dict) -> Case:
    folder = entry.get("folder", "")
    documents = entry.get("documents") or []
    pairs = documents.items() if isinstance(documents, dict) else (("", name) for name in documents)
    return Case(
        name=entry["name"], tool=entry["tool"], org=entry["org"],
        intervention_class=entry["intervention_class"], indication=entry["indication"],
        source_type=entry.get("source_type", ""), gate=entry.get("gate", ""),
        published_since=entry.get("published_since", ""),
        intended_use=entry.get("intended_use", ""),
        applicability_facts=dict(entry.get("applicability_facts") or {}),
        documents=tuple((role, str(Path(folder) / name)) for role, name in pairs),
    )


def select(cases: list[Case], only: Iterable[str]) -> list[Case]:
    """Cases named by `only`, which may hold case names or tool names."""
    wanted = {item.strip() for item in only if item.strip()}
    if not wanted:
        return cases
    known = {case.name for case in cases} | set(TOOLS)
    if unknown := sorted(wanted - known):
        raise ManifestError(f"--only names no case or tool: {', '.join(unknown)}")
    return [case for case in cases if case.name in wanted or case.tool in wanted]


def missing_documents(cases: list[Case], root: Path) -> list[str]:
    return [f"{case.name}: {relative}" for case in cases for _, relative in case.documents
            if not (Path(root) / relative).is_file()]


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def signals(tool: str, result: dict) -> dict:
    """The quality signals one published result carries, in the four shapes above."""
    facts, counts, distributions, maps = {}, {}, {}, {}
    _READERS[tool](result, facts, counts, distributions, maps)
    return {
        "facts": facts, "counts": counts,
        "distributions": {name: dict(sorted(values.items())) for name, values in distributions.items()},
        "maps": maps,
    }


def _inspector(result, facts, counts, distributions, maps):
    inspection = result["inspection"]
    facts["assessment_status"] = inspection.get("assessment_status") or ""
    facts["consistency_status"] = inspection.get("consistency_status") or ""
    if inspection.get("consistency_failure_code"):
        facts["consistency_failure_code"] = inspection["consistency_failure_code"]
    distributions["rubric_resolution"] = Counter(
        f"{item['rubric_id']}:{item['status']}" for item in inspection.get("rubric_resolutions", []))
    for review in inspection["reviews"]:
        rubric = review["rubric"]["id"]
        units = [unit for section in review["sections"] for unit in section["units"]]
        facts[f"assessment_status.{rubric}"] = review.get("assessment_status") or ""
        distributions[f"verdict.{rubric}"] = Counter(unit["verdict"] for unit in units)
        maps[f"verdict.{rubric}"] = {unit["id"]: unit["verdict"] for unit in units}
        counts[f"units.{rubric}"] = len(units)
    counts["document_findings"] = len(inspection.get("document_findings") or [])


def _aligner(result, facts, counts, distributions, maps):
    alignment = result["alignment"]
    for edge in alignment["edges"]:
        findings = [item for item in alignment["findings"] if item["edge_id"] == edge["edge_id"]]
        counts[f"requirements.{edge['edge_id']}"] = len(findings)
        distributions[f"verdict.{edge['edge_id']}"] = Counter(item["verdict"] for item in findings)


def _screener(result, facts, counts, distributions, maps):
    review = result["review"]
    questions = [question for discipline in review["disciplines"] for question in discipline["questions"]]
    counts["questions"] = len(questions)
    counts["documents"] = len(review.get("documents") or [])
    distributions["state"] = Counter(question["state"] for question in questions)
    distributions["required_state"] = Counter(
        question["state"] for question in questions if question.get("requirement") == "required")
    maps["state"] = {question["id"]: question["state"] for question in questions}


def drafter_panel(variable: dict) -> str:
    if variable["status"] == "failed":
        return "failed"
    suggestion = variable.get("suggestion") or {}
    return "insufficient" if suggestion.get("kind") == "insufficient" else "suggested"


def _drafter(result, facts, counts, distributions, maps):
    draft = result["result"]
    variables = draft["variables"]
    distributions["panel"] = Counter(drafter_panel(item) for item in variables)
    distributions["failure_code"] = Counter(item["failure"]["code"] for item in variables if item.get("failure"))
    distributions["leans_on"] = Counter(
        item["suggestion"]["leans_on"] for item in variables if drafter_panel(item) == "suggested")
    distributions["observation_basis"] = Counter(
        observation["basis"] for item in variables for observation in item["observations"])
    maps["panel"] = {item["name"]: drafter_panel(item) for item in variables}
    counts["variables"] = len(variables)
    counts["observations"] = sum(len(item["observations"]) for item in variables)
    counts["unverified_quotes"] = sum(item.get("unverified_quotes", 0) for item in variables)
    counts["unread_findings"] = sum(item.get("unread_findings", 0) for item in variables)
    counts["failed_sources"] = len(draft.get("failed_sources") or [])


def _scout(result, facts, counts, distributions, maps):
    matches, assessments, precedents = result["matches"], result["assessments"], result["precedents"]
    conformity, ledger = result["conformity"], result["quantitative_ledger"]
    measurements = [item for target in conformity for item in target["measurements"]]
    excluded = [item for target in conformity for item in target["excluded_measurements"]]
    facts["phase"] = result["phase"]
    facts["context_validation"] = result["context_validation"]["status"]
    facts["quantitative_ledger"] = ledger["status"]
    distributions["grounding"] = Counter(item["strength"] for item in assessments)
    distributions["relation"] = Counter(item["relation"] for item in matches)
    distributions["precedent"] = Counter(item["precedent"] for item in precedents)
    distributions["precedent_outcome"] = Counter(item["outcome"] for item in precedents)
    distributions["failure_code"] = Counter(
        f"{kind}:{item['failure_code']}"
        for kind, items in (("relation", matches), ("grounding", assessments), ("precedent", precedents))
        for item in items if item.get("failure_code"))
    distributions["target_recommendation"] = Counter(item["ai_recommendation"] for item in ledger["targets"])
    distributions["calibration_status"] = Counter(item["calibration_status"] for item in conformity)
    # At the evidence-review checkpoint every prose measurement awaits admission, which
    # the browser settles; this says how far the published result got.
    distributions["admission_status"] = Counter(
        item.get("admission_status", "") for item in (*measurements, *excluded))
    distributions["evidence_recommendation"] = Counter(
        item["ai_recommendation"] for item in (*measurements, *excluded) if item.get("evidence_mode") == "prose")
    distributions["reconciliation"] = Counter(
        f"{item['layer']}:{item['status']}" for item in result.get("reconciliations", []))
    distributions["search_failure"] = Counter(
        f"{trace['lane']}:{trace.get('error_code') or 'unknown'}"
        for trace in result["search_plan"] if trace["status"] == "failed")
    maps["grounding"] = {item["attribute_ref"]: item["strength"] for item in assessments}
    maps["precedent"] = {item["attribute_ref"]: f"{item['precedent']}/{item['outcome']}" for item in precedents}
    stats = result["stats"]
    counts.update({
        "variables": len(result["variables"]),
        "targets": len(ledger["targets"]),
        "queries": stats["queries"],
        "findings": stats["findings"],
        "unique_findings": stats["unique_findings"],
        "insights": stats["insights"],
        "search_traces": len(result["search_plan"]),
        "not_assessed": sum(item["relation"] == "not_assessed" for item in matches)
        + sum(item["strength"] == "not_assessed" for item in assessments)
        + sum(item["precedent"] == "not_assessed" for item in precedents),
        "no_evidence": sum(item["strength"] == "no_evidence" for item in assessments)
        + sum(item["precedent"] == "no_evidence" for item in precedents),
        "conformity_targets": len(conformity),
        "measurements_admitted": len(measurements),
        "measurements_excluded": len(excluded),
        "reconciliation_merged": sum(item.get("merged", 0) for item in result.get("reconciliations", [])),
        "development_landscape": len(result["development_landscape"]),
    })


_READERS: dict[str, Callable] = {
    "inspector": _inspector, "aligner": _aligner, "screener": _screener,
    "scout": _scout, "drafter": _drafter,
}


# ---------------------------------------------------------------------------
# Usage from model-call log lines
# ---------------------------------------------------------------------------


class Recorder(logging.Handler):
    """Attributes each `model_call` and `model_retry` log line to the running stage.

    The stage is the last one the pipeline announced through its progress callback.
    Pipelines run their stages in sequence, so a call belongs to the stage in force
    when its line is written. One recorder serves one case at a time.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        super().__init__(level=logging.INFO)
        self._clock = clock
        self._lock = threading.Lock()
        self.stage = "start"
        self.marks: list[tuple[float, str]] = [(clock(), "start")]
        self.calls: list[dict] = []
        self.retries: list[dict] = []

    def progress(self, stage: str, completed: int | None = None, total: int | None = None) -> bool:
        """Record a stage announcement; True when it starts a new stage."""
        with self._lock:
            if stage == self.stage:
                return False
            self.stage = stage
            self.marks.append((self._clock(), stage))
            return True

    def emit(self, record: logging.LogRecord) -> None:
        tag, _, payload = record.getMessage().partition(" ")
        if tag not in ("model_call", "model_retry"):
            return
        try:
            fields = json.loads(payload)
        except ValueError:
            return
        fields["stage"] = self.stage
        (self.calls if tag == "model_call" else self.retries).append(fields)

    def usage(self) -> dict:
        return usage(self.marks, self._clock(), self.calls, self.retries)


def usage(marks: list[tuple[float, str]], end: float, calls: list[dict], retries: list[dict]) -> dict:
    """Per-stage wall time, calls and tokens, in the order stages first ran."""
    stages: dict[str, dict] = {}
    for (started, stage), (finished, _) in zip(marks, [*marks[1:], (end, "")]):
        entry = stages.setdefault(stage, {"stage": stage, "seconds": 0.0, **_zero()})
        entry["seconds"] += finished - started
    for call in calls:
        entry = stages.setdefault(call["stage"], {"stage": call["stage"], "seconds": 0.0, **_zero()})
        entry["calls"] += 1
        entry["errors"] += bool(call.get("error"))
        entry["truncated"] += call.get("finish_reason") in ("length", "max_tokens")
        for name in TOKEN_FIELDS:
            entry[name] += call.get(name) or 0
        if call.get("model") and call["model"] not in entry["models"]:
            entry["models"].append(call["model"])
    for retry in retries:
        stages.setdefault(retry["stage"], {"stage": retry["stage"], "seconds": 0.0, **_zero()})["retries"] += 1
    rows = list(stages.values())
    for entry in rows:
        entry["seconds"] = round(entry["seconds"], 1)
    totals = {"seconds": round(end - marks[0][0], 1)}
    for name in ("calls", "errors", "truncated", "retries", *TOKEN_FIELDS):
        totals[name] = sum(entry[name] for entry in rows)
    return {
        "stages": rows, "totals": totals,
        "retries": [{key: retry.get(key) for key in ("stage", "schema_name", "attempt", "reason")}
                    for retry in retries],
    }


def _zero() -> dict:
    return {"calls": 0, "errors": 0, "truncated": 0, "retries": 0,
            **{name: 0 for name in TOKEN_FIELDS}, "models": []}


# ---------------------------------------------------------------------------
# Comparison with a baseline report
# ---------------------------------------------------------------------------


def compare(current: dict, baseline: dict) -> dict:
    """How one case's entry differs from the same case in a baseline report."""
    now, before = current.get("signals") or {}, baseline.get("signals") or {}
    comparison: dict[str, Any] = {"status": [baseline.get("status"), current.get("status")]}
    facts_now, facts_before = now.get("facts", {}), before.get("facts", {})
    comparison["facts_changed"] = {
        name: [facts_before.get(name), facts_now.get(name)]
        for name in sorted(set(facts_now) | set(facts_before))
        if facts_now.get(name) != facts_before.get(name)}
    counts_now, counts_before = now.get("counts", {}), before.get("counts", {})
    comparison["counts"] = {
        name: _pair(counts_before.get(name), counts_now.get(name))
        for name in sorted(set(counts_now) | set(counts_before))}
    dist_now, dist_before = now.get("distributions", {}), before.get("distributions", {})
    comparison["distributions"] = {
        name: {label: [dist_before.get(name, {}).get(label, 0), dist_now.get(name, {}).get(label, 0)]
               for label in sorted(set(dist_before.get(name, {})) | set(dist_now.get(name, {})))}
        for name in sorted(set(dist_now) | set(dist_before))}
    maps_now, maps_before = now.get("maps", {}), before.get("maps", {})
    comparison["agreement"] = {
        name: agreement(maps_before.get(name, {}), maps_now.get(name, {}))
        for name in sorted(set(maps_now) | set(maps_before))}
    comparison["usage"] = _usage_delta(current.get("usage") or {}, baseline.get("usage") or {})
    return comparison


def agreement(before: dict[str, str], now: dict[str, str]) -> dict:
    shared = [key for key in before if key in now]
    same = sum(before[key] == now[key] for key in shared)
    transitions = Counter(f"{before[key]} -> {now[key]}" for key in shared if before[key] != now[key])
    return {
        "compared": len(shared), "same": same,
        "rate": round(same / len(shared), 3) if shared else None,
        "transitions": dict(transitions.most_common()),
        "only_baseline": len(set(before) - set(now)), "only_current": len(set(now) - set(before)),
    }


def _pair(before, now) -> dict:
    delta = now - before if isinstance(now, (int, float)) and isinstance(before, (int, float)) else None
    return {"baseline": before, "current": now, "delta": round(delta, 1) if delta is not None else None}


_DELTA_FIELDS = ("seconds", "calls", "retries", *TOKEN_FIELDS)


def _usage_delta(now: dict, before: dict) -> dict:
    stages_now = {row["stage"]: row for row in now.get("stages", [])}
    stages_before = {row["stage"]: row for row in before.get("stages", [])}
    order = [*stages_before, *(stage for stage in stages_now if stage not in stages_before)]
    return {
        "totals": {name: _pair(before.get("totals", {}).get(name), now.get("totals", {}).get(name))
                   for name in _DELTA_FIELDS},
        "stages": {stage: {name: _pair(stages_before.get(stage, {}).get(name),
                                       stages_now.get(stage, {}).get(name))
                           for name in _DELTA_FIELDS}
                   for stage in order},
    }


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def render_markdown(report: dict) -> str:
    lines = [f"# PDIS evaluation {report['started_at']}", ""]
    if report.get("label"):
        lines += [f"Label: {report['label']}", ""]
    lines += [f"Baseline: {report.get('baseline') or 'none'}", "",
              "| Case | Tool | Status | Seconds | Calls | Prompt (cached) | Completion (reasoning) | Retries |",
              "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, case in report["cases"].items():
        totals = (case.get("usage") or {}).get("totals", {})
        delta = (case.get("comparison") or {}).get("usage", {}).get("totals", {})
        lines.append(
            f"| {name} | {case['tool']} | {case['status']} | {_cell(totals, delta, 'seconds')} "
            f"| {_cell(totals, delta, 'calls')} "
            f"| {_cell(totals, delta, 'prompt_tokens')} ({totals.get('cached_tokens', 0):,}) "
            f"| {_cell(totals, delta, 'completion_tokens')} ({totals.get('reasoning_tokens', 0):,}) "
            f"| {_cell(totals, delta, 'retries')} |")
    for name, case in report["cases"].items():
        lines += ["", f"## {name}", ""]
        if case["status"] != "complete":
            lines.append(f"Failed during `{case.get('failed_stage')}`: {case.get('error')}")
        comparison = case.get("comparison") or {}
        signal = case.get("signals") or {}
        for fact, value in signal.get("facts", {}).items():
            changed = comparison.get("facts_changed", {}).get(fact)
            lines.append(f"- {fact}: {value}" + (f" (baseline {changed[0]})" if changed else ""))
        for dist, values in signal.get("distributions", {}).items():
            before = {label: pair[0] for label, pair in comparison.get("distributions", {}).get(dist, {}).items()}
            text = ", ".join(f"{label} {count}{_delta(before, label, count)}" for label, count in values.items())
            gone = [label for label in before if label not in values and before[label]]
            text += "".join(f", {label} 0 ({-before[label]:+d})" for label in gone)
            lines.append(f"- {dist}: {text or 'none'}")
        if counts := signal.get("counts"):
            deltas = comparison.get("counts", {})
            lines.append("- counts: " + ", ".join(
                f"{key} {value}" + (f" ({deltas[key]['delta']:+g})" if deltas.get(key, {}).get("delta") else "")
                for key, value in counts.items()))
        for map_name, result in comparison.get("agreement", {}).items():
            if result["rate"] is None:
                continue
            moved = "; ".join(f"{k} x{v}" for k, v in list(result["transitions"].items())[:6])
            lines.append(f"- agreement {map_name}: {result['same']}/{result['compared']} "
                         f"({result['rate']:.0%})" + (f": {moved}" if moved else ""))
        stages = (case.get("usage") or {}).get("stages", [])
        stage_delta = comparison.get("usage", {}).get("stages", {})
        if stages:
            lines.append("- stages: " + "; ".join(
                f"{row['stage']} {row['seconds']:g}s"
                + _signed(stage_delta.get(row["stage"], {}).get("seconds", {}).get("delta"), "s")
                + (f" {row['calls']} call{'s' * (row['calls'] != 1)}" if row["calls"] else "")
                for row in stages))
        reasons = Counter(f"{row['stage']}/{row['schema_name']}" for row in (case.get("usage") or {}).get("retries", []))
        if reasons:
            lines.append("- retries: " + ", ".join(f"{key} x{n}" for key, n in reasons.most_common()))
    return "\n".join(lines) + "\n"


def _cell(totals: dict, delta: dict, name: str) -> str:
    value = totals.get(name)
    if value is None:
        return ""
    text = f"{value:,.0f}" if name != "seconds" else f"{value:g}"
    return text + _signed((delta.get(name) or {}).get("delta"))


def _signed(value, unit: str = "") -> str:
    return f" ({value:+,.0f}{unit})" if value else ""


def _delta(before: dict, label: str, count: int) -> str:
    # `before` holds every label of both runs when there is a baseline, else nothing.
    if label not in before or before[label] == count:
        return ""
    return f" ({count - before[label]:+d})"
