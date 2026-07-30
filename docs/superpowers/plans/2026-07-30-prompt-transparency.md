# Prompt transparency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the instructions each Scout model stage sends, in the docs, without changing any prompt a provider receives.

**Architecture:** Standardize how stages expose their system prompt, declare every prompt in one catalog, generate `shared/prompt_reference.json` from that catalog, and render it on the documentation page as collapsed entries fetched on demand. Prompt text stays authored in Python; the artifact is a derived view guarded by a regeneration test.

**Tech Stack:** Python 3.11 (stdlib `unittest`, `ast`, `json`), Next.js 14 app router, Tailwind 3.4.

## Global Constraints

- No prompt wording changes. `SHARED PRIMITIVE` is not normalized to `SHARED PRIMITIVES`; grounding and precedent gain no shared primitive; no section is reordered or reworded.
- No result envelope, API schema, or review contract changes.
- No runtime endpoint. The artifact is generated at build time and committed.
- Authored prompt text stays in Python. The catalog references builders; it never holds copies.
- Imports flow `web/ → api/ → services/ → shared/`. The catalog lives inside `services/scout/` and may import that service's stages.
- `intent_builder.py` is deterministic and has no prompt.
- Standardize builder **names only**. Six prompts require domain objects (`Attribute`, `QuantitativeTarget`, `ScoutTypeConfig`) because their text interpolates the field under evaluation; their signatures stay as they are.
- The catalog owns rendering. Each entry exposes `render() -> str`, closing over placeholder domain objects whose fields are visible slots (`{field_name}`, `{value} {unit}`). Snapshot test, generator, and docs all read the same rendering, so there is one convention and no second accessor map.

## Prompt inventory

Fourteen prompts already have a dedicated builder:

| Stage | Builder(s) |
| --- | --- |
| `context_validator` | `_system_prompt` |
| `drift_classifier` | `_system_prompt` |
| `evidence_assessor` | `_system_prompt` |
| `insight_extractor` | `_system_prompt` |
| `precedent_classifier` | `_system_prompt` |
| `projection_classifier` | `_system_prompt` |
| `unit_extractor` | `_system_prompt` |
| `conformity` | `_document_ledger_system_prompt`, `_measurement_system_prompt` |
| `query_extractor` | `_system_prompt_for_variable`, `_system_prompt_for_geographic_variable`, `_system_prompt_for_counterfactual_variable`, `_system_prompt_for_precedent_variable` |
| `target_resolver` | `_ledger_system_prompt` |

Three are assembled inline inside a public stage function and must be extracted:

| Stage | Function | Prompt starts |
| --- | --- | --- |
| `conformity` | `reconcile_quantitative_document_ledger` | line 1366 |
| `evidence_reviewer` | `prefill_evidence_review` | line 59 |
| `target_reviewer` | `prefill_target_review` | line 44 |

---

### Task 1: Golden snapshot of every prompt that has a builder

Captures today's output before anything moves. Fourteen prompts are callable
directly, so this needs no fixtures.

**Files:**
- Create: `tests/test_scout_prompt_snapshot.py`
- Create: `tests/data/prompt_snapshot.json`

**Interfaces:**
- Produces: `tests/data/prompt_snapshot.json`, a mapping of prompt id to text, consumed by Task 3 and Task 5.

- [ ] **Step 1: Write the snapshot writer as a test that fails when the file is absent**

```python
import json
import unittest
from pathlib import Path

SNAPSHOT = Path(__file__).parent / "data" / "prompt_snapshot.json"

CONTEXT = {
    "indication": "{indication}",
    "intervention_class": "{intervention_class}",
    "source_type": "itpp",
    "framing": "",
}


def _rendered() -> dict[str, str]:
    """Render every prompt that exposes a builder, with placeholder context."""
    from services.scout.stages import (
        context_validator,
        conformity,
        drift_classifier,
        evidence_assessor,
        insight_extractor,
        precedent_classifier,
        projection_classifier,
        query_extractor,
        target_resolver,
        unit_extractor,
    )

    return {
        "context_validator.validate": context_validator._system_prompt(
            CONTEXT["indication"]
        ),
        "drift_classifier.classify": drift_classifier._system_prompt(
            indication=CONTEXT["indication"],
            intervention_class=CONTEXT["intervention_class"],
        ),
        "conformity.document_ledger": conformity._document_ledger_system_prompt(
            indication=CONTEXT["indication"],
            intervention_class=CONTEXT["intervention_class"],
        ),
        "conformity.measurement": conformity._measurement_system_prompt(
            indication=CONTEXT["indication"],
            intervention_class=CONTEXT["intervention_class"],
        ),
        "target_resolver.ledger": target_resolver._ledger_system_prompt(
            intervention_class=CONTEXT["intervention_class"],
            source_type=CONTEXT["source_type"],
            indication=CONTEXT["indication"],
        ),
        # Remaining builders are added in Step 2 once their exact signatures
        # are read from source; every entry uses only CONTEXT values.
    }


class PromptSnapshotTest(unittest.TestCase):
    def test_prompts_match_snapshot(self) -> None:
        self.assertTrue(
            SNAPSHOT.exists(),
            "run scripts/write_prompt_snapshot.py to record the baseline",
        )
        expected = json.loads(SNAPSHOT.read_text())
        self.assertEqual(_rendered(), expected)
```

- [ ] **Step 2: Read each remaining builder's signature and add its entry**

For each of `evidence_assessor`, `insight_extractor`, `precedent_classifier`,
`projection_classifier`, `unit_extractor`, and the four `query_extractor`
builders, run `grep -n "^def _.*prompt" -A 6 <file>` and add one entry to
`_rendered()` passing only `CONTEXT` values. Do not guess a signature.

- [ ] **Step 3: Record the baseline**

```bash
.venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, ".")
from tests.test_scout_prompt_snapshot import _rendered, SNAPSHOT
SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
SNAPSHOT.write_text(json.dumps(_rendered(), indent=2, sort_keys=True) + "\n")
print(f"recorded {len(_rendered())} prompts")
PY
```

Expected: `recorded 14 prompts`.

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_snapshot -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_scout_prompt_snapshot.py tests/data/prompt_snapshot.json
git commit -m "test: snapshot Scout stage prompts before standardization"
```

---

### Task 2: Extract the three inline prompts

The only step that can change a prompt by accident, so it is verified
structurally as well as by review.

**Files:**
- Modify: `services/scout/stages/conformity.py` (extract from `reconcile_quantitative_document_ledger`, near line 1366)
- Modify: `services/scout/stages/evidence_reviewer.py` (extract from `prefill_evidence_review`, near line 59)
- Modify: `services/scout/stages/target_reviewer.py` (extract from `prefill_target_review`, near line 44)
- Create: `tests/test_scout_prompt_extraction.py`

**Interfaces:**
- Produces: `conformity.reconciliation_system_prompt`, `evidence_reviewer.review_system_prompt`, `target_reviewer.review_system_prompt`, each keyword-only, each returning the string the enclosing function previously built inline.

- [ ] **Step 1: Write the literal-sequence test against the pre-extraction source**

This compares the string literals the new builder returns with the literals
recorded from the original function body, using `ast` so no fixture or provider
call is needed.

```python
import ast
import subprocess
import unittest


def _literals(source: str, function: str) -> list[str]:
    """Every string literal inside one function, in source order."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function:
            return [
                child.value
                for child in ast.walk(node)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            ]
    raise AssertionError(f"{function} not found")


def _source_at_head(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"HEAD:{path}"], capture_output=True, text=True, check=True
    ).stdout


class PromptExtractionTest(unittest.TestCase):
    def test_reconciliation_prompt_literals_are_unchanged(self) -> None:
        path = "services/scout/stages/conformity.py"
        before = _literals(
            _source_at_head(path), "reconcile_quantitative_document_ledger"
        )
        after = _literals(
            open(path).read(), "reconciliation_system_prompt"
        ) + _literals(open(path).read(), "reconcile_quantitative_document_ledger")
        prompt_literals = [item for item in before if item.startswith("ROLE\n")]
        self.assertTrue(prompt_literals, "no prompt literal found at HEAD")
        for literal in before:
            self.assertIn(literal, after, f"literal lost during extraction: {literal!r}")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_extraction -v`
Expected: FAIL with "reconciliation_system_prompt not found".

- [ ] **Step 3: Extract, one file at a time**

For each of the three functions: cut the prompt expression verbatim, paste it
into a new module-level function, and call that function from the original site.
Change nothing inside the expression — not whitespace, not concatenation, not
an f-string boundary. Example shape:

```python
def reconciliation_system_prompt(*, indication: str, intervention_class: str) -> str:
    return (
        "ROLE\n"
        ...
    )
```

- [ ] **Step 4: Run both prompt tests**

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_extraction tests.test_scout_prompt_snapshot -v`
Expected: PASS.

- [ ] **Step 5: Read the diff and confirm it is a pure move**

Run: `git diff -- services/scout/stages/`
Expected: only indentation-preserving moves plus the new call sites.

- [ ] **Step 6: Commit**

```bash
git add services/scout/stages/ tests/test_scout_prompt_extraction.py
git commit -m "refactor: give three inline Scout prompts a builder"
```

---

### Task 3: Standardize builder names and signatures

**Files:**
- Modify: all ten stage files listed in the inventory
- Modify: `tests/test_scout_prompt_snapshot.py` (update accessor names)

**Interfaces:**
- Produces: one public builder per prompt. Single-prompt stages expose `system_prompt`; multi-prompt stages expose `document_ledger_system_prompt`, `measurement_system_prompt`, `reconciliation_system_prompt`, `variable_system_prompt`, `geographic_system_prompt`, `counterfactual_system_prompt`, `precedent_system_prompt`, `ledger_system_prompt`. All keyword-only.

- [ ] **Step 1: Rename one stage and run the snapshot**

Start with `drift_classifier`: `_system_prompt` → `system_prompt`, update its
call site, keep parameters keyword-only. Update the accessor in
`tests/test_scout_prompt_snapshot.py`.

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_snapshot -v`
Expected: PASS — a rename cannot change a returned string.

- [ ] **Step 2: Repeat for the remaining stages, running the snapshot after each**

Convert positional parameters to keyword-only as you go:
`context_validator._system_prompt(indication)` becomes
`system_prompt(*, indication)`, and its call site passes `indication=`.

- [ ] **Step 3: Confirm no private prompt accessors remain**

Run: `grep -rn "^def _[a-z_]*prompt" services/scout/stages/`
Expected: no output.

- [ ] **Step 4: Run the Python suite**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add services/scout/stages/ tests/test_scout_prompt_snapshot.py
git commit -m "refactor: one prompt seam per Scout model stage"
```

---

### Task 4: Prompt catalog

**Files:**
- Create: `services/scout/prompt_catalog.py`
- Create: `tests/test_scout_prompt_catalog.py`

**Interfaces:**
- Produces: `CatalogEntry` (frozen dataclass with `id: str`, `stage: str`, `title: str`, `builder: Callable[..., str]`, `context: tuple[str, ...]`, `framing_slot: str | None`, `result_fields: tuple[str, ...]`, `ui_labels: tuple[str, ...]`) and `PROMPT_CATALOG: tuple[CatalogEntry, ...]`.

- [ ] **Step 1: Write the completeness test**

```python
import unittest
from pathlib import Path

from services.scout.prompt_catalog import PROMPT_CATALOG

STAGES = Path("services/scout/stages")


class PromptCatalogTest(unittest.TestCase):
    def test_every_stage_prompt_is_catalogued(self) -> None:
        exposed = set()
        for path in sorted(STAGES.glob("*.py")):
            for line in path.read_text().splitlines():
                if line.startswith("def ") and "system_prompt" in line:
                    name = line[4:].split("(")[0]
                    exposed.add(f"{path.stem}.{name}")
        catalogued = {
            f"{entry.stage}.{entry.builder.__name__}" for entry in PROMPT_CATALOG
        }
        self.assertEqual(exposed, catalogued)

    def test_ids_are_unique(self) -> None:
        ids = [entry.id for entry in PROMPT_CATALOG]
        self.assertEqual(len(ids), len(set(ids)))
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_catalog -v`
Expected: FAIL with `ModuleNotFoundError: services.scout.prompt_catalog`.

- [ ] **Step 3: Write the catalog**

One entry per prompt. `ui_labels` uses the `ScoutSignalTopic` values from
`web/components/scout-signal-help.tsx`: `relationships`, `grounding`,
`alignment`, `precedent`. Leave `ui_labels` empty for prompts behind no signal.

```python
from dataclasses import dataclass
from typing import Callable

from .stages import drift_classifier


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    stage: str
    title: str
    builder: Callable[..., str]
    context: tuple[str, ...]
    framing_slot: str | None
    result_fields: tuple[str, ...]
    ui_labels: tuple[str, ...]


PROMPT_CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        id="drift.classify",
        stage="drift_classifier",
        title="Evidence relationship classification",
        builder=drift_classifier.system_prompt,
        context=("indication", "intervention_class"),
        framing_slot="drift_framing",
        result_fields=("matches[].relation",),
        ui_labels=("relationships",),
    ),
)
```

- [ ] **Step 4: Run the test until every prompt is catalogued**

Run: `.venv/bin/python -m unittest tests.test_scout_prompt_catalog -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/scout/prompt_catalog.py tests/test_scout_prompt_catalog.py
git commit -m "feat: declare Scout's prompt catalog"
```

---

### Task 5: Generate the shared reference

**Files:**
- Create: `scripts/generate_prompt_reference.py`
- Create: `shared/prompt_reference.json`
- Create: `tests/test_prompt_reference.py`

**Interfaces:**
- Consumes: `PROMPT_CATALOG` from Task 4.
- Produces: `shared/prompt_reference.json` with keys `version`, `prompts`, `framings`.

- [ ] **Step 1: Write the regeneration test**

```python
import json
import unittest
from pathlib import Path

from scripts.generate_prompt_reference import build_reference

REFERENCE = Path("shared/prompt_reference.json")


class PromptReferenceTest(unittest.TestCase):
    def test_committed_reference_matches_generator(self) -> None:
        self.assertEqual(
            json.loads(REFERENCE.read_text()),
            build_reference(),
            "run scripts/generate_prompt_reference.py and commit the result",
        )
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m unittest tests.test_prompt_reference -v`
Expected: FAIL with `ModuleNotFoundError` or missing file.

- [ ] **Step 3: Write the generator**

Render each prompt with `indication="{indication}"`,
`intervention_class="{intervention_class}"`, `source_type="itpp"`, and
`framing=""` so the configuration slot stays visible. Read every
`*_framing` key from the thirteen files in `services/scout/configs/` into
`framings`, one entry per configuration and key.

- [ ] **Step 4: Generate, then run the test**

```bash
.venv/bin/python scripts/generate_prompt_reference.py
.venv/bin/python -m unittest tests.test_prompt_reference -v
```

Expected: PASS, and `shared/prompt_reference.json` contains 17 prompts and 48 framing blocks.

- [ ] **Step 5: Confirm the snapshot still passes**

Run: `.venv/bin/python -m unittest discover -s tests`
Expected: all pass, proving generation changed no prompt.

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_prompt_reference.py shared/prompt_reference.json tests/test_prompt_reference.py
git commit -m "feat: generate the shared prompt reference"
```

---

### Task 6: Documentation surface

**Files:**
- Modify: `web/scripts/prepare-standalone.mjs` (copy the artifact into `web/public/`)
- Create: `web/components/docs/prompt-reference.tsx`
- Modify: `web/app/docs/page.tsx` (render the section)
- Modify: `web/components/scout-signal-help.tsx` (link each topic)

**Interfaces:**
- Consumes: `shared/prompt_reference.json` via `/prompt-reference.json`.
- Produces: `<PromptReference />`, a client component that fetches on first expand.

- [ ] **Step 1: Copy the artifact during the web build**

Add a copy of `../shared/prompt_reference.json` into `web/public/` in
`prepare-standalone.mjs`, beside the existing standalone preparation.

- [ ] **Step 2: Build the component**

One `<details>` per prompt, grouped by stage, collapsed. Fetch
`/prompt-reference.json` on the first `onToggle`, cache in state. Use
`text-[11px] leading-[1.6]` for the prompt body and `whitespace-pre-wrap`
so the section headers keep their line breaks. State above the list that
run-specific document content and the response schema are not shown.

- [ ] **Step 3: Render it under a new docs section and link the popovers**

Add the section after `workflows`. In `scout-signal-help.tsx`, add one link per
topic to `#prompts-<id>` using the `ui_labels` mapping from the artifact.

- [ ] **Step 4: Verify**

```bash
npm --prefix web run typecheck
npm --prefix web run build
```

Then serve the build and confirm: the docs route payload is unchanged within a
kilobyte, a collapsed entry fetches once on first open, and the prompt text
renders with its line breaks.

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat: publish Scout prompt reference in the docs"
```

---

## Self-review

**Spec coverage:** seam standardization (Tasks 2, 3), catalog (Task 4),
generated artifact and drift guard (Task 5), docs surface and popover links
(Task 6), byte-equality proof (Task 1, re-run in Tasks 2, 3, 5). The spec's
provider-boundary recording is deliberately narrowed: Task 1 renders through
builders, which is equivalent for the fourteen that have one, and Task 2 covers
the other three structurally with `ast`. Driving twelve stages through a
recording client would need full document, insight, and target fixtures per
stage — cost far above the risk, since Tasks 2 and 3 are moves and renames.

**Placeholders:** none. Task 1 Step 2 and Task 4 Step 3 deliberately instruct
reading exact signatures from source rather than guessing them.

**Type consistency:** `CatalogEntry.builder.__name__` in Task 4's test matches
the public builder names produced by Task 3. `build_reference()` in Task 5 is
the single generator entry point used by both the script and its test.
