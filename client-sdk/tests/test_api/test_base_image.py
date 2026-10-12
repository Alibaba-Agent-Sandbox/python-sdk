"""Base-image contract: references, lint, scaffold, Image/DockerBuilder integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from easy_sandbox import __version__
from easy_sandbox.api.base_image import (
    DEFAULT_BASE_TAG,
    DEFAULT_REGION,
    SERVER_READY_CMD,
    SERVER_START_CMD,
    BaseImageContract,
    is_official_base_image,
    lint_dockerfile,
    official_base_image,
    scaffold_dockerfile,
    warn_on_dockerfile,
)
from easy_sandbox.api.docker_builder import DockerBuilder
from easy_sandbox.api.image import Image

if TYPE_CHECKING:
    from pathlib import Path

OFFICIAL = f"fc-e2b-registry.{DEFAULT_REGION}.cr.aliyuncs.com/runtime/base:{DEFAULT_BASE_TAG}"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EBX_BASE_IMAGE_TAG", raising=False)
    monkeypatch.delenv("EBX_BASE_IMAGE_REGION", raising=False)


class TestReference:
    def test_default_reference(self) -> None:
        assert official_base_image() == OFFICIAL

    def test_overrides(self) -> None:
        ref = official_base_image(region="cn-shanghai", variant="browser", tag="v1.2.3")
        assert ref == "fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/runtime/browser:v1.2.3"

    def test_environment_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EBX_BASE_IMAGE_TAG", "v9")
        monkeypatch.setenv("EBX_BASE_IMAGE_REGION", "cn-beijing")
        assert official_base_image() == (
            "fc-e2b-registry.cn-beijing.cr.aliyuncs.com/runtime/base:v9"
        )

    def test_explicit_argument_beats_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EBX_BASE_IMAGE_TAG", "v9")
        assert official_base_image(tag="v1").endswith(":v1")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"region": "evil.com/x"},
            {"variant": "a/b"},
            {"variant": "../x"},
            {"tag": "v1 --privileged"},
            {"tag": "a:b"},
            {"region": "UPPER"},
        ],
    )
    def test_malformed_parts_are_rejected(self, kwargs: dict[str, str]) -> None:
        with pytest.raises(ValueError):
            official_base_image(**kwargs)

    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            (OFFICIAL, True),
            (OFFICIAL + "@sha256:abc", True),
            ("fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/runtime/claude-code:v1", True),
            ("ubuntu:22.04", False),
            ("python:3.12", False),
            ("fc-e2b-registry.cn-hangzhou.cr.aliyuncs.com/other/base:v1", False),
            ("evil.com/fc-e2b-registry.cn-hangzhou.cr.aliyuncs.com/runtime/base:v1", False),
            ("fc-e2b-registry.cn-hangzhou.cr.aliyuncs.com.evil.io/runtime/base:v1", False),
        ],
    )
    def test_is_official(self, ref: str, expected: bool) -> None:
        assert is_official_base_image(ref) is expected


class TestLint:
    def codes(self, text: str) -> list[str]:
        return [i.code for i in lint_dockerfile(text)]

    def test_official_base_is_clean(self) -> None:
        assert self.codes(f"FROM {OFFICIAL}\nRUN true\n") == []

    def test_b001_foreign_base(self) -> None:
        assert self.codes("FROM ubuntu:22.04\n") == ["B001"]

    def test_b001_only_the_last_stage_counts(self) -> None:
        text = f"FROM golang:1.22 AS build\nRUN true\nFROM {OFFICIAL}\nCOPY --from=build /a /a\n"
        assert self.codes(text) == []

    def test_b001_stage_reference_is_not_flagged(self) -> None:
        text = f"FROM {OFFICIAL} AS base\nFROM base\n"
        assert self.codes(text) == []

    def test_b001_platform_flag_is_skipped(self) -> None:
        assert self.codes(f"FROM --platform=linux/amd64 {OFFICIAL}\n") == []

    def test_b002_entrypoint(self) -> None:
        assert self.codes(f'FROM {OFFICIAL}\nENTRYPOINT ["/x"]\n') == ["B002"]

    def test_b002_only_final_stage(self) -> None:
        text = f'FROM x AS b\nENTRYPOINT ["/x"]\nFROM {OFFICIAL}\n'
        assert self.codes(text) == []

    def test_b003_user_root_left_active(self) -> None:
        assert self.codes(f"FROM {OFFICIAL}\nUSER root\n") == ["B003"]
        assert self.codes(f"FROM {OFFICIAL}\nUSER 0\n") == ["B003"]

    def test_b003_root_then_user_is_fine(self) -> None:
        assert self.codes(f"FROM {OFFICIAL}\nUSER root\nRUN true\nUSER user\n") == []

    @pytest.mark.parametrize("port", [5000, 49983, 49999])
    def test_b004_reserved_ports(self, port: int) -> None:
        assert self.codes(f"FROM {OFFICIAL}\nEXPOSE 9000 {port}\n") == ["B004"]

    def test_b005_no_from(self) -> None:
        issues = lint_dockerfile("RUN true\n")
        assert [i.code for i in issues] == ["B005"]
        assert issues[0].severity == "error"

    def test_line_continuations_are_joined(self) -> None:
        text = f"FROM {OFFICIAL}\nRUN a \\\n && b\nENTRYPOINT x\n"
        issues = lint_dockerfile(text)
        assert [(i.code, i.line) for i in issues] == [("B002", 4)]

    def test_comments_and_blank_lines_ignored(self) -> None:
        assert self.codes(f"# c\n\nFROM {OFFICIAL}\n# ENTRYPOINT x\n") == []

    def test_issue_str_contains_code_and_line(self) -> None:
        (issue,) = lint_dockerfile("FROM ubuntu:22.04\n")
        assert str(issue).startswith("B001:") and "(line 1)" in str(issue)

    def test_warn_logs_each_issue_and_returns_them(self, caplog: pytest.LogCaptureFixture) -> None:
        log = logging.getLogger("test.base_image")
        with caplog.at_level("WARNING", logger="test.base_image"):
            issues = warn_on_dockerfile("FROM ubuntu:22.04\nENTRYPOINT x\n", log, source="X")
        assert len(issues) == 2
        assert [r.levelname for r in caplog.records] == ["WARNING", "WARNING"]
        assert all("X:" in r.getMessage() for r in caplog.records)


class TestScaffold:
    def test_clean_under_its_own_lint(self) -> None:
        assert lint_dockerfile(scaffold_dockerfile()) == []

    def test_starts_from_official_image(self) -> None:
        assert scaffold_dockerfile().splitlines()[0] == f"FROM {OFFICIAL}"

    def test_pypi_fallback_is_pinned_to_the_sdk_version(self) -> None:
        text = scaffold_dockerfile()
        assert f"easy-sandbox-server=={__version__}" in text
        assert "COPY *.whl /tmp/" in text

    def test_explicit_version_and_wheel_glob(self) -> None:
        text = scaffold_dockerfile(server_version="1.2.3", wheel_glob="dist/*.whl")
        assert "easy-sandbox-server==1.2.3" in text
        assert "COPY dist/*.whl /tmp/" in text

    def test_no_entrypoint_or_cmd(self) -> None:
        for line in scaffold_dockerfile().splitlines():
            assert not line.startswith(("ENTRYPOINT", "CMD"))

    def test_start_and_ready_commands_documented(self) -> None:
        text = scaffold_dockerfile()
        assert SERVER_START_CMD in text
        assert SERVER_READY_CMD in text
        assert "--commands /home/user/app/commands.py" in text

    def test_optional_requirements_and_policy(self) -> None:
        text = scaffold_dockerfile(requirements_file="req.txt", policy_file="policy.json")
        assert "RUN pip install -r /home/user/app/req.txt" in text
        contract = BaseImageContract()
        assert f"COPY policy.json {contract.policy_path}" in text
        assert f"check-config --policy {contract.policy_path}" in text
        assert "--strict" not in text

    def test_without_commands_file(self) -> None:
        text = scaffold_dockerfile(commands_file=None)
        assert "--commands" not in text

    def test_region_variant_tag(self) -> None:
        text = scaffold_dockerfile(region="cn-shanghai", variant="browser", tag="v2")
        assert text.startswith(
            "FROM fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/runtime/browser:v2"
        )


class TestContract:
    def test_defaults(self) -> None:
        c = BaseImageContract()
        assert (c.user, c.home, c.server_port, c.pty_port) == ("user", "/home/user", 9000, 9001)
        assert c.reserved_ports() == (5000, 49983, 49999)
        assert "ENTRYPOINT" in c.forbidden_directives


class TestImageIntegration:
    def test_default_image_unchanged(self) -> None:
        assert Image().to_dockerfile().splitlines()[0] == "FROM ubuntu:22.04"

    def test_official_base(self) -> None:
        assert Image.official_base().to_dockerfile().splitlines()[0] == f"FROM {OFFICIAL}"

    def test_official_base_variant(self) -> None:
        first = Image.official_base("claude-code", region="cn-shanghai", tag="v3")
        assert first.to_dockerfile().startswith(
            "FROM fc-e2b-registry.cn-shanghai.cr.aliyuncs.com/runtime/claude-code:v3"
        )

    def test_official_base_rejects_malformed(self) -> None:
        with pytest.raises(ValueError):
            Image.official_base("a/b")


class TestDockerBuilderLint:
    def test_foreign_base_warns_but_does_not_raise(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        df = tmp_path / "Dockerfile"
        df.write_text("FROM ubuntu:22.04\n", encoding="utf-8")
        with caplog.at_level("WARNING", logger="easy_sandbox"):
            DockerBuilder._lint_dockerfile(df)
        assert any("B001" in r.getMessage() for r in caplog.records)

    def test_official_base_is_silent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        df = tmp_path / "Dockerfile"
        df.write_text(f"FROM {OFFICIAL}\n", encoding="utf-8")
        with caplog.at_level("WARNING", logger="easy_sandbox"):
            DockerBuilder._lint_dockerfile(df)
        assert not caplog.records

    def test_missing_dockerfile_is_ignored(self, tmp_path: Path) -> None:
        DockerBuilder._lint_dockerfile(tmp_path / "nope")
