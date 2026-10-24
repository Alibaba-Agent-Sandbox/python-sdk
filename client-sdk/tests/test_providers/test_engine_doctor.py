"""Actual Python doctor -> local Node engine initialization; no cloud requests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from agent_sandbox.providers import doctor, installer
from tests.test_providers.test_engine_provider import engine_env, iso, pytestmark  # noqa: F401

if TYPE_CHECKING:
    from pathlib import Path


def _plugin(root: Path, source: str) -> None:
    root.mkdir()
    (root / "abx-provider.toml").write_text("""manifest_version = 1
operation_contract_version = 1
[operations]
cli = []
python = []
[workflow]
inputs = []
startups = []
[provider]
id = "doctor-node"
name = "Doctor fixture"
version = "1.0.0"
[compat]
protocol = "node/1"
[runtime]
kind = "node"
entry = "provider.mjs"
[features]
supported = []
""")
    (root / "provider.mjs").write_text(source)
    installer.install(str(root), yes=True)


@pytest.mark.parametrize("valid", [True, False])
def test_doctor_initializes_real_node_plugin(engine_env, tmp_path, valid):  # noqa: F811
    marker = tmp_path / "closed"
    source = """import fs from 'node:fs';
export default () => ({ buildInfra: async () => ({
  operation_contract_version: 1, operations: {cli: [], python: []},
  sandbox_protocol: {
    create: () => { throw Error('doctor must not create'); },
    list: () => { throw Error('doctor must not list'); }
  },
  close: async () => fs.writeFileSync(MARKER, 'closed')
}) });""".replace("MARKER", json.dumps(str(marker)))
    _plugin(tmp_path / "plugin", source if valid else "invalid JavaScript !")
    report = doctor.doctor("doctor-node")
    assert report["ok"] is valid, report
    assert report["checks"][-1]["name"] == "handshake"
    assert marker.exists() is valid
