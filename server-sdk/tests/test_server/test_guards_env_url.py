"""Unit tests for the env, URL and process guards.

HTTP coverage of the same checks is in ``test_guards_live_routes.py``.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

from agent_sandbox.server.guards import check_env, check_process, check_url
from agent_sandbox.server.policy import PolicyDenied

if TYPE_CHECKING:
    from pathlib import Path


def code_of(fn: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(PolicyDenied) as exc:
        fn(*args, **kwargs)  # type: ignore[operator]
    return exc.value.code


class TestEnvGuard:
    def test_ordinary_assignment_is_admitted(self) -> None:
        assert check_env({"FOO": "bar", "COUNT": "1"}) == {"FOO": "bar", "COUNT": "1"}

    def test_abx_overwrite_is_denied(self) -> None:
        assert code_of(check_env, {"ABX_SERVER_TOKEN": "x"}) == "env_var_denied"
        assert code_of(check_env, {"abx_secret": "x"}) == "env_var_denied"

    def test_caller_deny_list_blocks_only_listed_names(self) -> None:
        assert code_of(check_env, {"SECRET": "x"}, deny=["SECRET", "TOKEN"]) == "env_var_denied"
        assert check_env({"FOO": "bar"}, deny=["SECRET"]) == {"FOO": "bar"}
        assert code_of(check_env, {"ABX_FLAG": "1"}, deny=["OTHER"]) == "env_var_denied"


class TestUrlGuard:
    @pytest.mark.parametrize(
        "url",
        [
            "https://127.0.0.1/",
            "http://[::1]/",
            "https://localhost/admin",
            "https://169.254.169.254/latest",
            "https://[fe80::1]/",
            "https://10.0.0.5/",
            "https://192.168.1.20/",
            "https://172.16.0.1/",
            "https://[::ffff:127.0.0.1]/",
        ],
    )
    def test_loopback_link_local_and_private_are_denied(self, url: str) -> None:
        assert code_of(check_url, url) == "url_denied"

    def test_public_https_url_is_admitted(self) -> None:
        assert check_url("https://example.com/path") == "https://example.com/path"
        assert check_url("https://1.1.1.1/") == "https://1.1.1.1/"

    def test_allow_private_flips_the_denial(self) -> None:
        assert check_url("https://10.0.0.5/", allow_private=True) == "https://10.0.0.5/"
        assert check_url("https://127.0.0.1/", allow_private=True) == "https://127.0.0.1/"
        assert check_url("https://169.254.169.254/", allow_private=True) == (
            "https://169.254.169.254/"
        )
        assert check_url("https://example.com/", allow_private=True) == "https://example.com/"


class TestProcessGuard:
    def test_ordinary_executable_is_admitted(self) -> None:
        resolved = shutil.which("true")
        assert resolved is not None
        assert check_process(["true"]) == ["true"]
        assert check_process(["/bin/true", "ignored"]) == ["/bin/true", "ignored"]
        assert os.path.realpath(resolved).startswith("/usr/")

    @pytest.mark.parametrize("exe", ["/proc/self/exe", "/sys/kernel", "/dev/null"])
    def test_system_executable_is_refused(self, exe: str) -> None:
        assert code_of(check_process, [exe]) == "process_denied"

    def test_symlink_that_resolves_under_dev_is_refused(self, tmp_path: Path) -> None:
        link = tmp_path / "via-dev"
        link.symlink_to("/dev/null")
        assert code_of(check_process, [str(link)]) == "process_denied"
