"""python -m scripts.evaluate --documents DIR --out DIR [--baseline REPORT] [--only a,b]"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .measure import (
    Case, ManifestError, Recorder, compare, load_manifest, missing_documents,
    render_markdown, select, signals,
)

MANIFEST = Path(__file__).with_name("cases.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.evaluate", description=__doc__)
    parser.add_argument("--documents", type=Path, required=True, help="root the manifest's filenames are relative to")
    parser.add_argument("--out", type=Path, required=True, help="new directory for this run's report and results")
    parser.add_argument("--baseline", type=Path, help="report.json of an earlier run to compare with")
    parser.add_argument("--only", default="", help="comma-separated case or tool names")
    parser.add_argument("--cases", type=Path, default=MANIFEST, help="case manifest (default: cases.yaml)")
    parser.add_argument("--label", default="", help="free text stored on the report, e.g. the change under test")
    args = parser.parse_args(argv)

    try:
        cases = select(load_manifest(args.cases), args.only.split(","))
    except ManifestError as exc:
        parser.error(str(exc))
    if missing := missing_documents(cases, args.documents):
        parser.error("documents not found under --documents:\n  " + "\n  ".join(missing))
    report_path = args.out / "report.json"
    if report_path.exists():
        parser.error(f"{report_path} exists; give each run its own --out so a baseline is never overwritten")
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    args.out.mkdir(parents=True, exist_ok=True)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    logging.basicConfig(level=logging.WARNING, handlers=[console], format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("shared.ai").setLevel(logging.INFO)

    report = {
        "harness_version": 1, "label": args.label,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest": str(args.cases), "baseline": str(args.baseline) if args.baseline else None,
        "cases": {},
    }
    for case in cases:
        entry = evaluate(case, args.documents, args.out)
        before = (baseline or {}).get("cases", {}).get(case.name)
        if before:
            entry["comparison"] = compare(entry, before)
        report["cases"][case.name] = entry
        # Written after every case, so a run stopped midway keeps what it finished.
        report_path.write_text(json.dumps(report, indent=2))
    summary = render_markdown(report)
    (args.out / "summary.md").write_text(summary)
    print(summary)
    return 0 if all(entry["status"] == "complete" for entry in report["cases"].values()) else 1


def evaluate(case: Case, documents: Path, out: Path) -> dict:
    from .runners import run_case

    recorder = Recorder()
    model_log = logging.getLogger("shared.ai")
    model_log.addHandler(recorder)

    def progress(stage: str, completed: int | None = None, total: int | None = None) -> None:
        if recorder.progress(stage, completed, total):
            print(f"[{time.strftime('%H:%M:%S')}] {case.name}: {stage}", file=sys.stderr, flush=True)

    entry: dict = {"tool": case.tool, "context": case.context(),
                   "documents": [relative for _, relative in case.documents]}
    print(f"[{time.strftime('%H:%M:%S')}] {case.name}: start", file=sys.stderr, flush=True)
    try:
        result = run_case(case, documents, progress)
        result_file = out / f"{case.name}.json"
        result_file.write_text(json.dumps(result, default=str))
        entry.update(status="complete", result_file=result_file.name, signals=signals(case.tool, result))
    except Exception as exc:  # noqa: BLE001 - one failed case must not stop the others
        traceback.print_exc()
        entry.update(status="failed", failed_stage=recorder.stage, error=f"{type(exc).__name__}: {exc}"[:2000])
    finally:
        model_log.removeHandler(recorder)
    entry["usage"] = recorder.usage()
    return entry


if __name__ == "__main__":
    sys.exit(main())
