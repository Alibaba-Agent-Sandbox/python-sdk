"""Migration helper for code written against the E2B Python SDK.

``agent_sandbox.Sandbox`` exposes E2B-shaped method names so that most
``e2b.Sandbox`` call sites port with an import change::

    from agent_sandbox.compat import Sandbox

This is a partial mapping, not a drop-in replacement: the wire protocol, the
authentication variables (``ABX_SANDBOX_API_KEY``) and several behaviours
differ.  See the "Migrate from E2B" guide for the full list.

=================================  ====================================
E2B SDK                            agent_sandbox
=================================  ====================================
``Sandbox.create()``               ``Sandbox.create()``
``Sandbox.connect(id)``            ``Sandbox.connect(id)``
``Sandbox.list()``                 ``Sandbox.list()``
``sandbox.kill()``                 ``sandbox.kill()``
``Sandbox.kill(id)``               ``Sandbox.kill_by_id(id)``
``sandbox.is_running()``           ``sandbox.is_running()``
``sandbox.pause()``                ``sandbox.pause()``
``sandbox.set_timeout(t)``         ``sandbox.set_timeout(t)``
``sandbox.commands.run(cmd)``      ``sandbox.commands.run(cmd)``
``sandbox.files.read(path)``       ``sandbox.files.read(path)``
``sandbox.files.write(path, d)``   ``sandbox.files.write(path, d)``
``sandbox.run_code(code)``         ``sandbox.run_code(code)``
``sandbox.get_host(port)``         ``sandbox.network.get_host(port)``
``sandbox.get_upload_url(path)``   raises ``FileOperationError`` [1]_
``sandbox.get_download_url(path)`` raises ``FileOperationError`` [1]_
=================================  ====================================

.. [1] The envd data plane requires ``X-Access-Token`` on ``/files`` and does
   not accept a signature-only URL.  Use ``files.write`` / ``files.read`` /
   ``files.upload`` / ``files.download``.
"""

from __future__ import annotations

from agent_sandbox.api.sandbox import Sandbox

E2BSandbox = Sandbox

__all__ = ["Sandbox", "E2BSandbox"]
