"""Opening a source an analysis already cites: allow-list and public-address checks, then text."""

from __future__ import annotations

import ipaddress
import re
import socket
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
        opener = urllib.request.build_opener(_PublicRedirectHandler())
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
    """Prevent imported result JSON from turning fetch_source into an SSRF hop."""
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
