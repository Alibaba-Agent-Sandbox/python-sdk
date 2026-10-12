"""Secret redaction for events, logs and persisted items — stdlib-only."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["REDACTED", "Redactor"]

REDACTED = "[REDACTED]"

_MIN_SECRET_LEN = 6

# Common credential shapes redacted even when the value is not registered.
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{16,}"),
    re.compile(r"(?i)(x-api-key|api[_-]?key|authorization)(\s*[:=]\s*)(['\"]?)[^\s'\",]{8,}"),
)


class Redactor:
    """Replace known secret values (and common token shapes) in text.

    Each registered secret is matched verbatim, URL-encoded and JSON-escaped.
    Base64 or otherwise transformed copies cannot be detected.
    """

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._needles: list[str] = []
        self.add(secrets)

    def add(self, secrets: Iterable[str]) -> None:
        """Register more secret values (values shorter than 6 chars are ignored)."""
        for value in secrets:
            if not value or len(value) < _MIN_SECRET_LEN:
                continue
            for form in (value, quote(value, safe=""), json.dumps(value)[1:-1]):
                if form and form not in self._needles:
                    self._needles.append(form)
        # Longest first so a secret containing another one is fully masked.
        self._needles.sort(key=len, reverse=True)

    def __call__(self, text: str) -> str:
        """Return *text* with secrets masked."""
        return self.redact(text)

    def redact(self, text: str) -> str:
        """Return *text* with secrets masked."""
        if not text:
            return text
        for needle in self._needles:
            if needle in text:
                text = text.replace(needle, REDACTED)
        for pattern in _TOKEN_PATTERNS[:3]:
            text = pattern.sub(REDACTED, text)
        return _TOKEN_PATTERNS[3].sub(
            lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}", text
        )

    def safe_cut(self, text: str) -> int:
        """Index up to which *text* can be emitted without splitting a secret.

        The unsafe tail (``max secret length - 1`` chars, extended back to the
        start of any secret occurrence that crosses the cut) is held back until
        more text arrives.
        """
        if not self._needles:
            return len(text)
        keep = len(self._needles[0]) - 1
        cut = max(0, len(text) - keep)
        for needle in self._needles:
            pos = text.find(needle)
            while pos != -1:
                if pos < cut < pos + len(needle):
                    cut = pos
                pos = text.find(needle, pos + 1)
        return cut

    def redact_obj(self, obj: object) -> object:
        """Recursively redact every string inside a JSON-like structure."""
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {k: self.redact_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact_obj(v) for v in obj]
        return obj
