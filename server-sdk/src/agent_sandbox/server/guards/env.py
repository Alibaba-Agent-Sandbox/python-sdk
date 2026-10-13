"""Environment guard: ordinary ``KEY=VALUE`` assignments, never ``ABX_*``.

A caller-supplied deny list is matched with :func:`fnmatch.fnmatchcase` (a literal name
matches itself).  This helper does not write ``os.environ``.  Live routes call it before
applying a caller-supplied env map.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Mapping, Sequence

from ..policy import PolicyDenied

__all__ = ["check_env"]

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ABX_PREFIX = "ABX_"


def check_env(updates: Mapping[str, str], *, deny: Sequence[str] = ()) -> dict[str, str]:
    """Admit ordinary ``KEY=VALUE`` pairs.

    ``ABX_*`` (any case) is always refused, and so is any name matching *deny*.

    Raises:
        ValueError: *deny* is not a sequence of non-empty strings.
        PolicyDenied: ``env_invalid`` (400) or ``env_var_denied``.
    """
    if isinstance(deny, (str, bytes)) or not isinstance(deny, Sequence):
        raise ValueError("deny must be a sequence of names")
    patterns = tuple(deny)
    if not all(isinstance(pat, str) and pat for pat in patterns):
        raise ValueError("deny must be a sequence of non-empty names")
    if not isinstance(updates, Mapping):
        raise PolicyDenied(
            "env_invalid",
            "Environment updates must be a mapping of KEY to VALUE",
            status=400,
            error_type="ValueError",
        )
    admitted: dict[str, str] = {}
    for name, value in updates.items():
        if (
            not isinstance(name, str)
            or _NAME.fullmatch(name) is None
            or not isinstance(value, str)
            or "\x00" in value
        ):
            raise PolicyDenied(
                "env_invalid",
                f"Invalid environment assignment {name!r}",
                status=400,
                error_type="ValueError",
            )
        if name.upper().startswith(_ABX_PREFIX) or any(
            fnmatch.fnmatchcase(name, pat) for pat in patterns
        ):
            raise PolicyDenied(
                "env_var_denied", f"Environment variable {name!r} cannot be overwritten"
            )
        admitted[name] = value
    return admitted
