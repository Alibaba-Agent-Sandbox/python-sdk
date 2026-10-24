"""``abx-provider.toml`` manifest: parsing, validation and version comparison."""

from __future__ import annotations

import copy
import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from packaging.version import Version

from agent_sandbox.models.errors import ProviderManifestError, ProviderVersionError
from agent_sandbox.providers.base import FEATURES, ConfigField
from agent_sandbox.utils.config_keys import (
    CORE_KEY_NAMES,
    FIELD_KEY_RE,
    GENERIC_ENDPOINT_KEYS,
    validate_provider_id,
)

if TYPE_CHECKING:
    from pathlib import Path

MANIFEST_NAME = "abx-provider.toml"
MANIFEST_MAX_BYTES = 256 * 1024
SUPPORTED_PROTOCOLS = {"exec": "epp/1", "rest": "e2b-rest/1", "node": "node/1"}
FIELD_TYPES = ("string", "int", "float", "bool", "enum", "path", "url", "csv")
_FIELD_TYPE_TO_KEY_TYPE = {"string": "str"}
FILESYSTEM_SCOPES = ("data_dir", "cwd", "home", "any")
_FORBIDDEN_ENV_PREFIXES = ("ABX_", "E2B_", "ALICLOUD_")
_FORBIDDEN_LAUNCHERS = (".bat", ".cmd", ".ps1")
COMMAND_PROTOCOL = "provider-commands/1"
COMMAND_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
COMMAND_MAX_BYTES = 64 * 1024
COMMAND_MAX_DEPTH = 16
_FORBIDDEN_SCHEMA_KEYS = {
    "$ref",
    "$dynamicRef",
    "$recursiveRef",
    "$id",
    "$async",
    "pattern",
    "patternProperties",
    "format",
}
_FORBIDDEN_JSON_KEYS = {"__proto__", "prototype", "constructor"}


@dataclass(frozen=True)
class ProviderCommand:
    """A provider management operation, independent of sandbox runtime commands."""

    id: str
    description: str
    description_zh: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    effect: Literal["read", "write", "delete"]
    idempotent: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the wire descriptor without exposing mutable manifest schemas."""
        return copy.deepcopy(
            {
                "id": self.id,
                "description": self.description,
                "description_zh": self.description_zh,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
                "effect": self.effect,
                "idempotent": self.idempotent,
            }
        )


@dataclass(frozen=True)
class Manifest:
    """A validated provider manifest."""

    id: str
    name: str
    name_zh: str
    version: str
    description: str
    kind: str  # exec | rest | node
    protocol: str
    requires: dict[str, str]
    command: tuple[str, ...]
    startup_timeout_ms: int
    call_timeout_ms: int
    platforms: tuple[str, ...]
    features: tuple[str, ...]
    operation_contract_version: int
    operations: dict[str, tuple[str, ...]]
    workflow_inputs: tuple[str, ...]
    startup_modes: tuple[str, ...]
    security: dict[str, Any]
    inherit: tuple[str, ...]
    auth_any_of: tuple[tuple[str, ...], ...]
    fields: tuple[ConfigField, ...]
    endpoint: dict[str, Any]
    license: str = ""
    homepage: str = ""
    sha256: str = ""
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
    commands: tuple[ProviderCommand, ...] = ()

    def to_summary(self) -> dict[str, Any]:
        """Fields shown in the consent screen and compared on update."""
        return {
            "runtime": list(self.command)
            if self.kind == "exec"
            else ["node", *(self.command or ("provider.mjs",))]
            if self.kind == "node"
            else ["rest", self.endpoint.get("base_url", "")],
            "security": self.security,
            "features": sorted(self.features),
            "operation_contract_version": self.operation_contract_version,
            "operations": {k: sorted(v) for k, v in self.operations.items()},
            "workflow_inputs": sorted(self.workflow_inputs),
            "startup_modes": sorted(self.startup_modes),
            "inherit": sorted(self.inherit),
            "fields": sorted(f.key for f in self.fields),
            "commands": [c.to_dict() for c in sorted(self.commands, key=lambda c: c.id)],
        }


# ---------------------------------------------------------------- versions


def version_satisfies(version: str, spec: str) -> bool:
    """Whether *version* satisfies a comma-separated AND list of comparators.

    Operators: ``>= <= > < == != ~=``. An empty spec matches everything.
    """
    have = Version(version)
    for raw in spec.split(","):
        part = raw.strip()
        if not part:
            continue
        m = re.match(r"^(>=|<=|==|!=|~=|>|<)\s*(.+)$", part)
        if not m:
            raise ValueError(f"invalid version comparator '{part}'")
        op, rhs_text = m.group(1), m.group(2)
        rhs = Version(rhs_text)
        c = (have > rhs) - (have < rhs)
        if op == ">=" and c < 0:
            return False
        if op == "<=" and c > 0:
            return False
        if op == ">" and c <= 0:
            return False
        if op == "<" and c >= 0:
            return False
        if op == "==" and c != 0:
            return False
        if op == "!=" and c == 0:
            return False
        if op == "~=":
            nums = rhs.release
            head = nums[:-1] if len(nums) > 1 else nums
            upper = Version(".".join(str(p) for p in (*head[:-1], head[-1] + 1)))
            if c < 0 or have >= upper:
                return False
    return True


def check_requires(manifest: Manifest, *, component: str, host_version: str) -> None:
    """Raise :class:`ProviderVersionError` unless this host satisfies ``compat.requires``."""
    spec = manifest.requires.get(component, "")
    if spec and not version_satisfies(host_version, spec):
        raise ProviderVersionError(
            f"Provider '{manifest.id}' requires {component} {spec} (this is {host_version}).",
            suggestion="Upgrade agent-sandbox/abx or install a compatible provider version.",
        )


# ---------------------------------------------------------------- parsing


def _toml_loads(data: bytes) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - Python < 3.11
        import tomli as tomllib
    try:
        return dict(tomllib.loads(data.decode("utf-8")))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ProviderManifestError(f"Invalid {MANIFEST_NAME}: {exc}.") from exc


def _err(msg: str) -> ProviderManifestError:
    return ProviderManifestError(f"Invalid {MANIFEST_NAME}: {msg}.")


def _table(doc: dict[str, Any], name: str, *, required: bool = False) -> dict[str, Any]:
    val = doc.get(name)
    if val is None:
        if required:
            raise _err(f"missing [{name}] table")
        return {}
    if not isinstance(val, dict):
        raise _err(f"[{name}] must be a table")
    return val


def _str(
    tbl: dict[str, Any], key: str, where: str, *, required: bool = False, default: str = ""
) -> str:
    val = tbl.get(key, default)
    if val is None or val == "" and required:
        raise _err(f"{where}.{key} is required")
    if not isinstance(val, str):
        raise _err(f"{where}.{key} must be a string")
    if required and not val.strip():
        raise _err(f"{where}.{key} is required")
    return val


def _str_list(tbl: dict[str, Any], key: str, where: str) -> list[str]:
    val = tbl.get(key, [])
    if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
        raise _err(f"{where}.{key} must be an array of strings")
    return list(val)


def _bounded_json(value: Any, *, depth: int = 0) -> None:
    if depth > COMMAND_MAX_DEPTH:
        raise _err("commands entry exceeds depth 16")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or key in _FORBIDDEN_JSON_KEYS:
                raise _err("commands entries contain an invalid or forbidden JSON key")
            _bounded_json(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            _bounded_json(child, depth=depth + 1)
    elif value is not None and not isinstance(value, str | int | float | bool):
        raise _err("commands entries must contain JSON values")


def _schema(value: Any, *, name: str, input_schema: bool = False) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _err(f"{name} must be a schema object")
    if input_schema and (
        value.get("type") != "object" or value.get("additionalProperties") is not False
    ):
        raise _err(f"{name} must declare type object and additionalProperties = false")

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if _FORBIDDEN_SCHEMA_KEYS.intersection(node):
            raise _err(
                f"{name} may not use references, ids, asynchronous schemas, patterns or formats"
            )
        if "$schema" in node and node["$schema"] != "http://json-schema.org/draft-07/schema#":
            raise _err(f"{name} must use JSON Schema draft 7")
        for key in ("properties", "definitions", "$defs"):
            children = node.get(key)
            if isinstance(children, dict):
                for child in children.values():
                    visit(child)
        for key in (
            "items",
            "additionalItems",
            "additionalProperties",
            "propertyNames",
            "contains",
            "not",
            "if",
            "then",
            "else",
        ):
            child = node.get(key)
            if isinstance(child, list):
                for item in child:
                    visit(item)
            else:
                visit(child)
        for key in ("allOf", "anyOf", "oneOf"):
            children = node.get(key)
            if isinstance(children, list):
                for child in children:
                    visit(child)
        dependencies = node.get("dependencies")
        if isinstance(dependencies, dict):
            for child in dependencies.values():
                visit(child)

    visit(value)
    return value


def _parse_commands(doc: dict[str, Any], kind: str) -> tuple[ProviderCommand, ...]:
    if "commands" not in doc:
        return ()
    commands = _table(doc, "commands")
    if commands.get("protocol") != COMMAND_PROTOCOL:
        raise _err(f"commands.protocol must be '{COMMAND_PROTOCOL}'")
    entries = commands.get("entries")
    if not isinstance(entries, list) or len(entries) > 128:
        raise _err("commands.entries must be an array of at most 128 entries")
    if entries and kind not in ("node", "exec"):
        raise _err("only node and exec providers may declare commands")
    result: list[ProviderCommand] = []
    seen: set[str] = set()
    keys = {
        "id",
        "description",
        "description_zh",
        "input_schema",
        "output_schema",
        "effect",
        "idempotent",
    }
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - keys:
            raise _err("commands entry must be a descriptor with known fields")
        _bounded_json(entry)
        try:
            size = len(
                json.dumps(
                    entry, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode("utf-8")
            )
        except (ValueError, TypeError) as exc:
            raise _err("commands entry must contain finite JSON values") from exc
        if size > COMMAND_MAX_BYTES:
            raise _err("commands entry exceeds 64 KiB")
        cid = entry.get("id")
        if not isinstance(cid, str) or len(cid) > 80 or not COMMAND_ID_RE.fullmatch(cid):
            raise _err(
                "commands entry id must be a lowercase operation id of at most 80 characters"
            )
        if cid in seen:
            raise _err(f"duplicate commands entry '{cid}'")
        seen.add(cid)
        if entry.get("effect") not in ("read", "write", "delete"):
            raise _err(f"commands.{cid}.effect must be read, write or delete")
        if not isinstance(entry.get("idempotent"), bool):
            raise _err(f"commands.{cid}.idempotent must be a boolean")
        for description in ("description", "description_zh"):
            if not _str(entry, description, f"commands.{cid}", required=True).strip():
                raise _err(f"commands.{cid}.{description} must not be blank")
        result.append(
            ProviderCommand(
                id=cid,
                description=_str(entry, "description", f"commands.{cid}", required=True),
                description_zh=_str(entry, "description_zh", f"commands.{cid}", required=True),
                input_schema=_schema(
                    entry.get("input_schema"),
                    name=f"commands.{cid}.input_schema",
                    input_schema=True,
                ),
                output_schema=_schema(
                    entry.get("output_schema"), name=f"commands.{cid}.output_schema"
                ),
                effect=entry["effect"],
                idempotent=entry["idempotent"],
            )
        )
    return tuple(result)


def parse_manifest(data: bytes | str) -> Manifest:
    """Parse and validate manifest bytes (design §7.5). Raises :class:`ProviderManifestError`."""
    raw_bytes = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw_bytes) > MANIFEST_MAX_BYTES:
        raise _err(f"file exceeds {MANIFEST_MAX_BYTES // 1024} KiB")
    doc = _toml_loads(raw_bytes)

    if type(doc.get("manifest_version")) is not int or doc["manifest_version"] != 1:
        raise _err("manifest_version must be 1")
    prov = _table(doc, "provider", required=True)
    pid = _str(prov, "id", "provider", required=True)
    problem = validate_provider_id(pid)
    if problem:
        raise _err(problem)
    version = _str(prov, "version", "provider", required=True)
    try:
        Version(version)
    except ValueError as exc:
        raise _err(f"provider.version: {exc}") from exc

    runtime = _table(doc, "runtime", required=True)
    kind = _str(runtime, "kind", "runtime", required=True)
    if kind == "python":
        raise _err(
            "runtime.kind 'python' is no longer supported; write the provider as 'node' "
            "(an ES module the engine loads) or 'exec' (a process that speaks EPP/1)"
        )
    if kind not in SUPPORTED_PROTOCOLS:
        raise _err("runtime.kind must be 'exec', 'rest', or 'node'")
    compat = _table(doc, "compat")
    protocol = _str(compat, "protocol", "compat", default=SUPPORTED_PROTOCOLS[kind])
    if protocol != SUPPORTED_PROTOCOLS[kind]:
        raise ProviderVersionError(
            f"Provider '{pid}' uses protocol '{protocol}', which this host does not support.",
            suggestion=f"Supported: {SUPPORTED_PROTOCOLS[kind]}.",
        )
    requires_raw = compat.get("requires", {})
    if not isinstance(requires_raw, dict) or not all(
        isinstance(v, str) for v in requires_raw.values()
    ):
        raise _err("compat.requires must be a table of strings")
    for comp, spec in requires_raw.items():
        try:
            version_satisfies("0", spec)
        except ValueError as exc:
            raise _err(f"compat.requires.{comp}: {exc}") from exc

    command: tuple[str, ...] = ()
    endpoint: dict[str, Any] = {}
    if kind == "exec":
        cmd = runtime.get("command")
        if (
            not isinstance(cmd, list)
            or not cmd
            or not all(isinstance(c, str) and c and "\x00" not in c for c in cmd)
        ):
            raise _err("runtime.command must be a non-empty array of non-empty strings")
        exe = cmd[0]
        if exe.lower().endswith(_FORBIDDEN_LAUNCHERS):
            raise _err(
                "runtime.command may not start a .bat/.cmd/.ps1 launcher (they need a shell); "
                "use an .exe or an interpreter plus script"
            )
        if exe.startswith(("./", "../", ".\\", "..\\")):
            normalized = posixpath.normpath(exe.replace("\\", "/"))
            if normalized == ".." or normalized.startswith("../"):
                raise _err("runtime.command executable must stay inside the plugin directory")
        command = tuple(cmd)
    elif kind == "node":
        entry = runtime.get("entry")
        if (
            not isinstance(entry, str)
            or not entry.endswith((".mjs", ".js"))
            or "\x00" in entry
            or entry.startswith(("/", "\\"))
        ):
            raise _err("runtime.entry must be a relative .mjs or .js file inside the plugin")
        normalized = posixpath.normpath(entry.replace("\\", "/"))
        if normalized == ".." or normalized.startswith("../"):
            raise _err("runtime.entry must stay inside the plugin directory")
        command = (normalized,)
    else:
        endpoint = dict(_table(doc, "endpoint", required=True))
        base = endpoint.get("base_url")
        if base is not None and not (
            isinstance(base, str) and base.startswith(("https://", "http://"))
        ):
            raise _err("endpoint.base_url must be an http(s) URL")
        auth = endpoint.get("auth", {"scheme": "bearer"})
        if not isinstance(auth, dict) or auth.get("scheme", "bearer") not in ("bearer", "header"):
            raise _err("endpoint.auth.scheme must be 'bearer' or 'header'")
        derive = endpoint.get("derive", {})
        if not isinstance(derive, dict) or not all(isinstance(v, str) for v in derive.values()):
            raise _err("endpoint.derive must be a table of strings")
        for dk in derive:
            if dk not in ("sandbox_base_url", "sandbox_domain"):
                raise _err(f"endpoint.derive.{dk} is not derivable")

    def ms(key: str, default: int) -> int:
        v = runtime.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int) or not (100 <= v <= 3_600_000):
            raise _err(f"runtime.{key} must be an integer between 100 and 3600000")
        return v

    platforms = tuple(_str_list(runtime, "platforms", "runtime"))

    feats = _table(doc, "features", required=True)
    supported = _str_list(feats, "supported", "features")
    unknown = sorted(set(supported) - set(FEATURES))
    if unknown:
        raise _err(f"unknown feature(s): {', '.join(unknown)}")

    from agent_sandbox.workflows.planner import CONTRACT

    if (
        type(doc.get("operation_contract_version")) is not int
        or doc["operation_contract_version"] != 1
    ):
        raise _err("operation_contract_version must be 1")
    operation_table = _table(doc, "operations", required=True)
    if set(operation_table) != {"cli", "python"}:
        raise _err("operations must declare exactly cli and python arrays")
    operations: dict[str, tuple[str, ...]] = {}
    known_operations = set(CONTRACT["operations"])
    for consumer in ("cli", "python"):
        values = _str_list(operation_table, consumer, "operations")
        if len(values) != len(set(values)) or set(values) - known_operations:
            raise _err(f"operations.{consumer} contains duplicate or unknown operations")
        if consumer == "python" and "template.prepare" in values:
            raise _err("operations.python template.prepare has no implementation")
        if kind == "exec" and any(value.startswith("code.") for value in values):
            raise _err("exec Python bridge does not implement interpreter operations")
        if kind == "rest" and any(value.startswith("code.") for value in values):
            raise _err("rest Python bridge has no verified interpreter wire mapping")
        operations[consumer] = tuple(values)
    workflow = _table(doc, "workflow", required=True)
    if not {"inputs", "startups"}.issubset(workflow) or set(workflow) - {
        "inputs",
        "startups",
        "source_placeholders",
    }:
        raise _err(
            "workflow must declare inputs and startups; only source_placeholders is optional"
        )
    workflow_inputs = _str_list(workflow, "inputs", "workflow")
    placeholders = _str_list(workflow, "source_placeholders", "workflow")
    if len(placeholders) != len(set(placeholders)) or set(placeholders) - {"<region>", "<tag>"}:
        raise _err("workflow.source_placeholders contains duplicate or unknown values")
    if placeholders and (
        "template.prepare" not in operations["cli"] or "source" not in workflow_inputs
    ):
        raise _err("workflow.source_placeholders requires CLI template.prepare and source input")
    startup_modes = _str_list(workflow, "startups", "workflow")
    for values, allowed_values, label in (
        (workflow_inputs, {"source", "image", "managed", "service"}, "inputs"),
        (startup_modes, {"exec", "entrypoint", "none"}, "startups"),
    ):
        if len(values) != len(set(values)) or set(values) - allowed_values:
            raise _err(f"workflow.{label} contains duplicate or unknown values")

    sec = _table(doc, "security")
    security: dict[str, Any] = {
        "network": _str_list(sec, "network", "security"),
        "filesystem": _str_list(sec, "filesystem", "security"),
        "env_passthrough": _str_list(sec, "env_passthrough", "security"),
        "spawns_processes": bool(sec.get("spawns_processes", False)),
    }
    for scope in security["filesystem"]:
        if scope not in FILESYSTEM_SCOPES:
            raise _err(f"security.filesystem: unknown scope '{scope}'")
    for name in security["env_passthrough"]:
        if name.upper().startswith(_FORBIDDEN_ENV_PREFIXES) or not re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*$", name
        ):
            raise _err(f"security.env_passthrough may not name '{name}'")

    core = _table(doc, "core")
    inherit = _str_list(core, "inherit", "core")
    bad = sorted(set(inherit) - set(GENERIC_ENDPOINT_KEYS))
    if bad:
        allowed = ", ".join(GENERIC_ENDPOINT_KEYS)
        raise _err(f"core.inherit may only contain {allowed} (got {', '.join(bad)})")

    fields_tbl = _table(_table(doc, "config"), "fields")
    fields: list[ConfigField] = []
    for fkey, spec in fields_tbl.items():
        if not isinstance(spec, dict):
            raise _err(f"config.fields.{fkey} must be a table")
        if not FIELD_KEY_RE.match(fkey):
            raise _err(f"field key '{fkey}' must match ^[a-z][a-z0-9_]*$")
        if fkey in CORE_KEY_NAMES or fkey.startswith("shortcuts"):
            raise _err(f"field key '{fkey}' collides with a core key")
        ftype = _str(spec, "type", f"config.fields.{fkey}", default="string")
        if ftype not in FIELD_TYPES:
            raise _err(
                f"config.fields.{fkey}.type '{ftype}' is not one of {', '.join(FIELD_TYPES)}"
            )
        secret = bool(spec.get("secret", False))
        if secret and "default" in spec and spec["default"] not in ("", None):
            raise _err(f"config.fields.{fkey}: secret fields may not have a default")
        env_names = tuple(_str_list(spec, "env", f"config.fields.{fkey}"))
        for en in env_names:
            if en.upper().startswith(_FORBIDDEN_ENV_PREFIXES):
                raise _err(f"config.fields.{fkey}.env may not use the reserved name '{en}'")
        choices = tuple(_str_list(spec, "choices", f"config.fields.{fkey}"))
        if ftype == "enum" and not choices:
            raise _err(f"config.fields.{fkey}: enum fields need 'choices'")
        default = spec.get("default")
        fields.append(
            ConfigField(
                key=fkey,
                type=_FIELD_TYPE_TO_KEY_TYPE.get(ftype, ftype),
                required=bool(spec.get("required", False)),
                secret=secret,
                credential=bool(spec.get("credential", False)),
                default=None if default in ("", None) else default,
                description=_str(spec, "description", f"config.fields.{fkey}"),
                description_zh=_str(spec, "description_zh", f"config.fields.{fkey}"),
                env=env_names,
                choices=choices,
            )
        )
    field_keys = {f.key for f in fields}

    auth_tbl = _table(doc, "auth")
    any_of_raw = auth_tbl.get("any_of", [])
    any_of: list[tuple[str, ...]] = []
    if not isinstance(any_of_raw, list):
        raise _err("auth.any_of must be an array of arrays")
    for grp in any_of_raw:
        if not isinstance(grp, list) or not all(isinstance(g, str) for g in grp):
            raise _err("auth.any_of must be an array of arrays of strings")
        missing = [g for g in grp if g not in field_keys and g not in GENERIC_ENDPOINT_KEYS]
        if missing:
            raise _err(f"auth.any_of references undeclared field(s): {', '.join(missing)}")
        any_of.append(tuple(grp))

    return Manifest(
        id=pid,
        name=_str(prov, "name", "provider", default=pid) or pid,
        name_zh=_str(prov, "name_zh", "provider"),
        version=version,
        description=_str(prov, "description", "provider"),
        license=_str(prov, "license", "provider"),
        homepage=_str(prov, "homepage", "provider"),
        kind=kind,
        protocol=protocol,
        requires=dict(requires_raw),
        command=command,
        startup_timeout_ms=ms("startup_timeout_ms", 10_000),
        call_timeout_ms=ms("call_timeout_ms", 60_000),
        platforms=platforms,
        features=tuple(supported),
        operation_contract_version=1,
        operations=operations,
        workflow_inputs=tuple(workflow_inputs),
        startup_modes=tuple(startup_modes),
        security=security,
        inherit=tuple(inherit),
        auth_any_of=tuple(any_of),
        fields=tuple(fields),
        endpoint=endpoint,
        commands=_parse_commands(doc, kind),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        raw=doc,
    )


def missing_manifest_error() -> ProviderManifestError:
    """The error for a plugin root without ``abx-provider.toml``."""
    return ProviderManifestError(
        f"Invalid {MANIFEST_NAME}: file not found at the plugin root.",
        suggestion=(
            f"Point SOURCE at the directory that contains {MANIFEST_NAME} "
            "(owner/repo//subdir or --subdir)."
        ),
    )


def load_manifest(directory: Path) -> Manifest:
    """Read and parse ``<directory>/abx-provider.toml``."""
    path = directory / MANIFEST_NAME
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise missing_manifest_error() from exc
    except OSError as exc:
        raise ProviderManifestError(
            f"Invalid {MANIFEST_NAME}: cannot read {path}: {exc.strerror or exc}."
        ) from exc
    return parse_manifest(data)
