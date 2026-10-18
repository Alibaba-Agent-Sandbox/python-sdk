"""Layered configuration loading.

Resolution is *layer-first* (see ``docs/en/design/providers-and-credentials.md``)::

    explicit kwargs > process environment > ./.env > ~/.abx/.env
        > ~/.abx/config.toml > defaults

Inside one layer a key has one environment variable. Product settings use
``ABX_<KEY>``. A vendor that already publishes a name keeps that name
(``ALICLOUD_ACCESS_KEY_ID``, ``ACR_NAMESPACE``, ``GITHUB_TOKEN``,
``ALIBABA_CLOUD_REGION_ID``). A blank or whitespace-only value is unset and
does not hide the next layer.

Canonical field names are ``sandbox_api_key``, ``sandbox_base_url`` and
``sandbox_domain``.

The generic ``sandbox_*`` keys belong to the built-in provider (``alicloud-express``).
Another provider receives them only through its consented ``inherit`` list.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from agent_sandbox._provider_schema import ProviderSchema as ProviderSchema
from agent_sandbox._provider_schema import resolve_provider_schema
from agent_sandbox.utils.bundled_config import (
    BUNDLED_CONFIGS,
    BUNDLED_KEYS,
    DEFAULT_CONFIG,
    bundled_config,
)
from agent_sandbox.utils.config_keys import (
    BUILTIN_PROVIDER_ID,
    CORE_KEYS,
    GENERIC_ENDPOINT_KEYS,
    ConfigKey,
    Resolved,
    Sources,
    env_names,
    get_key,
    provider_env_name,
    resolve_key,
)
from agent_sandbox.utils.logging import get_logger

logger = get_logger("transport.config")

# envd 数据平面固定端口（已实测验证）
ENVD_PORT: int = 49983

_ABX_DIR = Path.home() / ".abx"  # SDK extension
_CONFIG_FILE = _ABX_DIR / "config.toml"  # SDK extension
# Earlier entries are higher-priority layers. Each existing file is its own layer.
_ENV_FILE_CANDIDATES = [Path(".env"), _ABX_DIR / ".env"]
# Project dotenv only. The CLI reads this between the process environment
# and ~/.abx. Tests point it at a missing file so a repo .env cannot leak.
_PROJECT_ENV_FILE = Path(".env")

# Module-level cache
_cached_config: TransportConfig | None = None

DEFAULT_BASE_URL = DEFAULT_CONFIG["endpoint_defaults"]["sandbox_base_url"]
DEFAULT_DOMAIN = DEFAULT_CONFIG["endpoint_defaults"]["sandbox_domain"]
_DEFAULT_REGION = str(
    next((key.default for key in DEFAULT_CONFIG["keys"] if key.key == "region"), "")
)


class TransportConfig(BaseModel):
    """Transport-layer configuration.

    Loaded lazily from multiple sources (see the module docstring).
    """

    provider: str = Field(default=BUILTIN_PROVIDER_ID, description="Active provider id")

    # API endpoints
    sandbox_base_url: str = Field(default=DEFAULT_BASE_URL, description="Platform API URL")
    sandbox_domain: str = Field(default=DEFAULT_DOMAIN, description="Data-plane domain")
    region: str = _DEFAULT_REGION

    # Authentication
    sandbox_api_key: str | None = Field(
        default=None, description="Sandbox API key (E2B_API_KEY)", repr=False
    )
    access_key_id: str | None = Field(default=None, description="Provider AccessKey ID")
    access_key_secret: str | None = Field(
        default=None, description="Provider AccessKey Secret", repr=False
    )

    # Provider-scoped values of non-built-in providers (and extra built-in keys such as ``acr_*``)
    provider_options: dict[str, Any] = Field(default_factory=dict)

    # HTTP settings
    http_timeout: float = Field(default=30.0, ge=1.0, description="HTTP request timeout in seconds")
    max_connections: int = Field(default=100, ge=1)
    max_keepalive_connections: int = Field(default=20, ge=1)
    keepalive_expiry: float = Field(default=30.0, ge=1.0)
    http2: bool = True

    # WebSocket settings
    ws_ping_interval: float = Field(
        default=30.0, ge=1.0, description="WebSocket ping interval in seconds"
    )

    # Retry settings
    max_retries: int = Field(default=3, ge=0)
    retry_base_delay: float = Field(default=1.0, ge=0.1)

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def selected_provider_defaults(cls, value: Any) -> Any:
        """An explicit external provider never inherits the distribution's cloud endpoints."""
        if not isinstance(value, dict):
            return value
        metadata = bundled_config(str(value.get("provider", BUILTIN_PROVIDER_ID)))
        if metadata is None:
            return {"sandbox_base_url": "", "sandbox_domain": "", "region": "", **value}
        return value

    def build_envd_url(self, sandbox_id: str) -> str:
        """构建 envd 数据平面 URL（已实测验证）。

        格式: https://{ENVD_PORT}-{sandbox_id}.{sandbox_domain}
        """
        builder = resolve_provider_schema(BUILTIN_PROVIDER_ID).legacy_url_builder
        if builder is None:
            raise RuntimeError("The distribution does not provide the legacy URL convention.")
        return builder(sandbox_id, self.sandbox_domain)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning empty dict on failure."""
    if not path.is_file():
        return {}
    try:
        try:
            import tomllib  # type: ignore[import-not-found]  # Python 3.11+
        except ImportError:
            import tomli as tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        logger.debug("Loaded config from %s", path)
        return dict(data)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", path, exc)
        return {}


def _read_dotenv(path: Path) -> dict[str, str]:
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    try:
        values = dotenv_values(path)
    except (OSError, ValueError):
        return {}
    return {k: v.strip() for k, v in values.items() if v and v.strip()}


def _dotenv_layers() -> list[dict[str, str]]:
    """Each existing ``.env`` candidate as its own layer (highest priority first)."""
    layers: list[dict[str, str]] = []
    for candidate in _ENV_FILE_CANDIDATES:
        if candidate.is_file():
            logger.debug("Loaded .env from %s", candidate)
            layers.append(_read_dotenv(candidate))
    return layers


def collect_sources(overrides: dict[str, Any] | None = None) -> Sources:
    """Snapshot the live sources (process env, ``.env`` files, ``config.toml``)."""
    return Sources(
        overrides=overrides or {},
        environ=dict(os.environ),
        dotenv=_dotenv_layers(),
        toml=_load_toml_file(_CONFIG_FILE),
    )


def project_dotenv_value(names: tuple[str, ...]) -> str | None:
    """Return the first non-empty *names* entry in the project ``.env``.

    This is the layer between the process environment and ``~/.abx``.
    It does not read ``~/.abx/.env``; callers add that fallback themselves.
    """
    if not _PROJECT_ENV_FILE.is_file():
        return None
    values = _read_dotenv(_PROJECT_ENV_FILE)
    for name in names:
        value = values.get(name)
        if value and value.strip():
            return value.strip()
    return None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _metadata_schema(metadata: dict[str, Any]) -> ProviderSchema:
    return ProviderSchema(
        metadata["id"],
        metadata["keys"],
        metadata["inherit"],
        metadata["derive"],
        metadata["endpoint_defaults"],
        legacy_fields=frozenset(metadata.get("legacy_fields", ())),
        omit_default_options=bool(metadata.get("omit_default_options", False)),
    )


def _builtin_schema() -> ProviderSchema:
    """Compatibility view of the distribution default metadata."""
    return _metadata_schema(DEFAULT_CONFIG)


def provider_schema(provider_id: str) -> ProviderSchema:
    """Configuration is supplied by bundled metadata or the selected provider."""
    metadata = bundled_config(provider_id)
    if metadata is not None:
        return _metadata_schema(metadata)
    return resolve_provider_schema(provider_id)


def select_provider_id(sources: Sources) -> str:
    """Provider selection: explicit > ABX_PROVIDER > ./.env > ~/.abx/.env > [core] > built-in."""
    key = get_key("provider")
    assert key is not None
    res = resolve_key(key, sources)
    assert res is not None
    return str(res.value)


def _normalise_overrides(overrides: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in overrides.items() if k not in ("provider", "provider_options")}


def resolve_all(
    sources: Sources, schema: ProviderSchema | None = None
) -> tuple[ProviderSchema, dict[str, Resolved]]:
    """Resolve every key applicable to the selected provider.

    Returns ``(schema, {key: Resolved})``. Keys that have neither a value nor a default are absent.
    """
    if schema is None:
        schema = provider_schema(select_provider_id(sources))
    out: dict[str, Resolved] = {}
    pid = schema.provider_id

    for key in CORE_KEYS:
        if key.key == "provider":
            continue
        if key.key in GENERIC_ENDPOINT_KEYS and key.key not in schema.inherit:
            continue
        scoped = pid if key.key in GENERIC_ENDPOINT_KEYS else None
        # Defaults of the generic endpoint keys come from the built-in schema only.
        res = resolve_key(
            key,
            sources,
            scoped_for=scoped,
            use_default=key.key not in GENERIC_ENDPOINT_KEYS,
        )
        if res is None and key.key in schema.endpoint_defaults:
            res = Resolved(key.key, schema.endpoint_defaults[key.key], "default", "")
        if res is not None:
            out[key.key] = res
    for key in schema.keys:
        res = resolve_key(key, sources)
        if res is not None:
            out[key.key] = res

    if schema.derive:
        _apply_derive(sources, schema, out)
    return schema, out


def _apply_derive(sources: Sources, schema: ProviderSchema, out: dict[str, Resolved]) -> None:
    """Derive endpoint defaults from other keys (today: ``region``).

    Preserves the historical quirk: when the base URL is explicit by an override or a *process
    environment* variable, nothing is derived (the domain keeps its static default).
    """
    base_key = get_key("sandbox_base_url")
    assert base_key is not None
    if "sandbox_base_url" in schema.inherit:
        explicit = resolve_key(
            base_key,
            Sources(overrides=sources.overrides, environ=sources.environ),
            scoped_for=schema.provider_id,
            use_default=False,
        )
        if explicit is not None:
            return
    for key_name, template in schema.derive.items():
        current = out.get(key_name)
        if current is not None and current.layer != "default":
            continue
        fields = {k: str(v.value) for k, v in out.items() if v.layer != "default"}
        try:
            value = template.format(**fields)
        except (KeyError, IndexError):
            continue
        out[key_name] = Resolved(key_name, value, "derived", "")


def load_config(**overrides: Any) -> TransportConfig:
    """Load transport configuration with layered priority.

    Priority (highest to lowest):

    1. Code-level *overrides* (canonical names)
    2. Environment variables (one name per key)
    3. ``./.env`` then ``~/.abx/.env`` (layer-first)
    4. ``~/.abx/config.toml`` (optional)
    5. Defaults

    A blank or whitespace-only override or environment value is ignored.

    Args:
        **overrides: Code-level overrides (highest priority). ``provider`` selects the provider;
            ``provider_options`` passes provider-scoped values; ``sandbox_api_key`` /
            ``sandbox_base_url`` / ``sandbox_domain`` are the generic endpoint settings.

    Returns:
        Merged TransportConfig instance.
    """
    global _cached_config
    if _cached_config is not None and not overrides:
        return _cached_config

    provider_override = overrides.get("provider")
    options = dict(overrides.get("provider_options") or {})
    ov = _normalise_overrides(overrides)
    if isinstance(provider_override, str) and provider_override.strip():
        ov["provider"] = provider_override.strip()
    core_names = {k.key for k in CORE_KEYS}
    for k, v in options.items():
        if k not in core_names:
            ov.setdefault(k, v)

    sources = collect_sources(ov)
    schema, resolved = resolve_all(sources)

    scoped = {k.key for k in schema.keys}
    unknown = sorted(set(options) - scoped)
    if unknown:
        from agent_sandbox.models.errors import ProviderConfigError

        raise ProviderConfigError(
            f"Unknown option(s) for provider '{schema.provider_id}': {', '.join(unknown)}.",
            suggestion=f"Run 'abx provider info {schema.provider_id}' to list its options.",
        )

    field_names = set(TransportConfig.model_fields) - {"provider", "provider_options"}
    field_scoped = schema.legacy_fields
    values: dict[str, Any] = {"provider": schema.provider_id}
    opts: dict[str, Any] = {}
    for key_name, res in resolved.items():
        if key_name in scoped:
            if key_name in field_scoped:
                values[key_name] = res.value
            elif not schema.omit_default_options or res.layer != "default":
                opts[key_name] = res.value
        elif key_name in field_names:
            values[key_name] = res.value
    values["provider_options"] = {**opts, **{k: v for k, v in options.items() if k in scoped}}

    # A provider with no endpoint metadata never inherits the distribution default.
    values.setdefault("sandbox_base_url", schema.endpoint_defaults.get("sandbox_base_url", ""))
    values.setdefault("sandbox_domain", schema.endpoint_defaults.get("sandbox_domain", ""))
    values.setdefault("region", "")
    config = TransportConfig(**values)

    if not overrides:
        _cached_config = config
    return config


def explain_config(**overrides: Any) -> dict[str, dict[str, Any]]:
    """Describe where every setting of the selected provider comes from.

    Returns ``{key: {"value", "source", "name", "secret"}}``; ``source`` is one of
    ``override``, ``environ``, ``dotenv``, ``toml``, ``derived``, ``default``. Secret values
    are returned masked. Never raises on invalid values (they are reported as unset).
    """
    provider_override = overrides.get("provider")
    ov = _normalise_overrides(overrides)
    if isinstance(provider_override, str) and provider_override.strip():
        ov["provider"] = provider_override.strip()
    schema, resolved = resolve_all(collect_sources(ov))
    all_keys = {k.key: k for k in (*CORE_KEYS, *schema.keys)}
    info: dict[str, dict[str, Any]] = {
        "provider": {"value": schema.provider_id, "source": "n/a", "name": "", "secret": False}
    }
    for name, res in resolved.items():
        key = all_keys.get(name)
        secret = bool(key and key.secret)
        info[name] = {
            "value": mask_secret(str(res.value)) if secret else res.value,
            "source": res.layer,
            "name": res.name,
            "secret": secret,
        }
    return info


def mask_secret(value: str) -> str:
    """Mask a secret for display (keeps the last 4 characters of long values)."""
    if len(value) <= 8:
        return "****"
    return "****" + value[-4:]


def reset_config() -> None:
    """Clear the cached configuration (useful for testing)."""
    global _cached_config
    _cached_config = None


def http_timeout_configured() -> bool:
    """Return True when the user explicitly configured ``http_timeout``.

    Checks the same sources and names as :func:`load_config` (canonical
    ``ABX_HTTP_TIMEOUT`` in the environment, ``.env`` files and
    ``~/.abx/config.toml``) without applying defaults. The CLI uses this to decide whether a slow
    operation (e.g. sandbox create) should get a longer built-in HTTP timeout instead of the 30s
    default.
    """
    key = get_key("http_timeout")
    assert key is not None
    return resolve_key(key, collect_sources(), use_default=False) is not None


# ---------------------------------------------------------------------------
# Audit and migration
# ---------------------------------------------------------------------------


def _legacy_env_index() -> dict[str, tuple[ConfigKey, str]]:
    idx: dict[str, tuple[ConfigKey, str]] = {}
    for key in (*CORE_KEYS, *BUNDLED_KEYS):
        for a in key.aliases:
            if a.surface == "env" and a.kind == "legacy":
                idx[a.name] = (key, a.kind)
    return idx


def _toml_legacy_index() -> dict[str, ConfigKey]:
    idx: dict[str, ConfigKey] = {}
    for key in (*CORE_KEYS, *BUNDLED_KEYS):
        for a in key.aliases:
            if a.surface in ("config", "kwarg") and a.kind == "legacy":
                idx.setdefault(a.name, key)
    return idx


def audit_data(
    environ: dict[str, str], dotenv: list[tuple[str, dict[str, str]]], toml: dict[str, Any]
) -> list[dict[str, str]]:
    """Pure audit: every *legacy* name in use (names only, never values).

    ``compat`` (E2B_*) and ``native`` names are never reported.
    """
    findings: list[dict[str, str]] = []
    env_idx = _legacy_env_index()

    def env_entry(where: str, name: str, path: str = "") -> None:
        key, kind = env_idx[name]
        item = {
            "where": where,
            "name": name,
            "canonical_key": key.key,
            "canonical_name": key.env,
            "kind": kind,
        }
        if path:
            item["path"] = path
        findings.append(item)

    for name in sorted(environ):
        if name in env_idx and environ[name].strip():
            env_entry("env", name)
    for path, values in dotenv:
        for name in sorted(values):
            if name in env_idx and values[name].strip():
                env_entry("dotenv", name, path)
    toml_idx = _toml_legacy_index()
    transport = toml.get("transport")
    if isinstance(transport, dict):
        for name in sorted(transport):
            key = toml_idx.get(name)
            if key is not None and name != key.key:
                findings.append(
                    {
                        "where": "config",
                        "name": f"transport.{name}",
                        "canonical_key": key.key,
                        "canonical_name": f"transport.{key.key}",
                        "kind": "legacy",
                    }
                )
    return findings


def audit_config() -> list[dict[str, str]]:
    """Legacy names currently in use (process env, ``.env`` files, ``config.toml``)."""
    dotenv = [(str(c), _read_dotenv(c)) for c in _ENV_FILE_CANDIDATES if c.is_file()]
    return audit_data(dict(os.environ), dotenv, _load_toml_file(_CONFIG_FILE))


def plan_migration_data(toml: dict[str, Any], env: dict[str, str]) -> list[dict[str, Any]]:
    """Pure migration plan from stored legacy names to canonical ones (``config_format = 2``).

    Item shape: ``{"file": "toml"|"env", "action": "rename"|"drop"|"set", "from", "to"}``.
    ``drop`` removes a stale legacy entry whose canonical name already exists (or that is
    shadowed by a higher-priority legacy name). The result is deterministic.
    """
    plan: list[dict[str, Any]] = []
    transport = toml.get("transport")
    planned_targets: set[str] = set()
    if isinstance(transport, dict):
        for key in CORE_KEYS:
            if key.toml_section != "transport" and key.key != "sandbox_api_key":
                continue
            target = f"transport.{key.key}"
            for name in dict.fromkeys([*key.alias_names("config"), *key.alias_names("kwarg")]):
                if name == key.key or name not in transport:
                    continue
                dup = key.key in transport or target in planned_targets
                planned_targets.add(target)
                plan.append(
                    {
                        "file": "toml",
                        "action": "drop" if dup else "rename",
                        "from": f"transport.{name}",
                        "to": target,
                    }
                )
        providers = toml.get("providers")
        for metadata in BUNDLED_CONFIGS:
            prov_table = providers.get(metadata["id"]) if isinstance(providers, dict) else None
            for key in metadata["keys"]:
                p2 = key.storage_phase2
                if key.key in transport and p2 is not None and p2.file == "toml":
                    exists = isinstance(prov_table, dict) and key.key in prov_table
                    plan.append(
                        {
                            "file": "toml",
                            "action": "drop" if exists else "rename",
                            "from": f"transport.{key.key}",
                            "to": f"providers.{metadata['id']}.{key.key}",
                        }
                    )
    for key in (*CORE_KEYS, *BUNDLED_KEYS):
        p2 = key.storage_phase2
        target_env = p2.name if p2 and p2.file == "env" else key.env
        # Native names (OPENAI_*, DASHSCOPE_*) are user-owned: only the names that
        # ``config set`` wrote in phase 1 and the legacy names move.
        movable = {a.name for a in key.aliases if a.surface == "env" and a.kind == "legacy"}
        if key.storage_phase1 is not None and key.storage_phase1.file == "env":
            movable.add(key.storage_phase1.name)
        ordered = [
            n for n in env_names(key) if n in movable and n != target_env and env.get(n, "").strip()
        ]
        target_present = bool(env.get(target_env, "").strip())
        for i, name in enumerate(ordered):
            plan.append(
                {
                    "file": "env",
                    "action": "rename" if (i == 0 and not target_present) else "drop",
                    "from": name,
                    "to": target_env,
                }
            )
    plan.append(
        {"file": "toml", "action": "set", "from": None, "to": "core.config_format", "value": 2}
    )
    return plan


def plan_migration(
    config_path: Path | None = None, env_path: Path | None = None
) -> list[dict[str, Any]]:
    """Migration plan for the user's files (defaults: ``config.toml`` and the sibling ``.env``)."""
    cfg = config_path or _CONFIG_FILE
    env_file = env_path or cfg.parent / ".env"
    env = _read_dotenv(env_file) if env_file.is_file() else {}
    return plan_migration_data(_load_toml_file(cfg), env)


def apply_migration(
    config_path: Path | None = None, env_path: Path | None = None, *, backup: bool = True
) -> list[dict[str, Any]]:
    """Execute :func:`plan_migration`; keeps ``config.toml.bak`` / ``.env.bak`` (0600)."""
    from agent_sandbox.utils.toml_write import dumps_toml

    cfg = config_path or _CONFIG_FILE
    env_file = env_path or cfg.parent / ".env"
    plan = plan_migration(cfg, env_file)
    toml = _load_toml_file(cfg)
    env_lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.is_file() else []

    def secure_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)

    if backup:
        if cfg.is_file():
            secure_write(cfg.with_name(cfg.name + ".bak"), cfg.read_text(encoding="utf-8"))
        if env_file.is_file():
            secure_write(
                env_file.with_name(env_file.name + ".bak"), env_file.read_text(encoding="utf-8")
            )

    def pop_path(doc: dict[str, Any], dotted: str) -> Any:
        parts = dotted.split(".")
        node: Any = doc
        for p in parts[:-1]:
            node = node.get(p)
            if not isinstance(node, dict):
                return None
        return node.pop(parts[-1], None)

    def set_path(doc: dict[str, Any], dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = doc
        for p in parts[:-1]:
            nxt = node.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                node[p] = nxt
            node = nxt
        node[parts[-1]] = value

    for item in plan:
        if item["file"] != "toml":
            continue
        if item["action"] == "set":
            set_path(toml, item["to"], item["value"])
        else:
            value = pop_path(toml, item["from"])
            if item["action"] == "rename" and value is not None:
                set_path(toml, item["to"], value)

    moved_from_transport = any(
        i["file"] == "toml" and str(i.get("from") or "").startswith("transport.") for i in plan
    )
    if moved_from_transport and toml.get("transport") == {}:
        del toml["transport"]

    env_plan = {i["from"]: i for i in plan if i["file"] == "env"}
    if env_plan:
        new_lines: list[str] = []
        for line in env_lines:
            stripped = line.strip()
            body = stripped[len("export ") :] if stripped.startswith("export ") else stripped
            name = (
                body.split("=", 1)[0].strip()
                if "=" in body and not stripped.startswith("#")
                else ""
            )
            item_ = env_plan.get(name)
            if item_ is None:
                new_lines.append(line)
            elif item_["action"] == "rename":
                new_lines.append(line.replace(name, item_["to"], 1))
        env_lines = new_lines
    if env_plan:
        secure_write(env_file, "\n".join(env_lines) + ("\n" if env_lines else ""))
    secure_write(cfg, dumps_toml(toml))
    reset_config()
    return plan


__all__ = [
    "ENVD_PORT",
    "TransportConfig",
    "apply_migration",
    "audit_config",
    "audit_data",
    "collect_sources",
    "explain_config",
    "http_timeout_configured",
    "load_config",
    "mask_secret",
    "plan_migration",
    "plan_migration_data",
    "project_dotenv_value",
    "provider_env_name",
    "reset_config",
    "resolve_all",
    "select_provider_id",
]
