"""Actual managed command parsing preserves bounded database trust material."""

from __future__ import annotations

import base64
import os
import ssl
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from agent_sandbox.managed_agents import __main__ as entrypoint


@pytest.fixture
def ca_pem() -> str:
    certificates = ssl.create_default_context().get_ca_certs(binary_form=True)
    assert certificates, "The actual CA-validation regression needs the system trust store"
    return ssl.DER_cert_to_PEM_cert(certificates[0])


def run_main(monkeypatch: Any, args: list[str], callback: Any = None) -> None:
    monkeypatch.setattr(sys, "argv", ["managed-agents", *args])
    monkeypatch.setattr(entrypoint, "serve", callback or (lambda *_: pytest.fail("serve called")))
    entrypoint.main()


@pytest.mark.parametrize("mode", ["gateway", "worker", "dispatcher"])
def test_base64_ca_main_validates_materializes_and_removes(
    monkeypatch: Any, ca_pem: str, mode: str
) -> None:
    monkeypatch.delenv("ABX_MANAGED_DATABASE_CA_PEM", raising=False)
    paths: list[Path] = []

    def serve(args: Any, ca_file: str | None) -> None:
        assert args.mode == mode
        assert ca_file is not None
        path = Path(ca_file)
        assert path.read_text() == ca_pem
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        paths.append(path)

    encoded = base64.b64encode(ca_pem.encode("ascii")).decode("ascii")
    run_main(monkeypatch, [mode, "--database-ca-base64", encoded], serve)
    assert paths and not paths[0].exists() and not paths[0].parent.exists()


@pytest.mark.parametrize("environment", ["", "other CA source"])
def test_base64_ca_main_rejects_conflicting_environment(
    monkeypatch: Any, capsys: Any, ca_pem: str, environment: str
) -> None:
    monkeypatch.setenv("ABX_MANAGED_DATABASE_CA_PEM", environment)
    encoded = base64.b64encode(ca_pem.encode("ascii")).decode("ascii")
    with pytest.raises(SystemExit) as error:
        run_main(monkeypatch, ["gateway", "--database-ca-base64", encoded])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "exactly one argument or environment source" in output
    assert encoded not in output
    if environment:
        assert environment not in output


@pytest.mark.parametrize(
    "invalid",
    ["not_base64!", "é", "QUJD====", base64.b64encode(b"\xff").decode("ascii")],
)
def test_base64_ca_main_rejects_invalid_encoding_without_echo(
    monkeypatch: Any, capsys: Any, invalid: str
) -> None:
    monkeypatch.delenv("ABX_MANAGED_DATABASE_CA_PEM", raising=False)
    with pytest.raises(SystemExit) as error:
        run_main(monkeypatch, ["worker", "--database-ca-base64", invalid])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "canonical Base64" in output and invalid not in output


@pytest.mark.parametrize("raw", [b"x" * 65537, b"x" * 100000])
def test_base64_ca_main_rejects_oversize_before_serve(
    monkeypatch: Any, capsys: Any, raw: bytes
) -> None:
    monkeypatch.delenv("ABX_MANAGED_DATABASE_CA_PEM", raising=False)
    encoded = base64.b64encode(raw).decode("ascii")
    with pytest.raises(SystemExit) as error:
        run_main(monkeypatch, ["dispatcher", "--database-ca-base64", encoded])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "64 KiB ASCII PEM" in output and encoded not in output


@pytest.mark.parametrize(
    "invalid_pem",
    [
        "not a certificate",
        "-----BEGIN PUBLIC KEY-----\nQQ==\n-----END PUBLIC KEY-----",
        "-----BEGIN CERTIFICATE-----\nQQ==\n-----END CERTIFICATE-----",
    ],
)
def test_base64_ca_main_still_requires_valid_certificate(
    monkeypatch: Any, invalid_pem: str
) -> None:
    monkeypatch.delenv("ABX_MANAGED_DATABASE_CA_PEM", raising=False)
    encoded = base64.b64encode(invalid_pem.encode("ascii")).decode("ascii")
    with pytest.raises(ValueError, match="Database CA"):
        run_main(monkeypatch, ["gateway", "--database-ca-base64", encoded])


def test_existing_environment_ca_main_remains_supported(monkeypatch: Any, ca_pem: str) -> None:
    monkeypatch.setenv("ABX_MANAGED_DATABASE_CA_PEM", ca_pem)
    paths: list[Path] = []

    def serve(args: Any, ca_file: str | None) -> None:
        assert ca_file is not None and Path(ca_file).read_text() == ca_pem
        paths.append(Path(ca_file))

    run_main(monkeypatch, ["gateway"], serve)
    assert not paths[0].exists()
    assert os.environ["ABX_MANAGED_DATABASE_CA_PEM"] == ca_pem


def test_base64_ca_main_removes_file_after_startup_failure(monkeypatch: Any, ca_pem: str) -> None:
    monkeypatch.delenv("ABX_MANAGED_DATABASE_CA_PEM", raising=False)
    paths: list[Path] = []

    def serve(args: Any, ca_file: str | None) -> None:
        assert ca_file is not None
        paths.append(Path(ca_file))
        raise RuntimeError("example startup failure")

    encoded = base64.b64encode(ca_pem.encode("ascii")).decode("ascii")
    with pytest.raises(RuntimeError, match="example startup failure"):
        run_main(monkeypatch, ["worker", "--database-ca-base64", encoded], serve)
    assert not paths[0].exists() and not paths[0].parent.exists()
