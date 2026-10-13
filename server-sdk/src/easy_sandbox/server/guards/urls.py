"""URL guard: refuse loopback, link-local and private addresses unless explicitly allowed.

Only the address written in the URL is classified.  DNS names are not resolved here.
``handle_browser_navigate`` calls this before opening the URL.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from ..policy import PolicyDenied

__all__ = ["check_url"]


def _blocked_address(host: str) -> bool:
    """True when *host* is loopback, link-local, or private (including an IPv4-mapped form)."""
    name = host.strip("[]").lower().rstrip(".")
    if name == "localhost" or name.endswith(".localhost"):
        return True
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(name)
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return bool(ip.is_loopback or ip.is_link_local or ip.is_private)


def check_url(url: str, *, allow_private: bool = False) -> str:
    """Admit *url*.

    Loopback (``127.0.0.1``, ``::1``, ``localhost``), link-local (``169.254.0.0/16``,
    ``fe80::/10``) and private addresses are denied unless *allow_private* is true.
    A public ``https`` URL is returned unchanged.

    Raises:
        PolicyDenied: ``url_invalid`` (400) or ``url_denied``.
    """
    if not isinstance(url, str) or not url or any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
        raise PolicyDenied("url_invalid", "Invalid URL", status=400, error_type="ValueError")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise PolicyDenied(
            "url_invalid", "Invalid URL", status=400, error_type="ValueError"
        ) from None
    if parts.scheme not in ("http", "https") or not parts.hostname or port == 0:
        raise PolicyDenied("url_invalid", "Invalid URL", status=400, error_type="ValueError")
    if not allow_private and _blocked_address(parts.hostname):
        raise PolicyDenied(
            "url_denied", "Loopback, link-local and private addresses are not allowed"
        )
    return url
