"""The evaluation harness's pure parts: manifest, signals, comparison and usage.

The harness itself is live and is not run here; these pin what it reports, so a
change to a result field the signals read fails before the next live run would.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from scripts.evaluate.measure import (
    TOOLS,
    ManifestError,
    Recorder,
    agreement,
    compare,
    load_manifest,
    missing_documents,
    render_markdown,
    select,
    signals,
)

MANIFEST = Path(__file__).resolve().parents[1] / "scripts" / "evaluate" / "cases.yaml"


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cases.yaml"
    path.write_text(text)
    return path


# --- manifest ---------------------------------------------------------------


def test_checked_in_manifest_covers_every_tool():
    cases = load_manifest(MANIFEST)
    assert {case.tool for case in cases} == set(TOOLS)
    aligner = next(case for case in cases if case.tool == "aligner")
    assert [role for role, _ in aligner.documents] == ["itpp", "ctpp", "ipdp"]
    assert all(path.startswith("RSV Vaccine/") for _, path in aligner.documents)
    screener = next(case for case in cases if case.tool == "screener")
    assert len(screener.documents) == 12 and screener.gate == "lcs"


def test_manifest_lists_every_problem(tmp_path):
    path = write(tmp_path, """
cases:
  - {name: a, tool: inspector, org: bmgf, intervention_class: vaccine, indication: x,
     documents: [one.docx, two.docx]}
  - {name: b, tool: aligner, org: bmgf, intervention_class: vaccine, indication: x,
     documents: [one.docx]}
  - {name: c, tool: screener, org: bmgf, intervention_class: drug, indication: x,
     documents: [a.pdf], typo: 1}
  - {name: d, tool: nope}
  - {name: e, tool: drafter, org: bmgf, intervention_class: vaccine, indication: x}
  - {name: e, tool: drafter, org: bmgf, intervention_class: vaccine, indication: x}
""")
    with pytest.raises(ManifestError) as raised:
        load_manifest(path)
    message = str(raised.value)
    assert "case a: missing source_type" in message
    assert "case a: documents must list exactly one filename" in message
    assert "case b: documents must map at least two document types" in message
    assert "case c: missing gate" in message and "case c: unknown key typo" in message
    assert "case d: tool must be one of" in message
    assert "case e: name is used 2 times" in message


def test_select_and_missing_documents(tmp_path):
    cases = load_manifest(MANIFEST)
    assert [case.name for case in select(cases, ["scout"])] == ["rsv-scout"]
    assert {case.tool for case in select(cases, ["rsv-drafter", "aligner"])} == {"drafter", "aligner"}
    assert select(cases, [""]) == cases
    with pytest.raises(ManifestError):
        select(cases, ["nothing"])
    (tmp_path / "RSV Vaccine").mkdir()
    (tmp_path / "RSV Vaccine" / "RSV Maternal Vaccine iTPP 13 May 2022.docx").write_bytes(b"")
    missing = missing_documents(select(cases, ["inspector", "aligner"]), tmp_path)
    assert missing == [
        "rsv-aligner: RSV Vaccine/INV096779_2025_cTPP_MaxvaxRSVMaternalVaccine.docx",
        "rsv-aligner: RSV Vaccine/INV096779__2025_IPDP_Vaccine_Maxvax.docx",
    ]


# --- signals ----------------------------------------------------------------


def inspector_result(verdicts: dict[str, str]) -> dict:
    units = [{"id": key, "verdict": verdict} for key, verdict in verdicts.items()]
    return {"inspection": {
        "assessment_status": "complete", "consistency_status": "complete",
        "consistency_failure_code": None, "document_findings": [{"id": "conflict|0"}],
        "rubric_resolutions": [{"rubric_id": "bmgf", "status": "included"}],
        "reviews": [{"rubric": {"id": "bmgf"}, "assessment_status": "complete",
                     "sections": [{"units": units}]}],
    }}


def screener_result(states: dict[str, tuple[str, str]]) -> dict:
    questions = [{"id": key, "state": state, "requirement": requirement}
                 for key, (state, requirement) in states.items()]
    return {"review": {"documents": [{"doc_id": "a"}],
                       "disciplines": [{"id": "pds", "questions": questions}]}}


def test_inspector_signals():
    found = signals("inspector", inspector_result(
        {"bmgf::A|": "specified", "bmgf::B|": "vague", "bmgf::C|": "specified"}))
    assert found["distributions"]["verdict.bmgf"] == {"specified": 2, "vague": 1}
    assert found["maps"]["verdict.bmgf"]["bmgf::B|"] == "vague"
    assert found["counts"] == {"units.bmgf": 3, "document_findings": 1}
    assert found["facts"]["consistency_status"] == "complete"
    assert "consistency_failure_code" not in found["facts"]


def test_screener_and_aligner_signals():
    found = signals("screener", screener_result({
        "Q1": ("answered", "required"), "Q2": ("not_found", "required"),
        "Q3": ("partly_answered", "anticipatory")}))
    assert found["distributions"]["required_state"] == {"answered": 1, "not_found": 1}
    assert found["maps"]["state"] == {"Q1": "answered", "Q2": "not_found", "Q3": "partly_answered"}
    aligner = {"alignment": {"edges": [{"edge_id": "e1"}, {"edge_id": "e2"}], "findings": [
        {"edge_id": "e1", "verdict": "meets"}, {"edge_id": "e1", "verdict": "falls_short"},
        {"edge_id": "e2", "verdict": "meets"}]}}
    found = signals("aligner", aligner)
    assert found["counts"] == {"requirements.e1": 2, "requirements.e2": 1}
    assert found["distributions"]["verdict.e1"] == {"falls_short": 1, "meets": 1}


def test_drafter_signals():
    def variable(name, status="complete", kind=None, failure=None, observations=()):
        return {"name": name, "status": status, "failure": failure and {"code": failure},
                "suggestion": kind and {"kind": kind, "leans_on": "guidance"},
                "observations": [{"basis": basis} for basis in observations],
                "unverified_quotes": 1, "unread_findings": 0}
    result = {"result": {"failed_sources": ["ctis"], "variables": [
        variable("a", kind="range", observations=["comparable_product", "published_guidance"]),
        variable("b", kind="insufficient"),
        variable("c", status="failed", failure="evidence_unavailable")]}}
    found = signals("drafter", result)
    assert found["maps"]["panel"] == {"a": "suggested", "b": "insufficient", "c": "failed"}
    assert found["distributions"]["failure_code"] == {"evidence_unavailable": 1}
    assert found["distributions"]["leans_on"] == {"guidance": 1}
    assert found["counts"]["observations"] == 2 and found["counts"]["unverified_quotes"] == 3


def test_scout_signals():
    result = {
        "phase": "final", "context_validation": {"status": "match"},
        "quantitative_ledger": {"status": "complete", "targets": [{"ai_recommendation": "confirm"}]},
        "variables": [{}, {}],
        "matches": [{"relation": "confirms", "failure_code": ""},
                    {"relation": "not_assessed", "failure_code": "model_error"}],
        "assessments": [{"attribute_ref": "f1", "strength": "partial", "failure_code": ""},
                        {"attribute_ref": "f2", "strength": "no_evidence", "failure_code": ""}],
        "precedents": [{"attribute_ref": "f1", "precedent": "direct", "outcome": "mixed", "failure_code": ""}],
        "conformity": [{"calibration_status": "insufficient",
                        "measurements": [{"evidence_mode": "prose", "ai_recommendation": "admit",
                                          "admission_status": "needs_review"}],
                        "excluded_measurements": [{"evidence_mode": "structured_fact",
                                                   "admission_status": "rejected"}]}],
        "reconciliations": [{"layer": "insights", "status": "reconciled", "merged": 3}],
        "search_plan": [{"lane": "pubmed", "status": "failed", "error_code": "timeout"},
                        {"lane": "web", "status": "complete"}],
        "development_landscape": [],
        "stats": {"queries": 2, "findings": 5, "unique_findings": 4, "insights": 2},
    }
    found = signals("scout", result)
    assert found["distributions"]["relation"] == {"confirms": 1, "not_assessed": 1}
    assert found["distributions"]["failure_code"] == {"relation:model_error": 1}
    assert found["distributions"]["search_failure"] == {"pubmed:timeout": 1}
    assert found["distributions"]["evidence_recommendation"] == {"admit": 1}
    assert found["distributions"]["admission_status"] == {"needs_review": 1, "rejected": 1}
    assert found["maps"]["precedent"] == {"f1": "direct/mixed"}
    counts = found["counts"]
    assert (counts["not_assessed"], counts["no_evidence"]) == (1, 1)
    assert (counts["measurements_admitted"], counts["measurements_excluded"]) == (1, 1)
    assert counts["reconciliation_merged"] == 3 and counts["unique_findings"] == 4


# --- usage from log lines -----------------------------------------------------


def test_recorder_attributes_calls_and_retries_to_the_running_stage():
    now = [100.0]
    recorder = Recorder(clock=lambda: now[0])
    log = logging.getLogger("test_evaluate.shared.ai")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.addHandler(recorder)

    def call(**fields):
        log.info("model_call %s", json.dumps({"schema_name": "s", "model": "m", **fields}))

    try:
        now[0] = 101.0
        assert recorder.progress("parse") is True
        assert recorder.progress("parse", completed=1, total=2) is False
        call(prompt_tokens=10, cached_tokens=4, completion_tokens=3, reasoning_tokens=1)
        now[0] = 104.0
        recorder.progress("assess")
        log.info("model_retry %s", json.dumps({"schema_name": "s", "attempt": 1, "reason": "bad id"}))
        call(prompt_tokens=20, completion_tokens=5, reasoning_tokens=None, attempt=2)
        call(error="APITimeoutError", elapsed_ms=10)
        log.info("unrelated line")
        now[0] = 110.0
        found = recorder.usage()
    finally:
        log.removeHandler(recorder)

    stages = {row["stage"]: row for row in found["stages"]}
    assert list(stages) == ["start", "parse", "assess"]
    assert stages["parse"]["seconds"] == 3.0 and stages["assess"]["seconds"] == 6.0
    assert stages["parse"]["prompt_tokens"] == 10 and stages["parse"]["cached_tokens"] == 4
    assert stages["assess"]["calls"] == 2 and stages["assess"]["errors"] == 1
    assert stages["assess"]["retries"] == 1 and stages["assess"]["reasoning_tokens"] == 0
    assert found["totals"]["seconds"] == 10.0 and found["totals"]["calls"] == 3
    assert found["retries"] == [{"stage": "assess", "schema_name": "s", "attempt": 1, "reason": "bad id"}]


# --- comparison ---------------------------------------------------------------


def entry(result: dict, tool: str, seconds: float, prompt: int) -> dict:
    return {"tool": tool, "status": "complete", "signals": signals(tool, result),
            "usage": {"totals": {"seconds": seconds, "calls": 2, "prompt_tokens": prompt},
                      "stages": [{"stage": "assess", "seconds": seconds, "calls": 2,
                                  "prompt_tokens": prompt}], "retries": []}}


def test_comparison_reports_agreement_deltas_and_usage():
    before = entry(screener_result({"Q1": ("answered", "required"), "Q2": ("not_found", "required"),
                                    "Q3": ("answered", "required")}), "screener", 100.0, 1000)
    now = entry(screener_result({"Q1": ("answered", "required"), "Q2": ("partly_answered", "required"),
                                 "Q4": ("answered", "required")}), "screener", 80.0, 1200)
    found = compare(now, before)
    state = found["agreement"]["state"]
    assert (state["compared"], state["same"], state["rate"]) == (2, 1, 0.5)
    assert state["transitions"] == {"not_found -> partly_answered": 1}
    assert (state["only_baseline"], state["only_current"]) == (1, 1)
    assert found["distributions"]["state"]["not_found"] == [1, 0]
    assert found["distributions"]["state"]["partly_answered"] == [0, 1]
    assert found["counts"]["questions"]["delta"] == 0
    assert found["usage"]["totals"]["seconds"]["delta"] == -20.0
    assert found["usage"]["stages"]["assess"]["prompt_tokens"]["delta"] == 200

    report = {"started_at": "t", "baseline": "b.json",
              "cases": {"gate": {**now, "comparison": found}}}
    markdown = render_markdown(report)
    assert "agreement state: 1/2 (50%): not_found -> partly_answered x1" in markdown
    assert "not_found 0 (-1)" in markdown and "partly_answered 1 (+1)" in markdown


def test_agreement_without_shared_keys_has_no_rate():
    assert agreement({}, {"a": "x"})["rate"] is None
