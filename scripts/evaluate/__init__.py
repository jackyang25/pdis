"""Evaluation harness: re-run fixed real cases and report what changed.

Each case in ``cases.yaml`` names a tool, its product context and its documents. The
harness runs every case through the tool's own pipeline, composed as its API route
composes it, and writes into ``--out``:

- ``<case>.json``: the full published result, for a later diff;
- ``report.json``: per case, the quality signals read from result fields, wall time
  and tokens per pipeline stage from the ``model_call``/``model_retry`` log lines,
  and, with ``--baseline``, the comparison with that earlier ``report.json``;
- ``summary.md``: the same, short, also printed.

Live and costly: it calls the configured providers. Run it inside the ``pdis-diag``
image, which has LibreOffice; CONTRIBUTING.md has the command. Modules:
``measure`` holds the pure parts (manifest, signals, comparison, usage, markdown),
``runners`` the live invocation, ``__main__`` the command line.
"""
