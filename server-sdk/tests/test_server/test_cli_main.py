"""``agent-sandbox-server`` command line."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from agent_sandbox.server import __version__
from agent_sandbox.server.__main__ import _load_commands, main

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ._live import Live


@pytest.fixture(autouse=True)
def _restore_command_import_state() -> Iterator[None]:
    modules_before = set(sys.modules)
    path_before = sys.path[:]
    yield
    for name in set(sys.modules) - modules_before:
        if name.startswith("_abx_user_commands_") or name == "abx_cmds_mod":
            sys.modules.pop(name, None)
    sys.path[:] = path_before


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
    monkeypatch.delenv("ABX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("ABX_SERVER_POLICY_FILE", raising=False)
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
    monkeypatch.delenv("ABX_SERVER_POLICY", raising=False)
    monkeypatch.delenv("ABX_SERVER_POLICY_FILE", raising=False)
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
    mod = tmp_path / "abx_cmds_mod.py"
    mod.write_text("LOADED = True\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _load_commands("abx_cmds_mod")
    assert "abx_cmds_mod" in sys.modules


def test_load_commands_dataclass_resolves_postponed_annotations(tmp_path: Path) -> None:
    script = tmp_path / "commands.py"
    script.write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass, fields\n"
        "from typing import ClassVar\n"
        "import sys\n"
        "assert sys.modules[__name__].__dict__ is globals()\n"
        "@dataclass\n"
        "class Settings:\n"
        "    label: ClassVar[str] = 'commands'\n"
        "    count: int = 1\n"
        "assert [field.name for field in fields(Settings)] == ['count']\n"
    )
    _load_commands(str(script))
    loaded = next(
        module
        for module in sys.modules.values()
        if getattr(module, "__file__", None) == str(script)
    )
    assert loaded.Settings().count == 1


def test_load_commands_same_file_runs_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = tmp_path / "commands.py"
    marker = tmp_path / "registrations.txt"
    script.write_text(
        "from pathlib import Path\n"
        f"with Path({str(marker)!r}).open('a') as stream:\n"
        "    stream.write('registered\\n')\n"
    )
    monkeypatch.chdir(tmp_path)
    path_before = sys.path[:]
    _load_commands("commands.py")
    module_before = next(
        module
        for module in sys.modules.values()
        if getattr(module, "__file__", None) == str(script)
    )
    _load_commands(str(script))
    alias = tmp_path / "alias.py"
    alias.symlink_to(script)
    _load_commands(str(alias))
    assert marker.read_text() == "registered\n"
    assert sys.modules[module_before.__name__] is module_before
    assert sys.path.count(str(tmp_path)) == max(1, path_before.count(str(tmp_path)))


@pytest.mark.parametrize("failure", ["RuntimeError('bad commands')", "SystemExit(7)"])
def test_load_commands_failure_cleans_module_and_allows_retry(tmp_path: Path, failure: str) -> None:
    script = tmp_path / "commands.py"
    script.write_text(f"raise {failure}\n")
    modules_before = set(sys.modules)
    path_before = sys.path[:]
    with pytest.raises((RuntimeError, SystemExit)):
        _load_commands(str(script))
    assert not {
        name for name in set(sys.modules) - modules_before if name.startswith("_abx_user_commands_")
    }
    assert sys.path == path_before
    script.write_text("LOADED_AFTER_REPAIR = True\n")
    _load_commands(str(script))
    loaded = next(
        module
        for module in sys.modules.values()
        if getattr(module, "__file__", None) == str(script)
    )
    assert loaded.LOADED_AFTER_REPAIR is True


def test_load_commands_same_basename_keeps_distinct_modules(tmp_path: Path) -> None:
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        script = directory / "commands.py"
        script.write_text(f"SOURCE = {name!r}\n")
        _load_commands(str(script))
    loaded = {
        module.SOURCE
        for module in sys.modules.values()
        if getattr(module, "__file__", "")
        in {
            str(tmp_path / "first" / "commands.py"),
            str(tmp_path / "second" / "commands.py"),
        }
    }
    assert loaded == {"first", "second"}


def test_policy_modules_are_stdlib_only() -> None:
    import ast

    import agent_sandbox.server as pkg

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
                assert top in stdlib or top == "agent_sandbox" or optional, f"{name}.py: {module}"
