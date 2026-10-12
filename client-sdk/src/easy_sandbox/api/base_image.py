"""The official Alibaba Cloud Function Compute Agent Sandbox base image: contract and helpers.

Templates should be built ``FROM`` the official image: it already contains *envd* (so the platform
needs no ``copy`` + ``envdInject`` build step), runs the gateway as PID 1 and has the user, home
and ports the SDK assumes.  This module documents that contract in code and provides

* :func:`official_base_image` / :func:`is_official_base_image` -- image references,
* :class:`BaseImageContract` -- ports, user, paths and start/ready commands,
* :func:`lint_dockerfile` -- advisory checks (never raises, never changes a build),
* :func:`scaffold_dockerfile` -- a Dockerfile that layers ``easy-sandbox-server`` onto the image.

Nothing here changes the behaviour of an existing build: ``Image()`` still starts from
``ubuntu:22.04`` and ``DockerBuilder`` accepts any Dockerfile.  Non-official bases only produce
warnings that name the consequence.  See ``docs/en/design/base-image-and-server-sdk.md``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from easy_sandbox._version import __version__

if TYPE_CHECKING:
    import logging

#: ``fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/<variant>:<tag>``
OFFICIAL_REGISTRY_FMT = "fc-e2b-registry.{region}.cr.aliyuncs.com/runtime/{variant}:{tag}"
OFFICIAL_REGISTRY_HOST_RE = re.compile(r"^fc-e2b-registry\.([a-z0-9-]+)\.cr\.aliyuncs\.com$")

DEFAULT_REGION = "cn-hangzhou"
DEFAULT_BASE_VARIANT = "base"
#: Official tag documented at the time of writing; override with ``EBX_BASE_IMAGE_TAG``.
DEFAULT_BASE_TAG = "v0.0.49"

#: Variants published in the official registry (informational; unknown variants are accepted).
KNOWN_VARIANTS = ("base", "code-interpreter-v1", "browser", "claude-code")

#: Server ports (envd 49983, the gateway 5000 and the code interpreter 49999 are reserved).
SERVER_HTTP_PORT = 9000
SERVER_PTY_PORT = 9001
RESERVED_PORTS = (5000, 49983, 49999)

SERVER_START_CMD = f"easy-sandbox-server serve --port {SERVER_HTTP_PORT}"
SERVER_READY_CMD = f"easy-sandbox-server healthcheck --port {SERVER_HTTP_PORT}"
SERVER_POLICY_PATH = "/etc/easy-sandbox/server-policy.json"


def official_base_image(
    *,
    region: str | None = None,
    variant: str = DEFAULT_BASE_VARIANT,
    tag: str | None = None,
) -> str:
    """Return the reference of an official base image.

    Args:
        region: Region of the sandbox (the image region **must** equal it).  Defaults to
            ``EBX_BASE_IMAGE_REGION`` or ``cn-hangzhou``.
        variant: Image name below ``runtime/`` (``base``, ``code-interpreter-v1``, ...).
        tag: Image tag.  Defaults to ``EBX_BASE_IMAGE_TAG`` or :data:`DEFAULT_BASE_TAG`.

    Raises:
        ValueError: *region*, *variant* or *tag* is malformed.
    """
    region = region or os.environ.get("EBX_BASE_IMAGE_REGION") or DEFAULT_REGION
    tag = tag or os.environ.get("EBX_BASE_IMAGE_TAG") or DEFAULT_BASE_TAG
    for label, value, pattern in (
        ("region", region, r"[a-z0-9-]+"),
        ("variant", variant, r"[a-z0-9][a-z0-9._-]*"),
        ("tag", tag, r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}"),
    ):
        if not re.fullmatch(pattern, value):
            raise ValueError(f"invalid {label} for the official base image: {value!r}")
    return OFFICIAL_REGISTRY_FMT.format(region=region, variant=variant, tag=tag)


def is_official_base_image(ref: str) -> bool:
    """Whether *ref* points into the official ``fc-e2b-registry`` ``runtime/`` namespace."""
    name = ref.strip().split("@", 1)[0]
    host, _, rest = name.partition("/")
    return bool(OFFICIAL_REGISTRY_HOST_RE.match(host)) and rest.startswith("runtime/")


@dataclass(frozen=True)
class BaseImageContract:
    """What a Dockerfile layered on the official image can rely on (and must not break)."""

    user: str = "user"
    home: str = "/home/user"
    app_dir: str = "/home/user/app"
    shell: str = "/bin/bash"
    platform: str = "linux/amd64"
    envd_port: int = 49983
    gateway_port: int = 5000
    server_port: int = SERVER_HTTP_PORT
    pty_port: int = SERVER_PTY_PORT
    start_cmd: str = SERVER_START_CMD
    ready_cmd: str = SERVER_READY_CMD
    policy_path: str = SERVER_POLICY_PATH
    #: Directives a template must not set: the gateway is PID 1.
    forbidden_directives: tuple[str, ...] = ("ENTRYPOINT",)

    def reserved_ports(self) -> tuple[int, ...]:
        return RESERVED_PORTS


@dataclass(frozen=True)
class BaseImageIssue:
    """One advisory finding of :func:`lint_dockerfile`."""

    code: str
    message: str
    severity: str = "warning"
    line: int = 0

    def __str__(self) -> str:
        where = f" (line {self.line})" if self.line else ""
        return f"{self.code}: {self.message}{where}"


@dataclass
class _Parsed:
    from_lines: list[tuple[int, str]] = field(default_factory=list)
    directives: list[tuple[int, str, str]] = field(default_factory=list)


def _parse(text: str) -> _Parsed:
    parsed = _Parsed()
    logical = ""
    start = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not logical:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            start = number
        if line.endswith("\\"):
            logical += line[:-1] + " "
            continue
        logical += line
        keyword, _, rest = logical.strip().partition(" ")
        keyword = keyword.upper()
        parsed.directives.append((start, keyword, rest.strip()))
        if keyword == "FROM":
            parsed.from_lines.append((start, rest.strip()))
        logical = ""
    return parsed


def _from_image(arg: str) -> str:
    tokens = [t for t in arg.split() if not t.startswith("--")]
    return tokens[0] if tokens else ""


def lint_dockerfile(text: str) -> list[BaseImageIssue]:
    """Check *text* against the base-image contract.  Advisory only: never raises.

    Codes: ``B001`` last stage is not based on the official image, ``B002`` ``ENTRYPOINT`` set
    (replaces the gateway), ``B003`` ``USER root`` left active at the end, ``B004`` a reserved
    port is ``EXPOSE``d, ``B005`` no ``FROM``.
    """
    parsed = _parse(text)
    issues: list[BaseImageIssue] = []
    if not parsed.from_lines:
        return [BaseImageIssue("B005", "no FROM instruction found", "error")]
    line, arg = parsed.from_lines[-1]
    image = _from_image(arg)
    stage_names = {
        a.split()[-1].lower()
        for _, a in parsed.from_lines
        if len(a.split()) >= 3 and a.split()[-2].lower() == "as"
    }
    if image and image.lower() not in stage_names and not is_official_base_image(image):
        issues.append(
            BaseImageIssue(
                "B001",
                f"base image {image!r} is not the official Agent Sandbox image; the platform "
                "must inject envd during the build (envd_inject=True) and the template cannot "
                "rely on the documented user/ports. Prefer "
                f"`FROM {official_base_image()}` (see Image.official_base()).",
                line=line,
            )
        )
    final_stage_start = line
    user = None
    for number, keyword, rest in parsed.directives:
        if number < final_stage_start:
            continue
        if keyword == "ENTRYPOINT":
            issues.append(
                BaseImageIssue(
                    "B002",
                    "ENTRYPOINT replaces the official gateway (PID 1), which supervises envd; "
                    "use the platform start command (easy-sandbox-server serve) instead",
                    line=number,
                )
            )
        elif keyword == "USER":
            user = rest.split(":", 1)[0].strip()
        elif keyword == "EXPOSE":
            for port in re.findall(r"\d+", rest):
                if int(port) in RESERVED_PORTS:
                    issues.append(
                        BaseImageIssue(
                            "B004", f"port {port} is reserved by the sandbox runtime", line=number
                        )
                    )
    if user in {"root", "0"}:
        issues.append(
            BaseImageIssue(
                "B003",
                "the final USER is root; the runtime and examples assume the 'user' account",
            )
        )
    return issues


def warn_on_dockerfile(
    text: str, log: logging.Logger, *, source: str = "Dockerfile"
) -> list[BaseImageIssue]:
    """Log :func:`lint_dockerfile` findings as warnings (build behaviour is never changed)."""
    issues = lint_dockerfile(text)
    for issue in issues:
        log.warning("%s: %s", source, issue)
    return issues


def scaffold_dockerfile(
    *,
    region: str | None = None,
    variant: str = DEFAULT_BASE_VARIANT,
    tag: str | None = None,
    app_dir: str = "/home/user/app",
    commands_file: str | None = "commands.py",
    requirements_file: str | None = None,
    policy_file: str | None = None,
    server_version: str | None = None,
    wheel_glob: str = "*.whl",
) -> str:
    """Return a Dockerfile layering ``easy-sandbox-server`` onto the official base image.

    The SDK is installed from a wheel injected into the build context (``DockerBuilder`` does
    this for dev checkouts and the matching PyPI release) with a PyPI fallback **pinned to the
    SDK version** (client and server release in lock-step).  No ``ENTRYPOINT``/``CMD`` is
    emitted; the platform starts the server with :data:`SERVER_START_CMD`.
    """
    contract = BaseImageContract(app_dir=app_dir)
    version = server_version or __version__
    lines = [
        f"FROM {official_base_image(region=region, variant=variant, tag=tag)}",
        "",
        "# PEP 668: the official image's Python is externally managed.",
        "ENV PIP_BREAK_SYSTEM_PACKAGES=1 PIP_NO_CACHE_DIR=1",
        "",
        "# easy-sandbox-server: injected wheel first, pinned PyPI release as fallback.",
        f"COPY {wheel_glob} /tmp/",
        "RUN command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 1; } \\",
        " && if ls /tmp/easy_sandbox_server-*.whl >/dev/null 2>&1; then \\",
        "      pip install /tmp/easy_sandbox_server-*.whl; \\",
        "    else \\",
        f"      pip install 'easy-sandbox-server=={version}'; \\",
        "    fi \\",
        " && rm -f /tmp/easy_sandbox_server-*.whl",
        "",
        f"WORKDIR {contract.app_dir}",
    ]
    if requirements_file:
        lines += [
            f"COPY {requirements_file} {contract.app_dir}/{requirements_file}",
            f"RUN pip install -r {contract.app_dir}/{requirements_file}",
        ]
    if commands_file:
        lines.append(f"COPY {commands_file} {contract.app_dir}/{commands_file}")
    if policy_file:
        lines += [
            f"COPY {policy_file} {contract.policy_path}",
            f"RUN easy-sandbox-server check-config --policy {contract.policy_path}",
        ]
    lines += [
        "",
        f"EXPOSE {contract.server_port} {contract.pty_port}",
        f"ENV EBX_SERVER_BASE_DIR={contract.home}",
        "",
        "# Platform start/ready commands (do not rely on CMD; the gateway is PID 1):",
        f"#   start_cmd: {SERVER_START_CMD}"
        + (f" --commands {contract.app_dir}/{commands_file}" if commands_file else ""),
        f"#   ready_cmd: {SERVER_READY_CMD}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "DEFAULT_BASE_TAG",
    "DEFAULT_BASE_VARIANT",
    "DEFAULT_REGION",
    "KNOWN_VARIANTS",
    "OFFICIAL_REGISTRY_FMT",
    "RESERVED_PORTS",
    "SERVER_HTTP_PORT",
    "SERVER_POLICY_PATH",
    "SERVER_PTY_PORT",
    "SERVER_READY_CMD",
    "SERVER_START_CMD",
    "BaseImageContract",
    "BaseImageIssue",
    "is_official_base_image",
    "lint_dockerfile",
    "official_base_image",
    "scaffold_dockerfile",
    "warn_on_dockerfile",
]
