"""Canonical configuration-key registry and the pure layered resolver.

This module is the executable form of ``docs/en/design/providers-and-credentials.md``.
It knows every configuration key (one canonical name, one environment variable,
one storage name) and resolves a key against injected *sources*
(overrides, process environment, dotenv files, ``config.toml``) without touching
the filesystem or ``os.environ``. The Node.js CLI implements the same algorithm
and runs the same JSON vectors (``tests/fixtures/*.json``).

Resolution is **layer-first**: layers are tried in order (overrides, process
environment, each dotenv file, ``config.toml``, default) and inside a layer the
names are tried most-specific first. A blank or whitespace-only value is unset.

Run ``python -m agent_sandbox.utils.config_keys --json`` to print the schema export
(the contract with the CLI).
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

BUILTIN_PROVIDER_ID = "alicloud-express"
BUILTIN_PROVIDER_NAME = "Alibaba Cloud Express Edition"
BUILTIN_PROVIDER_NAME_ZH = "阿里云极速版"

GENERIC_ENDPOINT_KEYS = ("sandbox_api_key", "sandbox_base_url", "sandbox_domain")

PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

RESERVED_PROVIDER_IDS = (
    "alicloud-express",
    "default",
    "all",
    "none",
    "builtin",
    "shortcuts",
    "core",
    "transport",
    "providers",
)
RESERVED_PROVIDER_PREFIXES = ("abx-", "alicloud-", "shortcuts")
# Official catalog ids. alicloud-express stays reserved; these are installed
# from registry.agent-sandbox.cn, not compiled into the SDK.
OFFICIAL_CATALOG_IDS = frozenset({"opensandbox", "cubesandbox", "e2b", "alicloud-container"})

KEY_TYPES = ("str", "url", "int", "float", "bool", "enum", "path", "csv")
ALIAS_KINDS = ("native",)
ALIAS_SURFACES = ("env", "config", "kwarg", "flag")

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


@dataclass(frozen=True)
class Alias:
    """An alternative name of a key on one surface."""

    name: str
    kind: str  # compat | native | legacy
    surface: str  # env | config | kwarg | flag


@dataclass(frozen=True)
class Storage:
    """Where ``config set`` writes a key (``env`` = ``~/.abx/.env``, ``toml`` = config.toml)."""

    file: str
    name: str
    section: str | None = None


@dataclass(frozen=True)
class ConfigKey:
    """One configuration key."""

    key: str
    scope: str = "core"  # "core" or a provider id
    type: str = "str"
    secret: bool = False
    credential: bool = False
    required: bool = False
    default: Any = None
    group: str = ""
    description: str = ""
    description_zh: str = ""
    aliases: tuple[Alias, ...] = ()
    storage: Storage | None = None
    choices: tuple[str, ...] = ()
    settable: bool = True
    env_override: str | None = None
    toml_section: str | None = None

    @property
    def env(self) -> str:
        """Canonical environment variable name."""
        if self.env_override:
            return self.env_override
        if self.scope == "core":
            return f"ABX_{self.key.upper()}"
        return provider_env_name(self.scope, self.key)

    def alias_names(self, surface: str, *kinds: str) -> tuple[str, ...]:
        return tuple(
            a.name for a in self.aliases if a.surface == surface and (not kinds or a.kind in kinds)
        )


def provider_env_prefix(provider_id: str) -> str:
    return "ABX_" + provider_id.upper().replace("-", "_") + "_"


def provider_env_name(provider_id: str, key: str) -> str:
    return provider_env_prefix(provider_id) + key.upper()


def validate_provider_id(provider_id: str) -> str | None:
    """Return an error message when *provider_id* is not a valid third-party id."""
    if not (2 <= len(provider_id) <= 40) or not PROVIDER_ID_RE.match(provider_id):
        return (
            "provider id must be 2-40 chars of lowercase letters, digits and single "
            "hyphens, starting with a letter"
        )
    if provider_id in OFFICIAL_CATALOG_IDS:
        return None
    if provider_id in RESERVED_PROVIDER_IDS or provider_id.startswith(RESERVED_PROVIDER_PREFIXES):
        return f"provider id '{provider_id}' is reserved"
    return None


_G_CONN = "Connection"
_G_AUTH = "Sandbox authentication"
_G_ALI = "Alibaba Cloud credentials"
_G_INT = "Integrations"
_G_PROV = "Provider"

_BASE_URL_DEFAULT = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
_DOMAIN_DEFAULT = "cn-hangzhou.e2b.fc.aliyuncs.com"

CORE_KEYS: tuple[ConfigKey, ...] = (
    ConfigKey(
        "provider",
        group=_G_PROV,
        default=BUILTIN_PROVIDER_ID,
        description="Default provider id (see 'abx provider list')",
        description_zh="默认 provider 标识（见 'abx provider list'）",
        storage=Storage("toml", "provider", "core"),
        toml_section="core",
    ),
    ConfigKey(
        "sandbox_api_key",
        secret=True,
        credential=True,
        group=_G_AUTH,
        description="Agent Sandbox API key of the active provider",
        description_zh="当前 provider 的 Agent Sandbox API Key",
        storage=Storage("env", "ABX_SANDBOX_API_KEY"),
    ),
    ConfigKey(
        "sandbox_base_url",
        type="url",
        group=_G_CONN,
        default=_BASE_URL_DEFAULT,
        description="Agent Sandbox API endpoint of the active provider",
        description_zh="当前 provider 的 Agent Sandbox API 端点",
        storage=Storage("toml", "sandbox_base_url", "transport"),
        toml_section="transport",
    ),
    ConfigKey(
        "sandbox_domain",
        group=_G_CONN,
        default=_DOMAIN_DEFAULT,
        description="Envd data-plane domain",
        description_zh="envd 数据面域名",
        storage=Storage("toml", "sandbox_domain", "transport"),
        toml_section="transport",
    ),
    ConfigKey(
        "http_timeout",
        type="float",
        group=_G_CONN,
        default=30.0,
        description="HTTP request timeout in seconds",
        description_zh="HTTP 请求超时（秒）",
        storage=Storage("toml", "http_timeout", "transport"),
        toml_section="transport",
    ),
    ConfigKey(
        "http2",
        type="bool",
        group=_G_CONN,
        default=True,
        description="Use HTTP/2",
        description_zh="启用 HTTP/2",
        storage=Storage("toml", "http2", "transport"),
        toml_section="transport",
    ),
    ConfigKey("max_connections", type="int", default=100, settable=False, toml_section="transport"),
    ConfigKey(
        "max_keepalive_connections",
        type="int",
        default=20,
        settable=False,
        toml_section="transport",
    ),
    ConfigKey(
        "keepalive_expiry", type="float", default=30.0, settable=False, toml_section="transport"
    ),
    ConfigKey(
        "ws_ping_interval", type="float", default=30.0, settable=False, toml_section="transport"
    ),
    ConfigKey(
        "log_level",
        type="enum",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="WARNING",
        description="Log level",
        description_zh="日志级别",
        storage=Storage("toml", "log_level", "transport"),
        toml_section="transport",
    ),
    ConfigKey(
        "default_template",
        default="base",
        description="Template used when none is given",
        description_zh="未指定模板时使用的模板",
        storage=Storage("toml", "default_template", "transport"),
        toml_section="transport",
    ),
    ConfigKey(
        "github_token",
        secret=True,
        group=_G_INT,
        description="GitHub token for the template index",
        description_zh="用于模板索引的 GitHub Token",
        env_override="GITHUB_TOKEN",
        storage=Storage("env", "GITHUB_TOKEN"),
    ),
    ConfigKey("template_index_url", type="url", settable=False),
    ConfigKey("template_dir", type="path", settable=False),
    ConfigKey("mcp_auth_token", secret=True, settable=False),
    ConfigKey("mcp_allowed_origins", settable=False),
    ConfigKey("mcp_runtime_dir", type="path", settable=False),
)

_ALI = BUILTIN_PROVIDER_ID


def _ali(
    key: str,
    *,
    storage: Storage | None = None,
    env_override: str | None = None,
    **kw: Any,
) -> ConfigKey:
    """One provider key.

    ``env_override`` is the only environment variable when the vendor already has a name.
    """
    storage1 = storage or Storage("toml", key, "providers." + _ALI)
    if env_override and storage1.file == "env":
        storage2 = Storage("env", env_override)
    elif storage1.file == "env":
        storage2 = Storage("env", provider_env_name(_ALI, key))
    else:
        storage2 = storage1
    return ConfigKey(
        key,
        scope=_ALI,
        aliases=(),
        env_override=env_override,
        storage=storage2,
        **kw,
    )


ALICLOUD_EXPRESS_KEYS: tuple[ConfigKey, ...] = (
    _ali(
        "region",
        default="cn-hangzhou",
        group=_G_CONN,
        env_override="ALIBABA_CLOUD_REGION_ID",
        storage=Storage("toml", "region", "transport"),
        description="Region id (derives the API URL and domain)",
        description_zh="地域（用于推导 API 地址和域名）",
    ),
    _ali(
        "access_key_id",
        credential=True,
        group=_G_ALI,
        env_override="ALICLOUD_ACCESS_KEY_ID",
        storage=Storage("env", "ALICLOUD_ACCESS_KEY_ID"),
        description="Alibaba Cloud AccessKey ID",
        description_zh="阿里云 AccessKey ID",
    ),
    _ali(
        "access_key_secret",
        secret=True,
        credential=True,
        group=_G_ALI,
        env_override="ALICLOUD_ACCESS_KEY_SECRET",
        storage=Storage("env", "ALICLOUD_ACCESS_KEY_SECRET"),
        description="Alibaba Cloud AccessKey secret",
        description_zh="阿里云 AccessKey Secret",
    ),
)

_BY_KEY: dict[tuple[str, str], ConfigKey] = {}
for _k in (*CORE_KEYS, *ALICLOUD_EXPRESS_KEYS):
    _BY_KEY[(_k.scope, _k.key)] = _k

CORE_KEY_NAMES = tuple(k.key for k in CORE_KEYS)

#: Core keys whose value reaches every provider (non-secret tuning).
TUNING_KEYS = (
    "http_timeout",
    "http2",
    "max_connections",
    "max_keepalive_connections",
    "keepalive_expiry",
    "ws_ping_interval",
)


def get_key(key: str, scope: str = "core") -> ConfigKey | None:
    return _BY_KEY.get((scope, key))


def builtin_keys() -> tuple[ConfigKey, ...]:
    return ALICLOUD_EXPRESS_KEYS


def find_key_by_alias(name: str, surface: str) -> ConfigKey | None:
    """Look up a core key by canonical name or by an alias on *surface*."""
    for k in CORE_KEYS:
        if k.key == name:
            return k
    for k in (*CORE_KEYS, *ALICLOUD_EXPRESS_KEYS):
        if name in k.alias_names(surface):
            return k
    return None


# ---------------------------------------------------------------- resolver


@dataclass
class Sources:
    """Injected configuration sources (all plain data)."""

    overrides: Mapping[str, Any] = field(default_factory=dict)
    environ: Mapping[str, str] = field(default_factory=dict)
    dotenv: Sequence[Mapping[str, str]] = ()
    toml: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Resolved:
    key: str
    value: Any
    layer: str  # override | environ | dotenv | toml | default
    name: str  # the concrete name that supplied the value ("" for default)
    layer_index: int = 0  # dotenv file index


def coerce(key: ConfigKey, raw: Any) -> Any | None:
    """Coerce *raw* to the key's type; ``None`` means unset/invalid (blank, bad number)."""
    if raw is None:
        return None
    t = key.type
    if isinstance(raw, (list, tuple)):
        return ",".join(str(x) for x in raw) or None if t == "csv" else None
    if t == "bool" and isinstance(raw, bool):
        return raw
    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if isinstance(raw, bool):
        text = text.lower()
    if not text:
        return None
    try:
        if t == "float":
            return float(text)
        if t == "int":
            return int(float(text)) if re.fullmatch(r"[+-]?\d+\.0*", text) else int(text)
        if t == "bool":
            low = text.lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            return None
        if t == "enum" and key.choices:
            return text.upper() if text.upper() in key.choices else None
    except ValueError:
        return None
    return text


def env_names(key: ConfigKey, *, scoped_for: str | None = None) -> tuple[str, ...]:
    """Environment names for *key*, most specific first.

    *scoped_for* adds the provider-scoped override name for an inherited core key.
    """
    names: list[str] = []
    if scoped_for and key.scope == "core":
        names.append(provider_env_name(scoped_for, key.key))
    names.append(key.env)
    names.extend(a.name for a in key.aliases if a.surface == "env" and a.kind == "native")
    seen: dict[str, None] = {}
    for n in names:
        seen.setdefault(n)
    return tuple(seen)


def _toml_lookups(
    key: ConfigKey, toml: Mapping[str, Any], scoped_for: str | None
) -> list[tuple[str, Any]]:
    """(display name, raw value) candidates inside a TOML document, most specific first."""
    if key.secret or (key.storage is not None and key.storage.file == "env"):
        return []
    out: list[tuple[str, Any]] = []
    providers = toml.get("providers")
    prov_scope = key.scope if key.scope != "core" else scoped_for
    if prov_scope and isinstance(providers, Mapping):
        table = providers.get(prov_scope)
        if isinstance(table, Mapping) and key.key in table:
            out.append((f"providers.{prov_scope}.{key.key}", table[key.key]))
    if key.scope == "core":
        section = key.toml_section or "transport"
    elif key.scope == BUILTIN_PROVIDER_ID:
        section = "transport"
    else:
        return out
    names = [key.key, *key.alias_names("config"), *key.alias_names("kwarg")]
    # Phase-1 storage names (e.g. ``api_url``) are already among the config aliases.
    names = list(dict.fromkeys(names))
    table_obj = toml.get(section)
    if isinstance(table_obj, Mapping):
        for n in names:
            if n in table_obj:
                out.append((f"{section}.{n}", table_obj[n]))
    return out


def override_names(key: ConfigKey) -> tuple[str, ...]:
    return tuple(dict.fromkeys([key.key, *key.alias_names("kwarg")]))


def resolve_key(
    key: ConfigKey,
    sources: Sources,
    *,
    scoped_for: str | None = None,
    use_default: bool = True,
) -> Resolved | None:
    """Resolve *key*; ``None`` when nothing is set and no default applies.

    *scoped_for* names the provider whose ``[providers.<id>]`` table / ``ABX_<ID>_<KEY>``
    variable may override an inherited core key.
    """
    # 1. overrides
    for name in override_names(key):
        if name in sources.overrides:
            val = coerce(key, sources.overrides[name])
            if val is not None:
                return Resolved(key.key, val, "override", name)
    names = env_names(key, scoped_for=scoped_for)
    # 2. process environment
    for name in names:
        if name in sources.environ:
            val = coerce(key, sources.environ[name])
            if val is not None:
                return Resolved(key.key, val, "environ", name)
    # 3. dotenv files (each file its own layer, in order)
    for idx, env_map in enumerate(sources.dotenv):
        for name in names:
            if name in env_map:
                val = coerce(key, env_map[name])
                if val is not None:
                    return Resolved(key.key, val, "dotenv", name, idx)
    # 4. config.toml
    for name, raw in _toml_lookups(key, sources.toml, scoped_for):
        val = coerce(key, raw)
        if val is not None:
            return Resolved(key.key, val, "toml", name)
    if use_default and key.default is not None:
        return Resolved(key.key, key.default, "default", "")
    return None


def resolve_provider_id(sources: Sources) -> Resolved:
    """Resolve the *provider* key (explicit > env > dotenv > ``[core]`` > built-in)."""
    key = _BY_KEY[("core", "provider")]
    res = resolve_key(key, sources)
    assert res is not None
    return res


def export_schema(extra_provider_keys: Sequence[ConfigKey] = ()) -> dict[str, Any]:
    """Language-neutral schema export (``config-keys.json``)."""

    def storage(s: Storage | None) -> dict[str, Any] | None:
        if s is None:
            return None
        d: dict[str, Any] = {"file": s.file, "name": s.name}
        if s.section:
            d["section"] = s.section
        return d

    def rec(k: ConfigKey) -> dict[str, Any]:
        return {
            "key": k.key,
            "scope": k.scope,
            "type": k.type,
            "secret": k.secret,
            "credential": k.credential,
            "settable": k.settable,
            "env": k.env,
            "aliases": [{"name": a.name, "kind": a.kind, "surface": a.surface} for a in k.aliases],
            "env_names": list(env_names(k)),
            "toml_section": k.toml_section,
            "storage": storage(k.storage),
            "default": k.default,
            "choices": list(k.choices),
            "group": k.group,
            "description": k.description,
        }

    return {
        "schema_version": 1,
        "builtin_provider": {
            "id": BUILTIN_PROVIDER_ID,
            "name": BUILTIN_PROVIDER_NAME,
            "name_zh": BUILTIN_PROVIDER_NAME_ZH,
        },
        "reserved_provider_ids": list(RESERVED_PROVIDER_IDS),
        "reserved_provider_prefixes": list(RESERVED_PROVIDER_PREFIXES),
        "generic_endpoint_keys": list(GENERIC_ENDPOINT_KEYS),
        "tuning_keys": list(TUNING_KEYS),
        "keys": [rec(k) for k in (*CORE_KEYS, *ALICLOUD_EXPRESS_KEYS, *extra_provider_keys)],
    }


def _main(argv: Sequence[str]) -> int:
    if "--json" in argv:
        sys.stdout.write(json.dumps(export_schema(), indent=2, ensure_ascii=False) + "\n")
        return 0
    sys.stderr.write("usage: python -m agent_sandbox.utils.config_keys --json\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
