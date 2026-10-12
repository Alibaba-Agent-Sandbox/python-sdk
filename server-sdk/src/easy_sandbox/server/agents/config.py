"""Declarative agent definitions (``agent.yaml`` / JSON) — stdlib-only.

An :class:`AgentSpec` is the single configuration object consumed by the
runtime and the adapters.  Secrets (provider key, git token, ``secrets``,
MCP header/env values) are kept in the spec but never serialised by
:meth:`AgentSpec.public_dict`.
"""

from __future__ import annotations

import dataclasses
import difflib
import re
from typing import TYPE_CHECKING, Any

from .errors import AgentConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "GitSpec",
    "LimitsSpec",
    "McpServerSpec",
    "ProviderSpec",
    "WorkspaceSpec",
    "AgentSpec",
    "PERMISSION_MODES",
    "expand_vars",
]

PERMISSION_MODES = ("read_only", "workspace_write", "full_access")

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_MCP_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_DENIED_ENV = frozenset({"LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES"})
_GIT_SCHEMES = ("https://", "ssh://", "git://")


def expand_vars(value: str, environ: Mapping[str, str], problems: list[str], where: str) -> str:
    """Expand ``${VAR}`` / ``${VAR:-default}`` using *environ*.

    An unset variable without default is recorded in *problems* (never silently
    replaced by an empty string).
    """

    def _sub(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in environ:
            return environ[name]
        if default is not None:
            return default
        problems.append(f"{where}: environment variable {name} is not set")
        return ""

    return _VAR_RE.sub(_sub, value)


def _check_keys(
    data: Mapping[str, Any], allowed: set[str], where: str, problems: list[str]
) -> None:
    for key in data:
        if key not in allowed:
            hint = difflib.get_close_matches(str(key), sorted(allowed), n=1)
            suffix = f" (did you mean {hint[0]!r}?)" if hint else ""
            problems.append(f"{where}: unknown field {key!r}{suffix}")


def _str_map(value: Any, where: str, problems: list[str]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append(f"{where}: expected a mapping of strings")
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(item, (dict, list)) or item is None:
            problems.append(f"{where}.{key}: expected a scalar value")
            continue
        out[str(key)] = str(item)
    return out


def _check_env_names(values: Mapping[str, str], where: str, problems: list[str]) -> None:
    for key in values:
        if not _ENV_NAME_RE.match(key):
            problems.append(f"{where}: invalid environment variable name {key!r}")
        elif key in _DENIED_ENV or key.startswith("EBX_SERVER_"):
            problems.append(f"{where}: environment variable {key} is not allowed")


@dataclasses.dataclass
class ProviderSpec:
    """Model endpoint credentials for the CLI (``api_key`` is a secret)."""

    base_url: str | None = None
    api_key: str | None = None
    wire_api: str = "responses"
    auth: str = "api_key"
    api_key_env: str | None = None


@dataclasses.dataclass
class GitSpec:
    """Repository to clone into the workspace on first use (``token`` is secret)."""

    url: str
    ref: str | None = None
    token: str | None = None
    token_user: str = "x-access-token"
    depth: int | None = None


@dataclasses.dataclass
class WorkspaceSpec:
    """Working directory of the agent process."""

    path: str = "/workspace"
    git: GitSpec | None = None


@dataclasses.dataclass
class McpServerSpec:
    """One MCP server passed through to the CLI (stdio or remote)."""

    name: str
    command: str | None = None
    args: list[str] = dataclasses.field(default_factory=list)
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    transport: str | None = None

    @property
    def is_remote(self) -> bool:
        """``True`` for URL-based servers."""
        return self.url is not None

    def header_var(self, header: str) -> str:
        """Environment variable that carries the value of *header* for the CLI."""
        return _env_var("EBX_MCP", self.name, header)

    def env_var(self, key: str) -> str:
        """Environment variable that carries stdio-server env entry *key*."""
        return _env_var("EBX_MCP", self.name, "ENV", key)


def _env_var(*parts: str) -> str:
    return "_".join(re.sub(r"[^A-Za-z0-9]+", "_", p).strip("_").upper() for p in parts if p)


@dataclasses.dataclass
class LimitsSpec:
    """Per-turn resource limits."""

    turn_timeout_s: float = 1800.0
    idle_timeout_s: float = 300.0
    max_turns: int | None = None
    max_budget_usd: float | None = None
    max_output_bytes: int = 8 * 1024 * 1024
    cpu_seconds: int | None = None


_PROVIDER_KEYS = {"base_url", "api_key", "wire_api", "auth", "api_key_env"}
_GIT_KEYS = {"url", "ref", "token", "token_user", "depth"}
_WORKSPACE_KEYS = {"path", "git", "upload"}
_MCP_KEYS = {"command", "args", "env", "url", "headers", "transport"}
_LIMIT_KEYS = {
    "turn_timeout_s",
    "idle_timeout_s",
    "max_turns",
    "max_budget_usd",
    "max_output_bytes",
    "cpu_seconds",
}
_AGENT_KEYS = {
    "name",
    "runtime",
    "model",
    "instructions",
    "description",
    "provider",
    "workspace",
    "env",
    "secrets",
    "mcp_servers",
    "permissions",
    "limits",
    "extra_args",
    "command",
    "reasoning_effort",
}


@dataclasses.dataclass
class AgentSpec:
    """A fully resolved, validated agent definition."""

    name: str
    runtime: str
    model: str | None = None
    instructions: str | None = None
    description: str | None = None
    provider: ProviderSpec = dataclasses.field(default_factory=ProviderSpec)
    workspace: WorkspaceSpec = dataclasses.field(default_factory=WorkspaceSpec)
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    secrets: dict[str, str] = dataclasses.field(default_factory=dict)
    mcp_servers: dict[str, McpServerSpec] = dataclasses.field(default_factory=dict)
    permissions: str = "full_access"
    limits: LimitsSpec = dataclasses.field(default_factory=LimitsSpec)
    extra_args: list[str] = dataclasses.field(default_factory=list)
    command: dict[str, Any] | None = None
    reasoning_effort: str | None = None
    ephemeral: bool = False

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        environ: Mapping[str, str] | None = None,
        name: str | None = None,
    ) -> AgentSpec:
        """Parse and validate *data*.

        Args:
            data: Mapping as found in ``agent.yaml``/JSON.
            environ: When given, ``${VAR}`` placeholders in string values are
                expanded from it (unset variables are configuration errors).
            name: Default/forced agent name (e.g. from the URL path).

        Raises:
            AgentConfigError: listing *every* problem found.
        """
        problems: list[str] = []
        if not isinstance(data, dict):
            raise AgentConfigError("agent definition must be a JSON object")
        _check_keys(data, _AGENT_KEYS, "agent", problems)

        def sub(value: Any, where: str) -> Any:
            if environ is not None and isinstance(value, str):
                return expand_vars(value, environ, problems, where)
            return value

        def text(key: str, where: str | None = None) -> str | None:
            value = data.get(key)
            if value is None:
                return None
            if not isinstance(value, (str, int, float)):
                problems.append(f"{key}: expected a string")
                return None
            return str(sub(str(value), where or key))

        agent_name = name if name is not None else text("name")
        if not agent_name or not _NAME_RE.match(agent_name):
            problems.append("name: required, 1-64 characters of [A-Za-z0-9._-]")
            agent_name = agent_name or "invalid"
        elif name is not None and data.get("name") not in (None, name):
            problems.append(f"name: body name {data.get('name')!r} does not match {name!r}")
        runtime = text("runtime")
        if not runtime:
            problems.append(
                "runtime: required (codex, claude-code, cursor, qwen-code, command, ...)"
            )

        provider = cls._parse_provider(data.get("provider"), sub, problems)
        workspace = cls._parse_workspace(data.get("workspace"), sub, problems)
        limits = cls._parse_limits(data.get("limits"), problems)
        mcp_servers = cls._parse_mcp(data.get("mcp_servers"), sub, problems)

        env = {
            k: str(sub(v, f"env.{k}"))
            for k, v in _str_map(data.get("env"), "env", problems).items()
        }
        secrets = {
            k: str(sub(v, f"secrets.{k}"))
            for k, v in _str_map(data.get("secrets"), "secrets", problems).items()
        }
        _check_env_names(env, "env", problems)
        _check_env_names(secrets, "secrets", problems)
        overlap = set(env) & set(secrets)
        if overlap:
            problems.append(f"env/secrets: {sorted(overlap)} defined in both")

        permissions = (text("permissions") or "full_access").replace("-", "_")
        if permissions not in PERMISSION_MODES:
            problems.append(f"permissions: must be one of {', '.join(PERMISSION_MODES)}")

        extra_args_raw = data.get("extra_args") or []
        if not isinstance(extra_args_raw, list) or not all(
            isinstance(a, (str, int, float)) for a in extra_args_raw
        ):
            problems.append("extra_args: expected a list of strings")
            extra_args_raw = []

        command = data.get("command")
        if command is not None and not isinstance(command, dict):
            problems.append("command: expected a mapping")
            command = None

        effort = text("reasoning_effort")
        if effort is not None and effort not in (
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
        ):
            problems.append("reasoning_effort: must be none|minimal|low|medium|high|xhigh")

        if problems:
            raise AgentConfigError(problems)
        return cls(
            name=str(agent_name),
            runtime=str(runtime),
            model=text("model"),
            instructions=text("instructions"),
            description=text("description"),
            provider=provider,
            workspace=workspace,
            env=env,
            secrets=secrets,
            mcp_servers=mcp_servers,
            permissions=permissions,
            limits=limits,
            extra_args=[str(a) for a in extra_args_raw],
            command=dict(command) if command else None,
            reasoning_effort=effort,
        )

    @staticmethod
    def _parse_provider(raw: Any, sub: Any, problems: list[str]) -> ProviderSpec:
        if raw is None:
            return ProviderSpec()
        if not isinstance(raw, dict):
            problems.append("provider: expected a mapping")
            return ProviderSpec()
        _check_keys(raw, _PROVIDER_KEYS, "provider", problems)

        def field(key: str) -> str | None:
            value = raw.get(key)
            return None if value is None else str(sub(str(value), f"provider.{key}"))

        spec = ProviderSpec(
            base_url=field("base_url"),
            api_key=field("api_key"),
            wire_api=field("wire_api") or "responses",
            auth=field("auth") or "api_key",
            api_key_env=field("api_key_env"),
        )
        if spec.base_url and not spec.base_url.startswith(("http://", "https://")):
            problems.append("provider.base_url: must start with http:// or https://")
        if spec.wire_api not in ("responses", "chat"):
            problems.append("provider.wire_api: must be 'responses' or 'chat'")
        if spec.auth not in ("api_key", "bearer"):
            problems.append("provider.auth: must be 'api_key' or 'bearer'")
        if spec.api_key_env and not _ENV_NAME_RE.match(spec.api_key_env):
            problems.append("provider.api_key_env: invalid environment variable name")
        return spec

    @staticmethod
    def _parse_workspace(raw: Any, sub: Any, problems: list[str]) -> WorkspaceSpec:
        if raw is None:
            return WorkspaceSpec()
        if isinstance(raw, str):
            raw = {"path": raw}
        if not isinstance(raw, dict):
            problems.append("workspace: expected a mapping or a path")
            return WorkspaceSpec()
        _check_keys(raw, _WORKSPACE_KEYS, "workspace", problems)
        path = str(sub(str(raw.get("path") or "/workspace"), "workspace.path"))
        if not path.startswith("/") or ".." in path.split("/"):
            problems.append("workspace.path: must be absolute and must not contain '..'")
        git: GitSpec | None = None
        git_raw = raw.get("git")
        if isinstance(git_raw, str):
            git_raw = {"url": git_raw}
        if git_raw is not None:
            if not isinstance(git_raw, dict):
                problems.append("workspace.git: expected a mapping or a URL")
            else:
                _check_keys(git_raw, _GIT_KEYS, "workspace.git", problems)
                url = str(sub(str(git_raw.get("url") or ""), "workspace.git.url"))
                if not url.startswith(_GIT_SCHEMES) or url.startswith("-"):
                    problems.append("workspace.git.url: must start with https://, ssh:// or git://")
                token = git_raw.get("token")
                depth = git_raw.get("depth")
                git = GitSpec(
                    url=url,
                    ref=(
                        str(sub(str(git_raw["ref"]), "workspace.git.ref"))
                        if git_raw.get("ref")
                        else None
                    ),
                    token=str(sub(str(token), "workspace.git.token")) if token else None,
                    token_user=str(git_raw.get("token_user") or "x-access-token"),
                    depth=int(depth) if depth else None,
                )
                if git.ref is not None and (git.ref.startswith("-") or " " in git.ref):
                    problems.append("workspace.git.ref: invalid ref")
        return WorkspaceSpec(path=path, git=git)

    @staticmethod
    def _parse_limits(raw: Any, problems: list[str]) -> LimitsSpec:
        if raw is None:
            return LimitsSpec()
        if not isinstance(raw, dict):
            problems.append("limits: expected a mapping")
            return LimitsSpec()
        _check_keys(raw, _LIMIT_KEYS, "limits", problems)
        limits = LimitsSpec()
        for key in _LIMIT_KEYS:
            value = raw.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                problems.append(f"limits.{key}: must be a positive number")
                continue
            setattr(
                limits,
                key,
                value
                if key in ("turn_timeout_s", "idle_timeout_s", "max_budget_usd")
                else int(value),
            )
        return limits

    @staticmethod
    def _parse_mcp(raw: Any, sub: Any, problems: list[str]) -> dict[str, McpServerSpec]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            problems.append("mcp_servers: expected a mapping of name -> server")
            return {}
        servers: dict[str, McpServerSpec] = {}
        for name, item in raw.items():
            where = f"mcp_servers.{name}"
            if not _MCP_NAME_RE.match(str(name)):
                problems.append(f"{where}: name must match [A-Za-z0-9_-]{{1,40}}")
                continue
            if not isinstance(item, dict):
                problems.append(f"{where}: expected a mapping")
                continue
            _check_keys(item, _MCP_KEYS, where, problems)
            command = item.get("command")
            url = item.get("url")
            if bool(command) == bool(url):
                problems.append(f"{where}: exactly one of 'command' or 'url' is required")
                continue
            args = item.get("args") or []
            if not isinstance(args, list):
                problems.append(f"{where}.args: expected a list")
                args = []
            env = {
                k: str(sub(v, f"{where}.env.{k}"))
                for k, v in _str_map(item.get("env"), f"{where}.env", problems).items()
            }
            headers = {
                k: str(sub(v, f"{where}.headers.{k}"))
                for k, v in _str_map(item.get("headers"), f"{where}.headers", problems).items()
            }
            _check_env_names(env, f"{where}.env", problems)
            if url and not str(url).startswith(("http://", "https://")):
                problems.append(f"{where}.url: must start with http:// or https://")
            servers[str(name)] = McpServerSpec(
                name=str(name),
                command=str(sub(str(command), f"{where}.command")) if command else None,
                args=[str(sub(str(a), f"{where}.args")) for a in args],
                env=env,
                url=str(sub(str(url), f"{where}.url")) if url else None,
                headers=headers,
                transport=str(item["transport"]) if item.get("transport") else None,
            )
        return servers

    # ------------------------------------------------------------------ #
    # Derived data
    # ------------------------------------------------------------------ #

    def secret_values(self) -> list[str]:
        """Every secret value held by this spec (for redaction)."""
        values: list[str] = list(self.secrets.values())
        if self.provider.api_key:
            values.append(self.provider.api_key)
        if self.workspace.git and self.workspace.git.token:
            values.append(self.workspace.git.token)
        for server in self.mcp_servers.values():
            values.extend(server.headers.values())
            values.extend(server.env.values())
        return [v for v in values if v]

    def mcp_env(self) -> dict[str, str]:
        """Env vars that carry MCP header / env values to the CLI (placeholders → values)."""
        out: dict[str, str] = {}
        for server in self.mcp_servers.values():
            for header, value in server.headers.items():
                out[server.header_var(header)] = value
            for key, value in server.env.items():
                out[server.env_var(key)] = value
        return out

    def public_dict(self) -> dict[str, Any]:
        """JSON view with every secret masked as ``"***"``."""
        mask = "***"
        return {
            "name": self.name,
            "runtime": self.runtime,
            "model": self.model,
            "instructions": self.instructions,
            "description": self.description,
            "provider": {
                "base_url": self.provider.base_url,
                "api_key": mask if self.provider.api_key else None,
                "wire_api": self.provider.wire_api,
                "auth": self.provider.auth,
                "api_key_env": self.provider.api_key_env,
            },
            "workspace": {
                "path": self.workspace.path,
                "git": None
                if self.workspace.git is None
                else {
                    "url": _strip_userinfo(self.workspace.git.url),
                    "ref": self.workspace.git.ref,
                    "token": mask if self.workspace.git.token else None,
                    "depth": self.workspace.git.depth,
                },
            },
            "env": dict(self.env),
            "secrets": dict.fromkeys(self.secrets, mask),
            "mcp_servers": {
                n: {
                    "command": s.command,
                    "args": list(s.args),
                    "env": dict.fromkeys(s.env, mask),
                    "url": s.url,
                    "headers": dict.fromkeys(s.headers, mask),
                    "transport": s.transport,
                }
                for n, s in self.mcp_servers.items()
            },
            "permissions": self.permissions,
            "limits": dataclasses.asdict(self.limits),
            "extra_args": list(self.extra_args),
            "command": self.command,
            "reasoning_effort": self.reasoning_effort,
        }


def _strip_userinfo(url: str) -> str:
    return re.sub(r"^([a-z]+://)[^/@]*@", r"\1", url)
