"""Explicit command entrypoint for managed Gateway/Worker/Dispatcher containers."""

from __future__ import annotations

import argparse
import json
import os
import ssl
from pathlib import Path
from typing import Any

from .backend import ExpressBackend
from .dispatch import FCTaskSender, ManagedDispatcher
from .http import TokenAuthenticator, make_server
from .models import ManagedConfig
from .service import ManagedService
from .store import ManagedStore
from .worker import ManagedWorker


def load_document(name: str, *, required: bool = True) -> dict[str, Any] | None:
    """Load an explicit FILE or JSON document; never consult CWD/HOME configuration."""
    filename, raw = os.getenv(name + "_FILE"), os.getenv(name + "_JSON")
    if filename and raw:
        raise ValueError("Provide exactly one FILE or JSON managed configuration source")
    if not filename and not raw:
        if not required:
            return None
        raise ValueError("Required managed configuration was not supplied")
    data = json.loads(Path(filename).read_text() if filename else raw or "{}")
    if not isinstance(data, dict):
        raise ValueError("Managed configuration must be a JSON object")
    return data


def main() -> None:
    """Start only the explicitly requested role, with resolved service configuration."""
    parser = argparse.ArgumentParser(description="Durable Sandbox-hosted Agents API")
    parser.add_argument("mode", choices=("gateway", "worker", "dispatcher"))
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", default="0.0.0.0")  # nosec B104 - authenticated container ingress
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()
    ssl.create_default_context(cafile=os.getenv("ABX_MANAGED_TLS_CA_FILE"))
    compiled = load_document("ABX_MANAGED_CONFIG")
    assert compiled is not None
    config = ManagedConfig.from_dict(compiled)
    store = ManagedStore(
        os.environ["ABX_MANAGED_DATABASE_URL"], config.application_id, local=args.local
    )
    service = ManagedService(store, config)
    auth = None
    dispatcher = None
    token = os.getenv("ABX_MANAGED_INTERNAL_TOKEN", "")
    if args.mode == "gateway":
        auth = TokenAuthenticator(lambda: load_document("ABX_MANAGED_AUTH"))
        auth.source()  # fail readiness before binding a public socket
    else:
        provider = load_document("ABX_MANAGED_PROVIDER_CONFIG")
        model = load_document("ABX_MANAGED_MODEL_CONFIG", required=args.mode == "worker")
        assert provider is not None
        backend = ExpressBackend(provider, model)
        worker = ManagedWorker(service, backend)
        sender = None
        if args.mode == "dispatcher" and not args.local:
            sender = FCTaskSender(os.environ["ABX_MANAGED_FC_ENDPOINT"], config.workers, token)
        dispatcher = ManagedDispatcher(worker, sender)
    server = make_server(
        service,
        auth,
        mode=args.mode,
        dispatcher=dispatcher,
        internal_token=token,
        host=args.host,
        port=args.port,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
