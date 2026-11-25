"""Verify actual HTTP Python package inventory in an environment without pip.

Install the server with uv into a fresh virtual environment, then run this file
with that interpreter. Uses one local listener and no cloud resources.
"""

import http.client
import importlib.util
import json
import os
import secrets
import threading
import time

from agent_sandbox.server.app import SandboxServer

assert importlib.util.find_spec("pip") is None
os.environ["ABX_SERVER_TOKEN"] = secrets.token_hex(32)
server = SandboxServer(host="127.0.0.1", pty_port=0)
thread = threading.Thread(target=server.serve, args=(0,), daemon=True)
thread.start()
try:
    deadline = time.monotonic() + 5
    while server._httpd is None:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    connection = http.client.HTTPConnection("127.0.0.1", server._httpd.server_port, timeout=5)
    connection.request(
        "GET",
        "/packages?manager=pip",
        headers={"Authorization": "Bearer " + os.environ["ABX_SERVER_TOKEN"]},
    )
    response = connection.getresponse()
    body = json.loads(response.read())
    connection.close()
    assert response.status == 200
    names = {item["name"].lower() for item in body["packages"]}
    assert "agent-sandbox-server" in names and "websockets" in names
    print(
        json.dumps(
            {
                "pip_installed": False,
                "http_status": response.status,
                "server_listed": True,
                "dependency_listed": True,
            }
        )
    )
finally:
    server.shutdown()
    thread.join(5)
    assert not thread.is_alive()
