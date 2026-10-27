"""Every environment setting the backend reads, declared once.

A setting's name, default, whether it is a credential, and what it does live in one table.
Code reads the environment only through the accessors here, and `.env.example` is generated
from the table (`scripts/generate_env_example.py`); a test fails when the committed file
differs. Before this, a setting was stated in up to four places - the code that read it with
its own default, the example file's prose restating that default, a validation table naming
it again, and a deployment manifest - and only the names were checked, so a changed default
went on being documented, and pinned in local files, at its old value.

`local` is the value a local run sets where it differs from a deployment; everything else is
left to its default, so a default changed here reaches every environment at once.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Kind = Literal["text", "positive_int", "flag"]


class ConfigurationError(RuntimeError):
    """A configuration value is present but cannot be read as what it must be.

    Distinct from a missing credential: an absent credential is a deployment that has not
    finished, and is reported to the caller that needs it, whereas an unparseable number is
    a typo that will never resolve itself. Raising it keeps a malformed value from being
    silently replaced by a default that happens to work, which is how a tuning change
    appears to take effect and does not.
    """


@dataclass(frozen=True)
class Setting:
    name: str
    group: str
    #: What the setting does, as the example file says it. Its default is appended there
    #: from `default`, so the prose never restates a value.
    help: str
    default: str = ""
    kind: Kind = "text"
    #: A credential: never given a value in a committed file, bound from a secret where
    #: deployed.
    secret: bool = False
    #: The value a local run sets because it differs from a deployment.
    local: str = ""
    #: A credential needed only in place of another, so the example leaves it commented.
    alternative: bool = False


MODELS = "Model gateway"
RETRIEVAL = "Retrieval"
CONCURRENCY = "Concurrency"
MCP = "Employee MCP access (optional)"
LOGS = "Logs"

#: Groups whose settings are documented, with their setup, in their own README. The example
#: file names the README instead of listing settings nobody sets until they follow it.
GROUP_DOCS = {MCP: "api/mcp/README.md"}

#: What a group's heading says before its settings, in the example file.
GROUP_NOTES = {
    RETRIEVAL: (
        "Searcher calls every provider directly. A key raises that provider's quota, so set\n"
        "all of them: each lane runs without its key, more slowly, except Semantic Scholar\n"
        "and Tavily, which report themselves unconfigured until theirs is set."
    ),
}

SETTINGS: tuple[Setting, ...] = (
    Setting(
        "KONG_KEY", MODELS, secret=True,
        help=(
            "Kong's gateway key. When set, both the OpenAI-compatible and the native Anthropic\n"
            "clients route through Kong's unified endpoints with this one key, and\n"
            "OPENAI_API_KEY / ANTHROPIC_API_KEY are not used. Issued by the foundation's AI\n"
            "gateway team."
        ),
    ),
    Setting("OPENAI_API_KEY", MODELS, secret=True, alternative=True,
            help="Direct OpenAI key, used only when KONG_KEY is unset."),
    Setting("ANTHROPIC_API_KEY", MODELS, secret=True, alternative=True,
            help="Direct Anthropic key, used only when KONG_KEY is unset."),
    Setting("NCBI_API_KEY", RETRIEVAL, secret=True, help=(
            "NCBI E-utilities (PubMed): ~10 calls a second with a key, ~3 without. Issued from\n"
            "an NCBI account's settings: https://account.ncbi.nlm.nih.gov/settings/"
        )),
    Setting(
        "SEMANTIC_SCHOLAR_API_KEY", RETRIEVAL, secret=True,
        help=(
            "Semantic Scholar: one call a second with a key. Keyless calls share a public pool\n"
            "that is rate-limited in practice, so the lane needs this key. The limit is the\n"
            "key's, across everything using it: give each environment its own.\n"
            "https://www.semanticscholar.org/product/api#api-key-form"
        ),
    ),
    Setting(
        "OPENFDA_API_KEY", RETRIEVAL, secret=True,
        help=(
            "openFDA (FDA Regulatory and FDA Safety): 120,000 calls a day with a key, 1,000\n"
            "without. https://open.fda.gov/apis/authentication/"
        ),
    ),
    Setting(
        "TAVILY_API_KEY", RETRIEVAL, secret=True,
        help=(
            "Tavily web search, a paid service: the lane disables itself without a key. Use a\n"
            "production key; a development key allows 100 requests a minute.\n"
            "https://app.tavily.com"
        ),
    ),
    Setting(
        "SEARCH_CONTACT_EMAIL", RETRIEVAL,
        help=(
            "A contact providers may write to about this deployment's traffic: sent as NCBI's\n"
            "`email` and in the User-Agent. A team mailbox, never a person's. Unset sends none."
        ),
    ),
    Setting(
        "MAX_CONCURRENT_RUNS", CONCURRENCY, default="2", kind="positive_int",
        help=(
            "Analyses that run at once before the rest queue. Sized against the instance's\n"
            "memory, not throughput: the deployment jobspec states the two together."
        ),
    ),
    Setting("PDIS_MCP_ENABLED", MCP, default="false", kind="flag", help="`true` to serve the MCP endpoint."),
    Setting("PDIS_MCP_URL", MCP, help="Exact externally reachable HTTPS endpoint, ending /api/mcp (no trailing slash)."),
    Setting("PDIS_MCP_ISSUER", MCP, help="Exact token issuer."),
    Setting("PDIS_MCP_JWKS_URL", MCP, help="The issuer's administrator-approved public signing-key endpoint."),
    Setting("PDIS_MCP_AUDIENCE", MCP, help="Audience registered for this API, not the client application's ID."),
    Setting("PDIS_MCP_SCOPE", MCP, default="pdis:search", help="Delegated employee permission required on every MCP tool request."),
    Setting(
        "PDIS_MCP_BROWSER_ORIGINS", MCP,
        help=(
            "Comma-separated HTTPS origins for browser-based MCP clients. Grants them nothing\n"
            "on the website's other endpoints."
        ),
    ),
    Setting(
        "LOG_FORMAT", LOGS, default="json", local="text",
        help="`json` for a deployment's log aggregator; `text` is easier to read locally.",
    ),
    Setting("LOG_LEVEL", LOGS, default="INFO", help="Python logging level."),
)

GROUPS = (MODELS, RETRIEVAL, CONCURRENCY, MCP, LOGS)
BY_NAME: dict[str, Setting] = {setting.name: setting for setting in SETTINGS}


def default(name: str) -> str:
    return BY_NAME[name].default


def text(name: str) -> str:
    """The setting's value, stripped, or its default when unset or blank."""
    setting = BY_NAME[name]
    return (os.environ.get(name) or "").strip() or setting.default


def positive_int(name: str) -> int:
    raw = text(name)
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be a positive integer, got {raw!r}") from None
    if value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer, got {value}")
    return value


def flag(name: str) -> bool:
    raw = text(name).lower()
    if raw not in {"true", "false"}:
        raise ConfigurationError(f"{name} must be true or false, got {raw!r}")
    return raw == "true"


def listed(name: str) -> tuple[str, ...]:
    """A comma-separated setting as its non-blank items."""
    return tuple(item.strip() for item in text(name).split(",") if item.strip())


_READERS = {"positive_int": positive_int, "flag": flag}


def validate() -> None:
    """Parse every typed setting once, at startup, so a typo stops the process naming it."""
    for setting in SETTINGS:
        if reader := _READERS.get(setting.kind):
            reader(setting.name)


def render_example() -> str:
    """`.env.example`, from the table."""
    lines = [
        "# PDIS API environment. Generated from shared/settings.py by",
        "# scripts/generate_env_example.py; edit that table, not this file.",
        "# Copy this file to .env; never commit the populated file.",
        "#",
        "# Uncommented entries are what you set: credentials, and the values a local run",
        "# differs on. Commented entries are optional overrides; unset, the default shown",
        "# applies, so a default changed in code reaches every environment.",
    ]
    for group in GROUPS:
        lines += ["", f"# --- {group} " + "-" * max(3, 72 - len(group))]
        if note := GROUP_NOTES.get(group):
            lines += [f"# {line}" for line in note.splitlines()]
        if doc := GROUP_DOCS.get(group):
            lines.append(f"# Off unless configured; its settings and setup are in {doc}.")
            continue
        for setting in (item for item in SETTINGS if item.group == group):
            lines.append("")
            lines += [f"# {line}" for line in setting.help.splitlines()]
            if setting.default:
                lines.append(f"# Default: {setting.default}")
            if setting.secret and not setting.alternative:
                lines.append(f"{setting.name}=")
            elif setting.local:
                lines.append(f"{setting.name}={setting.local}")
            else:
                lines.append(f"# {setting.name}=")
    return "\n".join(lines) + "\n"
