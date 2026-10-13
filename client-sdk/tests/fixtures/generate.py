# ruff: noqa: E501, N802
"""Regenerate the language-neutral conformance fixtures (``python tests/fixtures/generate.py``).

The Python SDK is the reference implementation; the Node CLI runs the same files unchanged.
Inputs are written by hand below, expectations come from the reference implementation and are
reviewed in the diff. ``tests/test_providers/test_conformance.py`` fails when a file is stale.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import tomllib

HERE = Path(__file__).resolve().parent


def _resolution_inputs() -> list[dict[str, Any]]:
    k = "sandbox_api_key"
    e2b_like = {
        "inherit": ["sandbox_api_key", "sandbox_base_url", "sandbox_domain"],
        "fields": [],
        "derive": {},
        "endpoint_defaults": {
            "sandbox_base_url": "https://api.e2b.dev",
            "sandbox_domain": "e2b.dev",
        },
    }
    plug = {
        "inherit": [],
        "fields": [
            {"key": "token", "type": "str", "secret": True, "env": ["PLUG_TOKEN"]},
            {"key": "mode", "type": "enum", "choices": ["fast", "safe"], "default": "safe"},
            {"key": "retries", "type": "int", "default": 2},
        ],
        "derive": {},
        "endpoint_defaults": {},
    }
    region_derived = {
        "inherit": ["sandbox_base_url", "sandbox_domain", "sandbox_api_key"],
        "fields": [{"key": "region", "type": "str", "default": "r1"}],
        "derive": {
            "sandbox_base_url": "https://api.{region}.example.com",
            "sandbox_domain": "{region}.example.com",
        },
        "endpoint_defaults": {},
    }
    v: list[dict[str, Any]] = []

    def add(
        name: str,
        sources: dict[str, Any],
        provider: str = "alicloud-express",
        schema: dict[str, Any] | None = None,
    ) -> None:
        item: dict[str, Any] = {"name": name, "provider": provider, "sources": sources}
        if schema is not None:
            item["provider_schema"] = schema
        v.append(item)

    def S(overrides=None, environ=None, dotenv=None, toml=None) -> dict[str, Any]:
        return {
            "overrides": overrides or {},
            "environ": environ or {},
            "dotenv": dotenv or [],
            "toml": toml or {},
        }

    add("defaults only", S())
    for name in ("EBX_SANDBOX_API_KEY", "E2B_API_KEY", "SANDBOX_API_KEY"):
        add(f"{name} in process env", S(environ={name: "v-" + name}))
        add(f"{name} in dotenv", S(dotenv=[{name: "v-" + name}]))
    add(
        "canonical beats compat beats legacy (env)",
        S(environ={"SANDBOX_API_KEY": "l", "E2B_API_KEY": "c", "EBX_SANDBOX_API_KEY": "n"}),
    )
    add("compat beats legacy (env)", S(environ={"SANDBOX_API_KEY": "l", "E2B_API_KEY": "c"}))
    add(
        "layer beats name: legacy env over canonical dotenv",
        S(
            environ={"SANDBOX_API_KEY": "legacy-env"},
            dotenv=[{"EBX_SANDBOX_API_KEY": "canon-dotenv"}],
        ),
    )
    add("override beats env", S(overrides={k: "ov"}, environ={"EBX_SANDBOX_API_KEY": "env"}))
    add(
        "legacy kwarg api_key override",
        S(overrides={"api_key": "legacy-kw"}, environ={"EBX_SANDBOX_API_KEY": "env"}),
    )
    add("blank override falls through", S(overrides={k: "   "}, environ={"E2B_API_KEY": "env"}))
    add(
        "blank env falls through to dotenv",
        S(
            environ={"EBX_SANDBOX_API_KEY": " ", "E2B_API_KEY": ""},
            dotenv=[{"SANDBOX_API_KEY": "dot"}],
        ),
    )
    add(
        "project dotenv beats home dotenv",
        S(dotenv=[{"E2B_API_KEY": "project"}, {"E2B_API_KEY": "home"}]),
    )
    add(
        "project dotenv falls through to home dotenv per key",
        S(dotenv=[{"SANDBOX_REGION": "r-project"}, {"E2B_API_KEY": "home-key"}]),
    )
    add("dotenv beats toml", S(dotenv=[{"E2B_API_KEY": "dot"}], toml={"transport": {k: "toml"}}))
    add("toml canonical name", S(toml={"transport": {k: "t"}}))
    add("toml legacy name api_key", S(toml={"transport": {"api_key": "t-legacy"}}))
    add("toml canonical beats toml legacy", S(toml={"transport": {"api_key": "old", k: "new"}}))
    add(
        "flat legacy toml without [transport]",
        S(toml={"api_url": "https://flat.example", "api_key": "flat"}),
    )
    add(
        "flat legacy toml ignored when [transport] exists",
        S(toml={"api_url": "https://flat.example", "transport": {"http_timeout": 5}}),
    )
    add("toml api_base_url alias", S(toml={"transport": {"api_base_url": "https://b.example"}}))
    add(
        "toml api_url beats api_base_url",
        S(
            toml={
                "transport": {"api_base_url": "https://b.example", "api_url": "https://a.example"}
            }
        ),
    )
    add(
        "scoped toml table beats [transport] for built-in region",
        S(
            toml={
                "transport": {"region": "r-t"},
                "providers": {"alicloud-express": {"region": "r-s"}},
            }
        ),
    )
    add("region derives url and domain", S(overrides={"region": "cn-beijing"}))
    add(
        "region from dotenv derives nothing without explicit env url? derives",
        S(dotenv=[{"SANDBOX_REGION": "cn-shanghai"}]),
    )
    add(
        "explicit env url suppresses derivation (domain stays default)",
        S(overrides={"region": "cn-beijing"}, environ={"E2B_API_URL": "https://custom.example"}),
    )
    add(
        "dotenv url + region keeps dotenv url",
        S(dotenv=[{"E2B_API_URL": "https://dot.example", "SANDBOX_REGION": "cn-beijing"}]),
    )
    add(
        "override url suppresses derivation",
        S(overrides={"api_url": "https://ov.example", "region": "cn-beijing"}),
    )
    add(
        "ak/sk native names",
        S(environ={"ALICLOUD_ACCESS_KEY_ID": "ak", "ALICLOUD_ACCESS_KEY_SECRET": "sk"}),
    )
    add("ak legacy AccessKey", S(environ={"AccessKey": "ak-legacy", "AccessSecret": "sk-legacy"}))
    add(
        "ak canonical beats native",
        S(
            environ={
                "EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID": "canon",
                "ALICLOUD_ACCESS_KEY_ID": "native",
            }
        ),
    )
    add(
        "acr legacy names and csv",
        S(environ={"ACR_REGISTRY": "reg", "ACR_VSWITCH_IDS": "vsw-1,vsw-2", "ACR_PASSWORD": "pw"}),
    )
    add(
        "typed values",
        S(environ={"EBX_HTTP_TIMEOUT": "12.5", "EBX_MAX_RETRIES": "7", "EBX_HTTP2": "off"}),
    )
    add(
        "invalid typed values fall through",
        S(
            environ={"EBX_HTTP_TIMEOUT": "soon", "EBX_HTTP2": "maybe"},
            dotenv=[{"SANDBOX_HTTP_TIMEOUT": "9"}],
        ),
    )
    add("log level normalised", S(environ={"SANDBOX_LOG_LEVEL": "debug"}))
    add(
        "log level invalid ignored",
        S(environ={"EBX_LOG_LEVEL": "loud", "SANDBOX_LOG_LEVEL": "info"}),
    )
    add("llm key priority", S(environ={"OPENAI_API_KEY": "o", "DASHSCOPE_API_KEY": "d"}))
    add("llm canonical beats native", S(environ={"OPENAI_API_KEY": "o", "EBX_LLM_API_KEY": "c"}))
    add("github token native", S(environ={"GITHUB_TOKEN": "gh"}))
    add(
        "github token canonical beats native",
        S(environ={"GITHUB_TOKEN": "gh", "EBX_GITHUB_TOKEN": "mine"}),
    )
    add("template legacy names", S(environ={"SANDBOX_TEMPLATE": "py"}))
    add("provider selection is not a resolved key", S(environ={"EBX_PROVIDER": "e2b-like"}))
    # provider-scoped
    add(
        "non-builtin without inherit gets no generic keys",
        S(environ={"E2B_API_KEY": "generic", "E2B_API_URL": "https://g.example"}),
        "plug",
        plug,
    )
    add(
        "non-builtin: builtin scoped keys are absent",
        S(environ={"ALICLOUD_ACCESS_KEY_ID": "ak", "SANDBOX_REGION": "r"}),
        "plug",
        plug,
    )
    add("plugin fields: defaults", S(), "plug", plug)
    add(
        "plugin field canonical env and native alias",
        S(environ={"EBX_PLUG_TOKEN": "c", "PLUG_TOKEN": "n", "EBX_PLUG_MODE": "fast"}),
        "plug",
        plug,
    )
    add("plugin field native alias only", S(environ={"PLUG_TOKEN": "n"}), "plug", plug)
    add(
        "plugin field toml table and dotenv",
        S(
            dotenv=[{"EBX_PLUG_RETRIES": "5"}],
            toml={"providers": {"plug": {"token": "t", "mode": "fast", "retries": 9}}},
        ),
        "plug",
        plug,
    )
    add("plugin enum invalid falls to default", S(environ={"EBX_PLUG_MODE": "turbo"}), "plug", plug)
    add(
        "plugin option override",
        S(overrides={"token": "kw"}, environ={"EBX_PLUG_TOKEN": "env"}),
        "plug",
        plug,
    )
    add(
        "other provider's scoped env does not leak",
        S(environ={"EBX_OTHER_TOKEN": "x", "EBX_ALICLOUD_EXPRESS_REGION": "r"}),
        "plug",
        plug,
    )
    add(
        "inheritor uses generic keys",
        S(environ={"E2B_API_KEY": "generic", "E2B_API_URL": "https://g.example"}),
        "e2b-like",
        e2b_like,
    )
    add(
        "inheritor: scoped env beats generic",
        S(environ={"E2B_API_KEY": "generic", "EBX_E2B_LIKE_SANDBOX_API_KEY": "scoped"}),
        "e2b-like",
        e2b_like,
    )
    add(
        "inheritor: scoped toml table beats [transport]",
        S(
            toml={
                "providers": {"e2b-like": {"sandbox_api_key": "scoped"}},
                "transport": {"sandbox_api_key": "plain"},
            }
        ),
        "e2b-like",
        e2b_like,
    )
    add("inheritor: endpoint defaults when nothing set", S(), "e2b-like", e2b_like)
    add(
        "inheritor: explicit url beats endpoint default",
        S(dotenv=[{"EBX_SANDBOX_BASE_URL": "https://dot.example"}]),
        "e2b-like",
        e2b_like,
    )
    add("derived endpoint from provider region default", S(), "regional", region_derived)
    add(
        "derived endpoint from region override",
        S(overrides={"region": "r9"}),
        "regional",
        region_derived,
    )
    add(
        "derived endpoint suppressed by explicit env url",
        S(
            overrides={"region": "r9"},
            environ={"EBX_REGIONAL_SANDBOX_BASE_URL": "https://x.example"},
        ),
        "regional",
        region_derived,
    )
    return v


def _resolve(item: dict[str, Any]) -> dict[str, Any]:
    from easy_sandbox.providers.base import ConfigField
    from easy_sandbox.transport.config import ProviderSchema, _builtin_schema, resolve_all
    from easy_sandbox.utils.config_keys import Sources

    src = item["sources"]
    sources = Sources(
        overrides=src["overrides"], environ=src["environ"], dotenv=src["dotenv"], toml=src["toml"]
    )
    spec = item.get("provider_schema")
    if spec is None:
        schema = _builtin_schema()
    else:
        fields = tuple(
            ConfigField(
                key=f["key"],
                type=f.get("type", "str"),
                secret=f.get("secret", False),
                default=f.get("default"),
                env=tuple(f.get("env", ())),
                choices=tuple(f.get("choices", ())),
            ).to_config_key(item["provider"])
            for f in spec["fields"]
        )
        schema = ProviderSchema(
            item["provider"],
            fields,
            frozenset(spec["inherit"]),
            dict(spec["derive"]),
            dict(spec["endpoint_defaults"]),
        )
    _, resolved = resolve_all(sources, schema)
    return {
        key: {"value": r.value, "source": r.layer, "name": r.name}
        for key, r in sorted(resolved.items())
    }


def resolution_vectors() -> dict[str, Any]:
    vectors = []
    for item in _resolution_inputs():
        vectors.append({**item, "expect": _resolve(item)})
    return {
        "schema_version": 1,
        "description": "Resolve every applicable key of `provider` from `sources`; `expect` lists every key that is set.",
        "vectors": vectors,
    }


def tree_digest_vectors() -> dict[str, Any]:
    import base64

    from easy_sandbox.providers import store

    cases: list[tuple[str, list[tuple[str, bool, bytes]]]] = [
        ("empty tree", []),
        ("single file", [("ebx-provider.toml", False, b"manifest_version = 1\n")]),
        ("executable flag matters", [("run.sh", True, b"#!/bin/sh\n")]),
        ("not executable", [("run.sh", False, b"#!/bin/sh\n")]),
        (
            "sorted by utf-8 path bytes, not insertion order",
            [
                ("b.txt", False, b"b"),
                ("a/z.txt", False, b"z"),
                ("a.txt", False, b"a"),
                ("B.txt", False, b"B"),
            ],
        ),
        (
            "nested and unicode paths",
            [("lib/依赖/模块.py", False, "print('你好')\n".encode()), ("lib/x.py", True, b"")],
        ),
        ("binary content", [("blob.bin", False, bytes(range(256)))]),
        ("empty file", [("empty", False, b"")]),
        (
            "file whose name looks like the receipt, nested",
            [("sub/.ebx-install.json", False, b"{}")],
        ),
    ]
    out = []
    for name, files in cases:
        entries = [store.FileEntry(p, x, d) for p, x, d in files]
        out.append(
            {
                "name": name,
                "files": [
                    {"path": p, "executable": x, "content_b64": base64.b64encode(d).decode()}
                    for p, x, d in files
                ],
                "tree_sha256": store.digest_files(entries),
            }
        )
    return {
        "schema_version": 1,
        "algorithm": "sha256 over sorted(path utf-8 bytes): path \\0 (x|-) \\0 sha256(file) \\n",
        "vectors": out,
    }


def epp_error_vectors() -> dict[str, Any]:
    from easy_sandbox.providers.epp import exit_code_for, map_error

    cases: list[tuple[str, dict[str, Any], list[str]]] = [
        ("unauthenticated", {"code": -32001, "message": "no key"}, []),
        (
            "invalid api key subclass",
            {"code": -32001, "message": "bad", "data": {"sdk_code": "E1001"}},
            [],
        ),
        ("not found default", {"code": -32002, "message": "gone"}, []),
        (
            "not found with E2000 sdk_code is still resource-not-found",
            {"code": -32002, "message": "gone", "data": {"sdk_code": "E2000"}},
            [],
        ),
        ("template not found", {"code": -32002, "message": "t", "data": {"sdk_code": "E2001"}}, []),
        ("file not found", {"code": -32002, "message": "f", "data": {"sdk_code": "E4001"}}, []),
        (
            "feature unsupported",
            {"code": -32003, "message": "nope", "data": {"details": {"feature": "pty"}}},
            [],
        ),
        ("quota", {"code": -32004, "message": "full"}, []),
        ("timeout", {"code": -32005, "message": "slow"}, []),
        ("invalid params", {"code": -32006, "message": "bad param"}, []),
        ("other failure", {"code": -32000, "message": "boom"}, []),
        (
            "other failure with sdk_code",
            {"code": -32000, "message": "denied", "data": {"sdk_code": "E4002"}},
            [],
        ),
        ("method not found is a protocol error", {"code": -32601, "message": "no such method"}, []),
        ("parse error is a protocol error", {"code": -32700, "message": "bad json"}, []),
        ("unknown numeric code", {"code": 42, "message": "?"}, []),
        (
            "suggestion is carried",
            {"code": -32000, "message": "m", "data": {"suggestion": "try x"}},
            [],
        ),
        (
            "secrets and control characters are scrubbed",
            {"code": -32000, "message": "\u001b[31mfail\u001b[0m with sekret-value-1\u0000"},
            ["sekret-value-1"],
        ),
    ]
    out = []
    for name, err, secrets in cases:
        exc = map_error(err, "prov", secrets)
        out.append(
            {
                "name": name,
                "error": err,
                "provider_id": "prov",
                "secrets": secrets,
                "expect": {
                    "class": type(exc).__name__,
                    "sdk_code": exc.code,
                    "exit_code": exit_code_for(exc),
                    "message": exc.message,
                    "suggestion": exc.suggestion,
                },
            }
        )
    return {"schema_version": 1, "vectors": out}


def migration_vectors() -> dict[str, Any]:
    from easy_sandbox.transport import config as cfg
    from easy_sandbox.utils.toml_write import dumps_toml

    cases: list[tuple[str, dict[str, Any], str]] = [
        ("nothing stored", {}, ""),
        (
            "legacy api_url in transport",
            {"transport": {"api_url": "https://t.example", "http_timeout": 9}},
            "",
        ),
        (
            "api_base_url alias in transport",
            {"transport": {"api_base_url": "https://t.example"}},
            "",
        ),
        (
            "canonical already present: legacy dropped",
            {"transport": {"api_url": "https://old", "sandbox_base_url": "https://new"}},
            "",
        ),
        ("region moves to the provider table", {"transport": {"region": "cn-beijing"}}, ""),
        (
            "region already scoped",
            {"transport": {"region": "a"}, "providers": {"alicloud-express": {"region": "b"}}},
            "",
        ),
        (
            "env: phase-1 names renamed, comments kept",
            {},
            "# keep me\nE2B_API_KEY=abc\nSANDBOX_REGION=cn-shanghai\nOPENAI_API_KEY=k\n",
        ),
        ("env: shadowed legacy dropped", {}, "E2B_API_KEY=abc\nSANDBOX_API_KEY=old\n"),
        ("env: canonical present wins", {}, "EBX_SANDBOX_API_KEY=new\nE2B_API_KEY=old\n"),
        (
            "env: acr and ak legacy names",
            {},
            "ACR_REGISTRY=r\nACR_PASSWORD=p\nAccessKey=ak\nAccessSecret=sk\nTEAM_ID=7\n",
        ),
        (
            "env: export prefix and blank values",
            {},
            "export SANDBOX_REGION=cn-beijing\nSANDBOX_API_KEY=\n",
        ),
    ]
    out = []
    for name, toml_doc, env_text in cases:
        plan = cfg.plan_migration_data(toml_doc, _env_dict(env_text))
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "config.toml").write_text(dumps_toml(toml_doc), encoding="utf-8")
            if env_text:
                (home / ".env").write_text(env_text, encoding="utf-8")
            cfg.apply_migration(home / "config.toml", home / ".env", backup=False)
            toml_out = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
            env_out = (
                (home / ".env").read_text(encoding="utf-8") if (home / ".env").exists() else ""
            )
        out.append(
            {
                "name": name,
                "toml": toml_doc,
                "env": env_text,
                "plan": plan,
                "toml_after": toml_out,
                "env_after": env_out,
            }
        )
    return {"schema_version": 1, "vectors": out}


def _env_dict(text: str) -> dict[str, str]:
    from easy_sandbox.transport import config as cfg

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".env"
        path.write_text(text, encoding="utf-8")
        return cfg._read_dotenv(path)


def build_all() -> dict[str, Any]:
    from easy_sandbox.utils.config_keys import export_schema

    return {
        "config-keys.json": export_schema(),
        "config-resolution-vectors.json": resolution_vectors(),
        "tree-digest-vectors.json": tree_digest_vectors(),
        "epp-error-mapping.json": epp_error_vectors(),
        "migration-vectors.json": migration_vectors(),
    }


def render(doc: Any) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def main() -> None:
    for name, doc in build_all().items():
        (HERE / name).write_text(render(doc), encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
