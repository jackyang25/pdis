"""Give every test run the same environment, whoever is running it.

`api/main.py` calls `load_dotenv()` at import, so a developer with a populated
`.env` runs the suite with real provider credentials present and CI runs it with
none. That difference is invisible until it is not: two Inspector route tests
stubbed the pipeline but not the client acquisition that precedes it, passed on
every machine that had a `.env`, and failed on the first CI run.

Emptied rather than deleted. `load_dotenv()` does not override a variable that is
already set, so assigning a value is what actually keeps `.env` out of the run;
deleting one would let dotenv put the real value back when `api.main` is
imported. Empty is what the credential checks already treat as absent, so this
reproduces CI rather than approximating it.

Empty rather than a placeholder, because a placeholder would let a test that
forgets to stub its provider client pass anyway - which is the failure this file
exists to prevent, not one to make uniform. A test needing a credential supplies
its own with `patch.dict`, as `test_anthropic_client.py` does.

Only pytest imports this file. `python -m unittest discover -s tests` remains
valid but does not read it, so it still runs with whatever `.env` provides. CI
runs pytest, which is what makes this the environment that gates a merge.
"""

from __future__ import annotations

import os

# Emptied before any test module imports `api.main`, which is where the
# `load_dotenv()` call lives. pytest imports conftest before collecting tests.
ISOLATED_CREDENTIALS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "NCBI_API_KEY",
    "TAVILY_API_KEY",
    "TOOLUNIVERSE_API_TOKEN",
    "SEMANTIC_SCHOLAR_API_KEY",
)

for _name in ISOLATED_CREDENTIALS:
    os.environ[_name] = ""
