"""Prefer IPv4 for the searcher's direct-HTTP backends (PubMed, ClinicalTrials).

Some container environments (Docker without an IPv6 route - common locally and
on some hosts) resolve a service like NCBI to *both* an IPv4 and an IPv6
address, but can only route IPv4. Python's `urllib` does not reliably fall back
from an unreachable IPv6 address, so a lookup that yields IPv6 fails with
"[Errno 101] Network is unreachable" - even though IPv4 would have worked. The
OpenAI SDK is unaffected (it does its own IPv4 fallback), which is why only the
literature/registry lanes broke.

`prefer_ipv4()` installs a process-wide address-resolution shim: for ordinary
(family-unspecified) lookups it returns IPv4 addresses when the host has any,
and otherwise falls back to the normal result - so IPv6-only hosts still work.
Idempotent; safe to call more than once.
"""

from __future__ import annotations

import socket

_installed = False


def prefer_ipv4() -> None:
    global _installed
    if _installed:
        return
    _original = socket.getaddrinfo

    def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        if family == 0:  # unspecified -> try IPv4 first, keep IPv6 as fallback
            try:
                ipv4 = _original(host, port, socket.AF_INET, type, proto, flags)
                if ipv4:
                    return ipv4
            except socket.gaierror:
                pass
        return _original(host, port, family, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo
    _installed = True
