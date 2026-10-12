"""The shared Provider contract kit, pointed at the installed ``opensandbox`` plugin."""

from __future__ import annotations

from easy_sandbox.providers.testing import ProviderContractTests


class TestOpenSandboxContract(ProviderContractTests):
    provider_id = "opensandbox"
