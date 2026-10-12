"""``easy-sandbox-server`` command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from easy_sandbox.server import __version__
from easy_sandbox.server.__main__ import _load_commands, main

if TYPE_CHECKING:
    import pytest

    from ._live import Live


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_healthcheck_ok_and_down(live_server: Any) -> None:
    live: Live = live_server()
    assert main(["healthcheck", "--port", str(live.port)]) == 0
    live.close()
    assert main(["healthcheck", "--port", str(live.port), "--timeout", "0.5"]) == 1


def test_check_config_json_lists_endpoints(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EBX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("EBX_SERVER_POLICY_FILE", raising=False)
    assert main(["check-config", "--preset", "transfer-only", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    enabled = {row["endpoint"] for row in doc["endpoints"] if row["enabled"]}
    assert {"upload", "download"} <= enabled
    assert "shell" not in enabled


def test_check_config_invalid_policy_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "p.json"
    bad.write_text(json.dumps({"endpoints": {"uplaod": {"enabled": True}}}))
    bad.chmod(0o444)
    assert main(["check-config", "--policy", str(bad)]) == 1
    assert "upload" in capsys.readouterr().err


def test_check_config_explain_exit_codes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EBX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("EBX_SERVER_POLICY_FILE", raising=False)
    assert main(["check-config", "--preset", "transfer-only", "--explain", "shell"]) == 3
    assert json.loads(capsys.readouterr().out)["allowed"] is False
    assert main(["check-config", "--preset", "transfer-only", "--explain", "upload"]) == 0


def test_check_config_strict_fails_on_lint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = tmp_path / "p.json"
    policy.write_text(json.dumps({"endpoints": {"shell": {"enabled": True}}}))
    assert main(["check-config", "--policy", str(policy), "--strict"]) == 2
    assert "warning" in capsys.readouterr().out


def test_load_commands_from_file_and_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "marker.txt"
    script = tmp_path / "my_cmds.py"
    script.write_text(f"open({str(marker)!r}, 'w').write('loaded')\n")
    _load_commands(str(script))
    assert marker.read_text() == "loaded"
    mod = tmp_path / "ebx_cmds_mod.py"
    mod.write_text("LOADED = True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _load_commands("ebx_cmds_mod")
    assert "ebx_cmds_mod" in sys.modules


def test_policy_modules_are_stdlib_only() -> None:
    import ast

    import easy_sandbox.server as pkg

    stdlib = set(sys.stdlib_module_names)
    for name in ("policy", "guard", "runtime", "contract", "__main__"):
        path = Path(pkg.__file__).parent / f"{name}.py"
        for node in ast.walk(ast.parse(path.read_text())):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                optional = top == "yaml"  # lazily imported for *.yaml policy files only
                assert top in stdlib or top == "easy_sandbox" or optional, f"{name}.py: {module}"
