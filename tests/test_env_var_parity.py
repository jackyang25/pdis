"""Every environment setting is declared once, in `shared/settings.py`.

A setting used to be stated in up to four places - the code that read it with its own
default, `.env.example` restating that default, a validation table, and a deployment
manifest - and only the names were checked, so a changed default went on being documented
at its old value. Now the table holds the name, default and description; code reads only
through it; and `.env.example` is generated from it. These tests hold all three.

The scan reads the code rather than a hand-kept list: a list would be another place to
drift.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

from shared import settings

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCANNED = ("api", "services", "shared", "scripts")
SETTINGS_MODULE = ROOT / "shared" / "settings.py"
ACCESSORS = frozenset({"text", "positive_int", "flag", "listed", "default"})


def _python_files():
    for package in SCANNED:
        yield from sorted((ROOT / package).rglob("*.py"))


def _direct_environment_reads() -> list[str]:
    """Places outside the settings module that read the environment themselves."""
    found = []
    for path in _python_files():
        if path == SETTINGS_MODULE:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.Attribute, ast.Name)):
                source = ast.unparse(node)
                if source in {"os.environ", "os.getenv", "environ", "getenv"}:
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return sorted(set(found))


def _names_read() -> set[str]:
    """Every setting named in a call to one of the settings accessors."""
    names = set()
    for path in _python_files():
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ACCESSORS
                and ast.unparse(node.func.value) == "settings"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                names.add(node.args[0].value)
    return names


class SettingsTableTests(unittest.TestCase):
    def test_only_the_settings_module_reads_the_environment(self) -> None:
        self.assertEqual(
            _direct_environment_reads(), [],
            "read the environment through shared.settings, so the setting is declared once",
        )

    def test_every_setting_read_is_declared(self) -> None:
        undeclared = sorted(_names_read() - set(settings.BY_NAME))
        self.assertEqual(undeclared, [], f"read but not in shared/settings.py: {undeclared}")

    def test_every_declared_setting_is_read(self) -> None:
        """A declared setting nothing reads sends someone to set a value with no effect."""
        unread = sorted(set(settings.BY_NAME) - _names_read())
        self.assertEqual(unread, [], f"declared in shared/settings.py but read nowhere: {unread}")

    def test_the_scan_finds_what_it_must(self) -> None:
        """A parity scan that silently stops finding anything passes forever."""
        read = _names_read()
        for name in ("KONG_KEY", "MAX_CONCURRENT_RUNS", "PDIS_MCP_BROWSER_ORIGINS"):
            with self.subTest(name=name):
                self.assertIn(name, read)

    def test_the_example_file_is_generated_from_the_table(self) -> None:
        self.assertEqual(
            (ROOT / ".env.example").read_text(),
            settings.render_example(),
            ".env.example differs from shared/settings.py; run scripts/generate_env_example.py",
        )

    def test_a_group_documented_elsewhere_names_every_one_of_its_settings(self) -> None:
        """The example file points to the group's README instead of listing its settings,
        so the README is where each one has to be found."""
        for group, doc in settings.GROUP_DOCS.items():
            text = (ROOT / doc).read_text()
            for setting in settings.SETTINGS:
                if setting.group == group:
                    with self.subTest(setting=setting.name):
                        self.assertIn(setting.name, text)

    def test_a_credential_has_no_default_and_no_local_value(self) -> None:
        for setting in settings.SETTINGS:
            if setting.secret:
                with self.subTest(name=setting.name):
                    self.assertEqual((setting.default, setting.local), ("", ""))

    def test_a_malformed_number_stops_startup_naming_the_setting(self) -> None:
        from unittest.mock import patch

        with patch.dict("os.environ", {"MAX_CONCURRENT_RUNS": "two"}):
            with self.assertRaisesRegex(settings.ConfigurationError, "MAX_CONCURRENT_RUNS"):
                settings.validate()


if __name__ == "__main__":
    unittest.main()
