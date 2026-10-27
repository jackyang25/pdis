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

On this platform a credential reaches a container as a `__NAME__` placeholder in
the jobspec that the deploy step seds a Drone secret into, so a placeholder is a
binding and not a value. `tests/test_jobspec_parity.py` separately asserts every
placeholder has a matching sed, which is what stops one being left unfilled.

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

# Derived from the settings table, not listed here: a hand-kept list would be one more place
# a credential's name lives, and the one that fails softest.
from shared.settings import SETTINGS

GATEWAY_CREDENTIALS = tuple(sorted(setting.name for setting in SETTINGS if setting.secret))


def _manifest(name: str) -> str:
    return (ROOT / name).read_text()


class DeploySecretTests(unittest.TestCase):
    def test_no_manifest_assigns_a_credential_a_literal_value(self) -> None:
        for name in DEPLOY_MANIFESTS:
            text = _manifest(name)
            for credential in GATEWAY_CREDENTIALS:
                with self.subTest(manifest=name, credential=credential):
                    for line in text.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#") or credential not in stripped:
                            continue
                        # A binding reads from somewhere rather than stating a
                        # value: a `__NAME__` placeholder the deploy step seds a
                        # Drone secret into, a CI secret reference, a template
                        # interpolation, or a shell expansion.
                        if re.search(
                            r"__[A-Z_]+__|\{\{|from_secret|\$\{|\$[A-Z_]", stripped
                        ):
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
            gateway = text[text.index('task "api"') : text.index('group "web"')]
            for credential in GATEWAY_CREDENTIALS:
                with self.subTest(jobspec=name, credential=credential):
                    # assertTrue rather than assertIn: the haystack is the whole
                    # gateway group, and printing it buries the one name that
                    # matters under five kilobytes of HCL.
                    self.assertTrue(
                        credential in gateway,
                        f"{name} never binds {credential} for the gateway",
                    )


if __name__ == "__main__":
    unittest.main()
