"""No deploy artifact carries a credential's value, and none forgets to bind one.

Two failures, opposite in shape. A credential written into a manifest is a
credential in the git history, where rotating it means rewriting history rather
than changing one entry - and the manifests are the files most likely to be
edited quickly, under deploy pressure, by someone pasting a working value in to
see if it helps. A credential left out entirely fails differently and later: the
lane that needed it disables itself, the deploy comes up green, and the missing
capability is discovered by a user.

This replaces a check that read `render.yaml` and asserted `sync: false` beside
`TAVILY_API_KEY`. The platform changed; the property did not.

The literal check is deliberately blunt - a NAME=value assignment for a known
credential, anywhere in a committed manifest. A blunt rule with no exceptions is
one nobody has to interpret at the moment they are least inclined to.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Committed files that describe a deployment. `.env` files are not here: they
# are gitignored, and the example files carry deliberately empty values.
DEPLOY_MANIFESTS = ("jobspec.nomad", "jobspec_acc.nomad", ".drone.yml", "compose.yaml")

# Derived from the code, not listed here. A hand-kept list is a fourth place a
# credential's name lives - after the code that reads it, `.env.example`, and the
# jobspec that binds it - and the one that fails softest: adding a credential
# everywhere except this tuple leaves the binding check silently not looking for
# it, which is the failure this module exists to prevent.
from test_env_var_parity import _env_names_read_in_code

CREDENTIAL_SUFFIXES = ("_API_KEY", "_API_TOKEN")

# Read by the ToolUniverse package inside the connector image rather than by any
# code in this repository, so no scan of this source tree can find it. It is
# named here because the connector still has to be handed it.
CONNECTOR_ONLY_CREDENTIALS = ("SEMANTIC_SCHOLAR_API_KEY",)


def _gateway_credentials() -> tuple[str, ...]:
    """Every credential the gateway's own code reads."""
    return tuple(
        sorted(
            name
            for name in _env_names_read_in_code()
            if name.endswith(CREDENTIAL_SUFFIXES)
        )
    )


GATEWAY_CREDENTIALS = _gateway_credentials()
CREDENTIALS = tuple(sorted({*GATEWAY_CREDENTIALS, *CONNECTOR_ONLY_CREDENTIALS}))


def _manifest(name: str) -> str:
    return (ROOT / name).read_text()


class DeploySecretTests(unittest.TestCase):
    def test_no_manifest_assigns_a_credential_a_literal_value(self) -> None:
        for name in DEPLOY_MANIFESTS:
            text = _manifest(name)
            for credential in CREDENTIALS:
                with self.subTest(manifest=name, credential=credential):
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#") or credential not in stripped:
                            continue
                        # A binding reads from somewhere: a template
                        # interpolation, a CI secret reference, or a shell
                        # expansion of a value supplied at runtime.
                        if re.search(r"\{\{|from_secret|\$\{|\$[A-Z_]", stripped):
                            continue
                        # An assignment with anything after it that is not a
                        # reference is a committed value.
                        assignment = re.search(
                            rf"{credential}\s*[:=]\s*(\S.*)?$", stripped
                        )
                        self.assertFalse(
                            assignment and (assignment.group(1) or "").strip(),
                            f"{name} assigns {credential} a literal value: {stripped!r}",
                        )

    def test_the_gateway_binds_every_credential_it_reads(self) -> None:
        """A lane whose key is unbound turns itself off, and a deploy missing one
        still comes up healthy. Nothing reports it but the absent capability."""
        for name in ("jobspec.nomad", "jobspec_acc.nomad"):
            text = _manifest(name)
            gateway = text[: text.index('group "web"')]
            for credential in GATEWAY_CREDENTIALS:
                with self.subTest(jobspec=name, credential=credential):
                    # assertTrue rather than assertIn: the haystack is the whole
                    # gateway group, and printing it buries the one name that
                    # matters under five kilobytes of HCL.
                    self.assertTrue(
                        credential in gateway,
                        f"{name} never binds {credential} for the gateway",
                    )

    def test_the_shared_connector_token_is_bound_on_both_sides(self) -> None:
        """It authenticates the gateway to the connector, so one value has to
        reach two jobs. Render generated it and injected it into both; nothing
        generates it now, which makes forgetting one side the likely failure."""
        for name in ("jobspec.nomad", "jobspec_acc.nomad"):
            text = _manifest(name)
            connector = text[text.index('group "tooluniverse"') :]
            gateway = text[: text.index('group "web"')]
            with self.subTest(jobspec=name):
                self.assertIn("TOOLUNIVERSE_API_TOKEN", gateway)
                self.assertIn("TOOLUNIVERSE_API_TOKEN", connector)


if __name__ == "__main__":
    unittest.main()
