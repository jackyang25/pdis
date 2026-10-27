"""Opt-in remote access, with no anonymous or insecure fallback."""

from dataclasses import dataclass
from urllib.parse import urlsplit
from pydantic import AnyHttpUrl

from shared import settings

MCP_PATH = "/api/mcp"
MCP_METADATA_PATH = "/api/.well-known/oauth-protected-resource"


@dataclass(frozen=True)
class MCPSettings:
    url: str
    issuer: str
    jwks_url: str
    audience: str
    scope: str = "pdis:search"
    browser_origins: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("url", "issuer", "jwks_url"):
            value = getattr(self, name)
            AnyHttpUrl(value)
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or "*" in value
            ):
                raise ValueError(
                    f"PDIS MCP {name} must be an absolute HTTPS URL without credentials, query or fragment"
                )
        if urlsplit(self.url).path != MCP_PATH:
            raise ValueError("PDIS_MCP_URL must end in /api/mcp (no trailing slash)")
        if (
            not self.audience.strip()
            or not self.scope.strip()
            or any(c.isspace() for c in self.scope)
        ):
            raise ValueError(
                "PDIS MCP audience and single required scope must be nonempty"
            )
        for origin in self.browser_origins:
            AnyHttpUrl(origin)
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
                or "*" in origin
            ):
                raise ValueError(
                    "PDIS_MCP_BROWSER_ORIGINS must contain full HTTPS origins without paths"
                )

    @property
    def origin(self) -> str:
        parsed = urlsplit(self.url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def metadata_url(self) -> str:
        # RFC 9728 discovery via WWW-Authenticate can name this explicit URL.
        # Keeping it below /api avoids a new root-level ingress exception.
        return f"{self.origin}{MCP_METADATA_PATH}"

    @property
    def allowed_origins(self) -> list[str]:
        return list(dict.fromkeys([self.origin, *self.browser_origins]))


def load_mcp_settings() -> MCPSettings | None:
    try:
        enabled = settings.flag("PDIS_MCP_ENABLED")
    except settings.ConfigurationError as exc:
        raise ValueError(str(exc)) from None
    if not enabled:
        return None
    return MCPSettings(
        url=settings.text("PDIS_MCP_URL"),
        issuer=settings.text("PDIS_MCP_ISSUER"),
        jwks_url=settings.text("PDIS_MCP_JWKS_URL"),
        audience=settings.text("PDIS_MCP_AUDIENCE"),
        scope=settings.text("PDIS_MCP_SCOPE"),
        browser_origins=settings.listed("PDIS_MCP_BROWSER_ORIGINS"),
    )
