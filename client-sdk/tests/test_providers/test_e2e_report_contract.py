"""The cloud harness must reject acceptance checks that never executed."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def live(monkeypatch):
    source = Path(__file__).resolve().parents[3] / "e2e" / "provider_live.py"
    if not source.is_file():
        pytest.skip("cloud harness source is not included in this checkout")
    spec = importlib.util.spec_from_file_location("_sdk_e2e_report_contract", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Normal module registration is required by the dataclass decorator.
    monkeypatch.setitem(sys.modules, spec.name, module)
    # Import selects a per-process socket. Preserve this unit run's environment.
    with patch.dict(os.environ):
        spec.loader.exec_module(module)
    return module


def test_empty_report_rejects_unexecuted_expected_features(live):
    report = live.Report("fake")
    with pytest.raises(AssertionError, match="sandbox.lifecycle was not executed"):
        live.assert_report(report, expect_pass={"sandbox.lifecycle"}, expect_refused=set())


def test_unrelated_blocked_row_cannot_satisfy_cli_acceptance(live):
    report = live.Report("fake")
    report.add("cli", "blocked", "not installed")
    with pytest.raises(AssertionError, match="exec.run was not executed"):
        live.assert_report(report, expect_pass={"exec.run"}, expect_refused=set())


def test_partial_report_must_include_expected_refusal(live):
    report = live.Report("fake")
    report.add("sandbox.lifecycle", "pass", "executed")
    with pytest.raises(AssertionError, match="pty was not executed"):
        live.assert_report(report, expect_pass={"sandbox.lifecycle"}, expect_refused={"pty"})


@pytest.mark.parametrize("status", ["fail", "blocked", "refused"])
def test_recorded_wrong_result_still_fails(live, status):
    report = live.Report("fake")
    report.add("exec.run", status, "executed")
    with pytest.raises(AssertionError, match="exec.run"):
        live.assert_report(report, expect_pass={"exec.run"}, expect_refused=set())


def test_complete_correct_report_passes(live):
    report = live.Report("fake")
    report.add("sandbox.lifecycle", "pass", "executed")
    report.add("pty", "refused", "E8004")
    live.assert_report(report, expect_pass={"sandbox.lifecycle"}, expect_refused={"pty"})


def test_cli_override_accepts_arguments_and_quoted_paths(live, monkeypatch):
    monkeypatch.setenv("ABX_BIN", 'node "/a CLI path/abx.js"')
    monkeypatch.setattr(live.shutil, "which", lambda _name: pytest.fail("override has priority"))
    assert live.cli_command() == ["node", "/a CLI path/abx.js"]


def test_cli_discovery_uses_path(live, monkeypatch):
    monkeypatch.delenv("ABX_BIN", raising=False)
    monkeypatch.setattr(live.shutil, "which", lambda name: "/tools/abx" if name == "abx" else None)
    assert live.cli_command() == ["/tools/abx"]


def test_missing_cli_has_no_invented_sibling_fallback(live, monkeypatch):
    monkeypatch.delenv("ABX_BIN", raising=False)
    monkeypatch.setattr(live.shutil, "which", lambda _name: None)
    assert live.cli_command() == []


def test_cube_requires_explicit_backend_even_when_default_port_is_open(live, monkeypatch):
    monkeypatch.setattr(live, "_installed", lambda _provider: "")
    monkeypatch.delenv("ABX_CUBESANDBOX_BASE_URL", raising=False)
    monkeypatch.setattr(
        live, "_tcp", lambda *_args: pytest.fail("must not probe unrelated service")
    )
    assert "ABX_CUBESANDBOX_BASE_URL is not set" in live.cube_ready()


def test_cube_probes_explicit_endpoint_instead_of_a_fixed_port(live, monkeypatch):
    monkeypatch.setattr(live, "_installed", lambda _provider: "")
    monkeypatch.setenv("ABX_CUBESANDBOX_BASE_URL", "https://cube.example.invalid:8443")
    calls = []
    monkeypatch.setattr(live, "_tcp", lambda host, port: calls.append((host, port)) or True)
    assert live.cube_ready() == ""
    assert calls == [("cube.example.invalid", 8443)]


@pytest.mark.parametrize(
    "value", ["not-an-origin", "https://cube.example.invalid:wrong", "ftp://host"]
)
def test_invalid_cube_endpoint_does_not_trigger_a_probe(live, monkeypatch, value):
    monkeypatch.setattr(live, "_installed", lambda _provider: "")
    monkeypatch.setenv("ABX_CUBESANDBOX_BASE_URL", value)
    monkeypatch.setattr(
        live, "_tcp", lambda *_args: pytest.fail("invalid origin must not be probed")
    )
    assert "not a valid HTTP(S) origin" in live.cube_ready()
