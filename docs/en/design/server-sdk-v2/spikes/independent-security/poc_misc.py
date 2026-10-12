"""PoCs: URL scopes (04 section 9, 05 section 7) and other design-level models."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from _common import *  # noqa: F403
from _common import Denied, secure


def is_u1_url_glob_matches_the_raw_string_not_the_host():
    """IS-U1: 'allow/deny glob lists over scheme://host/path' is bypassable by parser differentials.

    Rewired to the spike's UrlScope (compares the PARSED hostname; strict parser; canonical URL returned)."""
    from ebxp.guards import UrlScope, check_url
    scope = UrlScope(hosts=("*.example.com",), schemes=("https",), block_private=True)
    bypass = []
    for url in ("https://evil.test#.example.com/x", "https://evil.test?.example.com/x", "https://evil.test\\.example.com/x",
                "https://evil.test%2f.example.com/x", "https://user@evil.test/@a.example.com/x", "https://a.example.com@evil.test/x",
                "https://\u0430.example.com/x", "https://example.com.evil.test/x", "http://a.example.com/x"):
        try:
            check_url(scope, url)
            bypass.append(url)
        except Denied:
            pass
    secure(not bypass, f"URLs whose real host is not under example.com (or wrong scheme) were admitted: {bypass}")
    secure(check_url(scope, "https://a.example.com/x").startswith("https://a.example.com"), "baseline legitimate URL refused")


def is_u1b_private_range_rule_misses_cgnat_metadata_address():
    """IS-U1: Alibaba Cloud's metadata service is 100.100.100.200 (100.64/10): block_private must cover it."""
    from ebxp.guards import block_private
    missed = [h for h in ("100.100.100.200", "100.64.0.1", "192.168.1.1", "10.0.0.1", "0.0.0.0", "169.254.169.254", "127.0.0.1",
                          "::1", "fd00::1", "::ffff:100.100.100.200") if not block_private(h)]
    secure(not missed, f"block_private lets these internal addresses through: {missed}")


CHECKS = [
    ("IS-U1", is_u1_url_glob_matches_the_raw_string_not_the_host),
    ("IS-U1b", is_u1b_private_range_rule_misses_cgnat_metadata_address),
]
