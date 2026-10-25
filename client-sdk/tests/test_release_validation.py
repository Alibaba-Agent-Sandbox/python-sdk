"""Release guards reject a wrong tag or a different artifact under an existing filename."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_release", Path(__file__).resolve().parents[2] / "scripts/check_release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_candidate_tag_must_match_both_packages():
    version = release.release_version()
    release.validate_tag(f"v{version}", version)
    with pytest.raises(ValueError, match="Release must use tag"):
        release.validate_tag("main", version)
    with pytest.raises(ValueError, match="Release must use tag"):
        release.validate_tag("v999.0.0", version)


def test_existing_and_published_files_are_content_checked(tmp_path):
    wheel = tmp_path / "package.whl"
    wheel.write_bytes(b"candidate")
    remote = {
        "urls": [
            {
                "filename": wheel.name,
                "digests": {"sha256": hashlib.sha256(b"candidate").hexdigest()},
            }
        ]
    }
    release.verify_files([wheel], remote, required=True)
    release.verify_files([wheel], {"urls": []}, required=False)
    with pytest.raises(ValueError, match="missing"):
        release.verify_files([wheel], {"urls": []}, required=True)
    wheel.write_bytes(b"different")
    with pytest.raises(ValueError, match="differs"):
        release.verify_files([wheel], remote, required=False)


@pytest.mark.parametrize(
    "mode,status,expected",
    [("published", 404, 75), ("published", 500, None), ("preflight", 404, None)],
)
def test_only_published_metadata_not_found_is_retryable(monkeypatch, mode, status, expected):
    import sys
    from urllib.error import HTTPError

    def unavailable(*args, **kwargs):
        raise HTTPError("https://pypi.org/", status, "unavailable", {}, None)

    monkeypatch.setattr(sys, "argv", ["check_release.py", mode])
    monkeypatch.setattr(release, "public_artifacts", unavailable)
    if expected is None:
        with pytest.raises(HTTPError):
            release.main()
    else:
        with pytest.raises(SystemExit) as exc:
            release.main()
        assert exc.value.code == expected


def _run_public_workflow(tmp_path, metadata=0, install=0, check=0, probe=0):
    """Execute the maintained shell, replacing only its external commands."""
    import json
    import os
    import subprocess
    import textwrap

    import yaml

    workflow = yaml.safe_load((release.ROOT / ".github/workflows/publish.yml").read_text())
    shell = next(
        step["run"]
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Verify public PyPI files and fresh installation"
    )
    commands = tmp_path / "commands"
    commands.mkdir()
    executable = commands / "python"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        + textwrap.dedent("""\
        import json, os, pathlib, sys
        state_path = pathlib.Path(os.environ["RETRY_STATE"])
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        args = sys.argv[1:]
        if args[:2] == ["-m", "venv"]:
            target = pathlib.Path(args[2]) / "bin"
            target.mkdir(parents=True)
            (target / "python").symlink_to(pathlib.Path(__file__).resolve())
            sys.exit(0)
        if args[:1] == ["-c"] and "release_version" in args[1]:
            print("0.4.0a2")
            sys.exit(0)
        kind = ("metadata" if args == ["scripts/check_release.py", "published"] else
                "install" if args[:3] == ["-m", "pip", "install"] else
                "check" if args == ["-m", "pip", "check"] else "probe")
        state[kind] = state.get(kind, 0) + 1
        state_path.write_text(json.dumps(state))
        failures = int(os.environ[kind.upper() + "_FAILURES"])
        if state[kind] <= abs(failures):
            print(kind + " failure", file=sys.stderr)
            sys.exit(75 if kind == "metadata" and failures > 0 else 1)
    """)
    )
    executable.chmod(0o755)
    sleeper = commands / "sleep"
    sleeper.write_text("#!/bin/sh\nprintf 'sleep\\n' >> \"$RETRY_SLEEPS\"\n")
    sleeper.chmod(0o755)
    state_path = tmp_path / "state.json"
    sleeps_path = tmp_path / "sleeps"
    env = dict(
        os.environ,
        PATH=f"{commands}:/usr/bin:/bin",
        RUNNER_TEMP=str(tmp_path),
        RETRY_STATE=str(state_path),
        RETRY_SLEEPS=str(sleeps_path),
        METADATA_FAILURES=str(metadata),
        INSTALL_FAILURES=str(install),
        CHECK_FAILURES=str(check),
        PROBE_FAILURES=str(probe),
    )
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", shell],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    state = json.loads(state_path.read_text())
    sleeps = len(sleeps_path.read_text().splitlines()) if sleeps_path.exists() else 0
    return result, state, sleeps


def test_public_workflow_retries_propagation_then_checks_install_once(tmp_path):
    result, state, sleeps = _run_public_workflow(tmp_path, metadata=1, install=1)
    assert result.returncode == 0, result.stderr
    assert state == {"metadata": 2, "install": 2, "check": 1, "probe": 1}
    assert sleeps == 2
    assert "install failure" in result.stderr


@pytest.mark.parametrize(
    "options,expected,sleeps",
    [
        ({"metadata": -1}, {"metadata": 1}, 0),
        ({"metadata": 9}, {"metadata": 6}, 5),
        ({"install": 9}, {"metadata": 1, "install": 6}, 5),
        ({"check": 1}, {"metadata": 1, "install": 1, "check": 1}, 0),
        ({"probe": 1}, {"metadata": 1, "install": 1, "check": 1, "probe": 1}, 0),
    ],
)
def test_public_workflow_preserves_hard_failures_and_retry_bound(
    tmp_path, options, expected, sleeps
):
    result, state, actual_sleeps = _run_public_workflow(tmp_path, **options)
    assert result.returncode != 0
    assert state == expected
    assert actual_sleeps == sleeps
