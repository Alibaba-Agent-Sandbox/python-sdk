"""Ready-made, collectable contract suite: ``pytest --pyargs agent_sandbox.providers.contract``.

Select the provider with ``--provider-under-test`` (registered by loading
``agent_sandbox.providers.testing`` as a pytest plugin, ``-p``)::

    pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract \
           --provider-under-test my-provider

Prefer ``python -m agent_sandbox.providers test my-provider``, which wires all of this up and fails
when nothing was collected.
"""

from __future__ import annotations

from agent_sandbox.providers.testing import ProviderContractTests


class TestProviderContract(ProviderContractTests):
    """Runs every applicable contract test against ``--provider-under-test``."""
