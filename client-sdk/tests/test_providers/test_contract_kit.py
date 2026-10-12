"""The documented ways of running the provider contract kit really collect and run tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from easy_sandbox.providers import testing
from tests.test_providers.helpers import LOCAL_PROCESS


def _env(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EBX_", "E2B_", "SANDBOX_"))}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return env


def _cli(home, *args, timeout=240):
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "easy_sandbox.providers", *args],
        cwd=home,
        env=_env(home),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@pytest.fixture(scope="module")
def installed_home(tmp_path_factory):
    home = tmp_path_factory.mktemp("kit-home")
    done = _cli(home, "install", str(LOCAL_PROCESS), "--yes")
    assert done.returncode == 0, done.stderr
    return home


def _counts(output: str) -> dict[str, int]:
    return {word: int(n) for n, word in re.findall(r"(\d+) (passed|failed|skipped|error)", output)}


def test_python_m_test_command_runs_the_kit(installed_home):
    res = _cli(installed_home, "test", "local-process")
    counts = _counts(res.stdout)
    assert res.returncode == 0, res.stdout + res.stderr
    assert counts.get("passed", 0) >= 12, res.stdout
    assert "failed" not in counts


def test_documented_pytest_command_collects_tests(installed_home):
    res = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "easy_sandbox.providers.testing",
            "--pyargs",
            "easy_sandbox.providers.contract",
            "--provider-under-test",
            "local-process",
            "-c",
            os.devnull,
            "--rootdir",
            str(installed_home),
            "-p",
            "no:cacheprovider",
            "-o",
            "asyncio_mode=auto",
        ],
        cwd=installed_home,
        env=_env(installed_home),
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    counts = _counts(res.stdout)
    assert res.returncode == 0, res.stdout + res.stderr
    assert counts.get("passed", 0) >= 12, res.stdout


def test_missing_provider_selection_fails_instead_of_skipping(installed_home):
    res = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "easy_sandbox.providers.testing",
            "--pyargs",
            "easy_sandbox.providers.contract",
            "-c",
            os.devnull,
            "--rootdir",
            str(installed_home),
            "-p",
            "no:cacheprovider",
            "-x",
            "-q",
        ],
        cwd=installed_home,
        env=_env(installed_home),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert res.returncode != 0
    assert "no provider selected" in res.stdout


def test_test_command_rejects_unknown_provider(installed_home):
    res = _cli(installed_home, "test", "nope-provider")
    assert res.returncode != 0


def test_parse_options():
    assert testing.parse_options(["a=1", "b=x=y"]) == {"a": "1", "b": "x=y"}
    with pytest.raises(pytest.UsageError):
        testing.parse_options(["novalue"])
