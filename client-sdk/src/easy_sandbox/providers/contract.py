"""Ready-made, collectable contract suite: ``pytest --pyargs easy_sandbox.providers.contract``.

Select the provider with ``--provider-under-test`` (registered by loading
``easy_sandbox.providers.testing`` as a pytest plugin, ``-p``)::

    pytest -p easy_sandbox.providers.testing --pyargs easy_sandbox.providers.contract \
           --provider-under-test my-provider

Prefer ``python -m easy_sandbox.providers test my-provider``, which wires all of this up and fails
when nothing was collected.
"""

from __future__ import annotations

from easy_sandbox.providers.testing import ProviderContractTests


class TestProviderContract(ProviderContractTests):
    """Runs every applicable contract test against ``--provider-under-test``."""
