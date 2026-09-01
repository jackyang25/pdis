"""Every environment variable the backend reads is documented in `.env.example`.

Configuration is stated in two places that drift apart silently: the code that
reads a variable, and the file a developer copies to find out what to set. When
they disagree the failure is invisible - the lane that needed the variable turns
itself off, or a default takes over, and nothing reports that a value was
missing. Tavily reached production configured in the deploy manifest and absent
from `.env.example`, so no local environment ever ran that lane.

The scan reads the code rather than a hand-kept list. A list would be a third
place to drift, and the point of this test is that there are only two.

Reads through `api.deps._positive_int` and `_positive_float` are counted too:
they take the variable name as their first argument, so a grep for `os.getenv`
misses them and a reviewer reading such a grep concludes the variable is unused.
"""

from __future__ import annotations

import ast
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED_PACKAGES = ("api", "services", "shared")
ENV_EXAMPLE = ROOT / ".env.example"

# These take the variable name as their first positional argument.
NAME_IN_FIRST_ARG = frozenset({"_positive_int", "_positive_float"})

# `# NAME=` counts as documented: some variables are supplied by the host or are
# correct at their default, and this file records them without inviting a value.
DOCUMENTED = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=")


def _env_names_read_in_code() -> dict[str, set[str]]:
    """Map each variable name to the files that read it."""
    found: dict[str, set[str]] = {}

    def record(name: str, path: pathlib.Path) -> None:
        if name.isupper():
            found.setdefault(name, set()).add(str(path.relative_to(ROOT)))

    for package in SCANNED_PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    attr = getattr(func, "attr", None) or getattr(func, "id", "")
                    source = ast.unparse(func)
                    reads_env = (
                        attr in NAME_IN_FIRST_ARG
                        or "getenv" in source
                        or ("environ" in source and attr == "get")
                    )
                    first = node.args[0] if node.args else None
                    if reads_env and isinstance(first, ast.Constant):
                        if isinstance(first.value, str):
                            record(first.value, path)
                elif isinstance(node, ast.Subscript):
                    if "environ" in ast.unparse(node.value):
                        index = node.slice
                        if isinstance(index, ast.Constant) and isinstance(
                            index.value, str
                        ):
                            record(index.value, path)
    return found


def _documented_names() -> set[str]:
    return {
        match.group(1)
        for line in ENV_EXAMPLE.read_text().splitlines()
        if (match := DOCUMENTED.match(line))
    }


class EnvVarParityTests(unittest.TestCase):
    def test_every_variable_read_by_the_backend_is_documented(self) -> None:
        read = _env_names_read_in_code()
        undocumented = sorted(set(read) - _documented_names())
        self.assertEqual(
            undocumented,
            [],
            "read in code but absent from .env.example: "
            + "; ".join(f"{name} ({', '.join(sorted(read[name]))})" for name in undocumented),
        )

    def test_the_scan_finds_the_variables_it_is_supposed_to_find(self) -> None:
        """Guards the scan itself.

        A parity test that silently stops finding anything passes forever. These
        three are read through the three different shapes the scan has to
        understand - `os.environ.get`, `os.getenv`, and a name passed to a helper
        - so losing any one of them breaks this before it breaks the check above.
        """
        read = _env_names_read_in_code()
        for name in ("OPENAI_API_KEY", "MAX_CONCURRENT_RUNS", "TOOLUNIVERSE_TIMEOUT_SECONDS"):
            with self.subTest(name=name):
                self.assertIn(name, read)

    def test_documented_variables_are_not_stale(self) -> None:
        """A name in `.env.example` that nothing reads sends a developer to set a
        value with no effect, which is the same drift in the other direction."""
        documented = _documented_names()
        unread = sorted(documented - set(_env_names_read_in_code()))
        self.assertEqual(
            unread,
            [],
            f"documented in .env.example but read nowhere in the backend: {unread}",
        )


if __name__ == "__main__":
    unittest.main()
