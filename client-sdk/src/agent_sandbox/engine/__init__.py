"""Local provider engine.

SDKs talk to this process over a Unix socket with gRPC. The engine is the
only place that opens backend HTTP, SSE and WebSocket connections. The
built-in Alibaba Cloud provider goes through ``Create`` as well.
"""

from agent_sandbox.engine.client import Engine

__all__ = ["Engine"]
