"""Opening a source an analysis already cites: allow-list and public-address checks, then text."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlparse

from . import limits, sources


def fetch_source(url: str, allowed_urls: set[str]) -> str:
    """Fetch the full text behind an ALREADY-CITED url. Grounding + safety: only
    URLs present in the result may be fetched (no fresh/arbitrary browsing)."""
    url = url.strip()
    if url not in allowed_urls:
        return (
            "Refused: that URL is not one of the sources cited in this result. "
            "I can only open links that already appear in the results."
        )
    if not _is_public_http_url(url):
        return "Refused: cited source URL does not resolve to a public HTTP endpoint."
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "pdis-ask/0.1"})
        opener = urllib.request.build_opener(
            # No proxy: through one, the address connected to would be the proxy's,
            # and the check below would no longer govern where the request goes.
            urllib.request.ProxyHandler({}),
            _PublicHTTPHandler,
            _PublicHTTPSHandler,
            _PublicRedirectHandler(),
        )
        with opener.open(request, timeout=limits.FETCH_TIMEOUT_SECONDS) as response:
            raw = response.read(limits.MAX_FETCH_BYTES).decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return f"Could not open this source ({exc}). Fall back to the excerpt in the result."

    text = sources.truncate(_strip_html(raw), limits.MAX_FETCH_CHARS,
                            "only the start of this source can be read; rely on the result's excerpt for the rest")
    return text or "(the source returned no readable text)"


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _is_public_http_url(url: str) -> bool:
    """Prevent imported result JSON from turning fetch_source into an SSRF hop.

    An early, readable refusal only. A name can resolve differently a moment later, so
    the check that governs is the one `_connect_public` makes on the address it opens.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or default_port)
        return bool(addresses) and all(
            ipaddress.ip_address(sockaddr[0]).is_global
            for *_, sockaddr in addresses
        )
    except (OSError, ValueError):
        return False


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Apply the same public-endpoint check to every redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if not _is_public_http_url(newurl):
            raise urllib.error.HTTPError(
                newurl, code, "redirect to non-public endpoint refused", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _NonPublicAddress(OSError):
    """The host resolved to an address that is not on the public internet."""


def _connect_public(host: str, port: int, timeout, source_address) -> socket.socket:  # noqa: ANN001
    """Resolve once, refuse unless every address is public, and connect to one of them.

    Connecting to the address that was checked, rather than handing the name back to the
    socket layer, closes the gap in which a second lookup could answer with a private one.
    """
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        public = bool(addresses) and all(
            ipaddress.ip_address(sockaddr[0]).is_global for *_, sockaddr in addresses
        )
    except ValueError:
        public = False
    if not public:
        raise _NonPublicAddress(f"{host} does not resolve to a public address")
    address = addresses[0][4]
    return socket.create_connection((address[0], address[1]), timeout, source_address)


class _PublicHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = _connect_public(self.host, self.port, self.timeout, self.source_address)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, context: ssl.SSLContext | None = None, **kwargs) -> None:  # noqa: ANN002, ANN003
        self._tls = context or ssl.create_default_context()
        super().__init__(*args, context=self._tls, **kwargs)

    def connect(self) -> None:
        sock = _connect_public(self.host, self.port, self.timeout, self.source_address)
        # The certificate is still verified against the name, not the address.
        self.sock = self._tls.wrap_socket(sock, server_hostname=self.host)


class _PublicHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):  # noqa: ANN001
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):  # noqa: ANN001
        return self.do_open(_PublicHTTPSConnection, req)
