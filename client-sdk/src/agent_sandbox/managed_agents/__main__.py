"""Explicit command entrypoint for managed Gateway/Worker/Dispatcher containers."""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import json
import os
import re
import ssl
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .backend import ExpressBackend
from .dispatch import FCTaskSender, ManagedDispatcher
from .http import TokenAuthenticator, make_server
from .models import ManagedConfig
from .service import ManagedService
from .store import ManagedStore
from .worker import ManagedWorker

if TYPE_CHECKING:
    from collections.abc import Iterator


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
    parser.add_argument("--database-ca-base64", nargs="+", metavar="BASE64_PEM")
    args = parser.parse_args()
    pem = os.getenv("ABX_MANAGED_DATABASE_CA_PEM")
    if args.database_ca_base64 is not None:
        if pem is not None:
            parser.error("Provide database CA through exactly one argument or environment source")
        try:
            pem = decode_database_ca(args.database_ca_base64)
        except argparse.ArgumentTypeError as error:
            parser.error(str(error))
    ssl.create_default_context(cafile=os.getenv("ABX_MANAGED_TLS_CA_FILE"))
    with database_ca_file(pem) as ca_file:
        serve(args, ca_file)


def decode_database_ca(parts: list[str]) -> str:
    """Decode bounded public CA material without reflecting argument values in errors."""
    try:
        if (
            not parts
            or any(not part for part in parts)
            or sum(map(len, parts)) > 4 * ((65536 + 2) // 3)
        ):
            raise ValueError
        encoded = "".join(parts).encode("ascii")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 65536 or base64.b64encode(raw) != encoded:
            raise ValueError
        return raw.decode("ascii")
    except (ValueError, UnicodeError, binascii.Error):
        raise argparse.ArgumentTypeError(
            "Database CA must be canonical Base64 of at most 64 KiB ASCII PEM"
        ) from None


@contextlib.contextmanager
def database_ca_file(pem: str | None) -> Iterator[str | None]:
    """Materialize a bounded CA-only bundle privately for libpq, never in guest config."""
    if pem is None:
        yield None
        return
    pattern = re.compile(r"-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----")
    certificates = pattern.findall(pem)
    if len(pem.encode()) > 65536 or not 1 <= len(certificates) <= 8 or pattern.sub("", pem).strip():
        raise ValueError("Database CA must contain only 1-8 PEM certificates within 64 KiB")
    try:
        ssl.create_default_context().load_verify_locations(cadata=pem)
    except ssl.SSLError:
        raise ValueError("Database CA certificates are invalid") from None
    with tempfile.TemporaryDirectory(prefix="abx-managed-database-ca-") as directory:
        path = os.path.join(directory, "ca.pem")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(pem)
        yield path


def serve(args: argparse.Namespace, ca_file: str | None) -> None:
    """Serve one role while its explicit database trust material remains alive."""
    compiled = load_document("ABX_MANAGED_CONFIG")
    assert compiled is not None
    config = ManagedConfig.from_dict(compiled)
    store = ManagedStore(
        os.environ["ABX_MANAGED_DATABASE_URL"],
        config.application_id,
        local=args.local,
        expected_state_id=config.expected_state_id,
        database_ca_file=ca_file,
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
