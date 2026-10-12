"""``OpRef`` and the ``ops`` attribute tree (design 02, section 1; decision D2).

Nodes are deliberately **not** ``str`` subclasses: a ``str`` subclass would shadow verbs that are
``str`` methods (``ops.custom.format`` would be ``str.format``).
"""

from __future__ import annotations

from typing import Any

__all__ = ["OpRef", "OpTree", "ops"]


class OpRef:
    """A dotted path node: ``ops.files.list`` is ``OpRef("files.list")``.

    The node does not know whether it is a leaf or a namespace; the registry decides when the
    reference is used (an ID may never be a prefix of another ID, so the answer is unambiguous).
    """

    __slots__ = ("_path",)
    _path: str

    def __init__(self, path: str) -> None:
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> OpRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return OpRef(f"{self._path}.{name}")

    def __getitem__(self, name: str) -> OpRef:
        return OpRef(f"{self._path}.{name}")

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("OpRef is immutable")

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"ops.{self._path}"

    def __hash__(self) -> int:
        return hash(self._path)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (OpRef, str)):
            return str(other) == self._path
        return NotImplemented

    def __dir__(self) -> list[str]:
        return []


class OpTree:
    """Root of the reference tree (exported as :data:`ops`)."""

    __slots__ = ()

    def __getattr__(self, name: str) -> OpRef:
        if name.startswith("_"):
            raise AttributeError(name)
        return OpRef(name)

    def __getitem__(self, name: str) -> OpRef:
        return OpRef(name)

    def __repr__(self) -> str:
        return "ops"


ops = OpTree()
