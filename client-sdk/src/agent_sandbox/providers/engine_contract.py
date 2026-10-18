"""Backend session contract for the provider engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Session:
    """Backend connections for one sandbox. Tokens stay in this process."""

    sandbox_id: str
    provider: str
    envd_url: str
    token: Any
    http: Any
    process: Any
    files: Any
    sandbox_protocol: Any
    terminal: Any = None
