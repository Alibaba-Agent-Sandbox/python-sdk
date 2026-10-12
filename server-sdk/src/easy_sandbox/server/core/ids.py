"""Operation ID grammar and the legacy-name mangling table (design 02, section 2)."""

from __future__ import annotations

import re

__all__ = [
    "ID_RE",
    "RESERVED_NAMESPACES",
    "is_valid_id",
    "mangle_custom_name",
    "validate_id",
]

ID_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$")

#: Namespaces only the SDK registers in (``custom`` is the user-command namespace).
RESERVED_NAMESPACES = frozenset(
    {
        "core",
        "files",
        "commands",
        "process",
        "terminal",
        "system",
        "devtools",
        "browser",
        "agents",
        "ext",
    }
)

_NON_ID_CHARS = re.compile(r"[^a-z0-9_]+")


def is_valid_id(op_id: object) -> bool:
    """Return whether *op_id* is a well-formed dotted operation ID."""
    return isinstance(op_id, str) and ID_RE.match(op_id) is not None


def validate_id(op_id: object) -> str:
    """Return *op_id* or raise :class:`ValueError` explaining the grammar."""
    if not is_valid_id(op_id):
        raise ValueError(
            f"invalid operation id {op_id!r}: use 2 to 5 dotted lowercase segments "
            "([a-z][a-z0-9_]*), e.g. 'files.list'"
        )
    assert isinstance(op_id, str)
    return op_id


def mangle_custom_name(name: str) -> str:
    """Map a legacy ``CommandRegistry`` name to a ``custom.<segment>`` ID.

    Lower-cases, replaces every run of characters outside ``[a-z0-9_]`` with ``_`` and prefixes
    ``c_`` when the result does not start with a letter (``Hello-World.v2`` ->
    ``custom.hello_world_v2``).  Collision handling (``_2``, ``_3``) is the caller's job.
    """
    segment = _NON_ID_CHARS.sub("_", name.lower())
    if not segment or not segment[0].isalpha() or not segment[0].isascii():
        segment = f"c_{segment}"
    return f"custom.{segment}"
