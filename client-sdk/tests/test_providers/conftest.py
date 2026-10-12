from __future__ import annotations

import pytest

from easy_sandbox.providers import installer
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import LOCAL_PROCESS


@pytest.fixture
def local_process(iso):  # noqa: F811
    """The reference ``local-process`` plugin installed into the isolated store."""
    installer.install(str(LOCAL_PROCESS), yes=True)
    return iso
