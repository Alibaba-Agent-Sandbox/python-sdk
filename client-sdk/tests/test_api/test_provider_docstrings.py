"""Keep ProviderSandbox lifecycle help aligned with its callable parameters."""

import inspect
import re

import pytest

from agent_sandbox import ProviderSandbox


@pytest.mark.parametrize(
    "method_name",
    [
        name + suffix
        for name in (
            "create",
            "connect",
            "list",
            "kill_by_id",
            "get_info_by_id",
            "set_timeout_by_id",
        )
        for suffix in ("", "_sync")
    ],
)
def test_lifecycle_docstrings_match_signatures(method_name: str) -> None:
    method = getattr(ProviderSandbox, method_name)
    doc = inspect.getdoc(method) or ""
    documented_parameters = set(re.findall(r"^    ([a-z_]+):", doc, re.MULTILINE))
    assert documented_parameters <= inspect.signature(method).parameters.keys()
    assert not re.search(r"\*(?:api_key|api_url)\*", doc)
