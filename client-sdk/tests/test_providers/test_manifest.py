"""Manifest parsing/validation rules."""

from __future__ import annotations

import re

import pytest

from agent_sandbox.models.errors import ProviderManifestError, ProviderVersionError
from agent_sandbox.providers.manifest import (
    check_requires,
    parse_manifest,
    version_satisfies,
)

BASE = """
manifest_version = 1
operation_contract_version = 1
[operations]
cli = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
python = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
[workflow]
inputs = ["managed"]
startups = ["exec", "none"]
[provider]
id = "demo-prov"
version = "1.2.3"
[runtime]
kind = "exec"
command = ["python3", "./p.py"]
[features]
supported = ["sandbox.lifecycle", "exec.run"]
"""


def mutate(old: str, new: str) -> str:
    assert old in BASE
    return BASE.replace(old, new)


def test_minimal_manifest_defaults():
    m = parse_manifest(BASE)
    assert (m.id, m.version, m.kind, m.protocol) == ("demo-prov", "1.2.3", "exec", "epp/1")
    assert m.command == ("python3", "./p.py")
    assert m.startup_timeout_ms == 10_000 and m.call_timeout_ms == 60_000
    assert m.inherit == () and m.fields == () and m.auth_any_of == ()
    assert len(m.sha256) == 64


def test_bytes_and_str_inputs_agree():
    assert parse_manifest(BASE.encode()).sha256 == parse_manifest(BASE).sha256


@pytest.mark.parametrize(
    "features",
    [
        ("templates.build",),
        ("templates.deploy",),
        ("templates.read", "templates.build", "templates.deploy"),
    ],
)
def test_template_features_are_independent_manifest_declarations(features):
    text = mutate(
        'supported = ["sandbox.lifecycle", "exec.run"]',
        "supported = [" + ", ".join(f'"{feature}"' for feature in features) + "]",
    )
    manifest = parse_manifest(text)
    assert manifest.features == features
    assert manifest.to_summary()["features"] == sorted(features)


def test_builtin_template_build_does_not_grant_image_deploy():
    from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider

    assert "templates.build" in AlicloudExpressProvider.features
    assert "templates.deploy" not in AlicloudExpressProvider.features


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("not toml [", "Invalid abx-provider.toml"),
        (mutate("manifest_version = 1", "manifest_version = 2"), "manifest_version"),
        (mutate('id = "demo-prov"', 'id = "Demo"'), "provider id"),
        (mutate('id = "demo-prov"', 'id = "alicloud-express"'), "reserved"),
        (mutate('id = "demo-prov"', 'id = "abx-thing"'), "reserved"),
        (mutate('version = "1.2.3"', 'version = "banana"'), "version"),
        (mutate('kind = "exec"', 'kind = "docker"'), "runtime.kind"),
        (mutate('command = ["python3", "./p.py"]', "command = []"), "runtime.command"),
        (mutate('command = ["python3", "./p.py"]', 'command = ["run.bat"]'), "launcher"),
        (mutate('command = ["python3", "./p.py"]', 'command = ["../evil"]'), "inside the plugin"),
        (
            mutate('command = ["python3", "./p.py"]', 'command = ["./../../evil"]'),
            "inside the plugin",
        ),
        (
            mutate('supported = ["sandbox.lifecycle", "exec.run"]', 'supported = ["time.travel"]'),
            "unknown feature",
        ),
        (BASE + '\n[core]\ninherit = ["region"]\n', "core.inherit"),
        (BASE + '\n[runtime2]\n[security]\nenv_passthrough = ["ABX_TOKEN"]\n', "env_passthrough"),
        (BASE + '\n[security]\nfilesystem = ["everything"]\n', "filesystem"),
        (BASE + '\n[config.fields.provider]\ntype = "string"\n', "collides"),
        (BASE + '\n[config.fields.Bad-Key]\ntype = "string"\n', "must match"),
        (BASE + '\n[config.fields.tok]\ntype = "secret"\n', "type"),
        (
            BASE + '\n[config.fields.tok]\ntype = "string"\nsecret = true\ndefault = "x"\n',
            "default",
        ),
        (BASE + '\n[config.fields.tok]\ntype = "enum"\n', "choices"),
        (BASE + '\n[config.fields.tok]\ntype = "string"\nenv = ["ABX_TOK"]\n', "reserved"),
        (BASE + '\n[auth]\nany_of = [["ghost"]]\n', "undeclared"),
        (mutate('kind = "exec"', 'kind = "exec"\nstartup_timeout_ms = 5'), "startup_timeout_ms"),
        (BASE + '\n[compat]\nprotocol = "epp/9"\n', "protocol"),
        (BASE + '\n[compat]\nrequires = { sdk = "~~1" }\n', "compat.requires"),
    ],
)
def test_rejections(text, needle):
    with pytest.raises((ProviderManifestError, ProviderVersionError)) as exc:
        parse_manifest(text)
    assert needle.lower() in str(exc.value).lower()


def test_oversized_manifest_rejected():
    with pytest.raises(ProviderManifestError):
        parse_manifest(BASE + "#" + "x" * (257 * 1024))


def test_protocol_mismatch_is_version_error_code():
    with pytest.raises(ProviderVersionError) as exc:
        parse_manifest(BASE + '\n[compat]\nprotocol = "epp/9"\n')
    assert exc.value.code == "E8013"


def test_rest_manifest():
    text = """
manifest_version = 1
operation_contract_version = 1
[operations]
cli = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
python = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
[workflow]
inputs = ["managed"]
startups = ["exec", "none"]
[provider]
id = "rest-one"
version = "0.1"
[runtime]
kind = "rest"
[endpoint]
base_url = "https://api.example.com"
auth = { scheme = "header", header = "X-Key" }
derive = { sandbox_domain = "{region}.example.com" }
[features]
supported = ["sandbox.lifecycle"]
[core]
inherit = ["sandbox_api_key"]
[auth]
any_of = [["sandbox_api_key"]]
"""
    m = parse_manifest(text)
    assert m.kind == "rest" and m.protocol == "e2b-rest/1"
    assert m.inherit == ("sandbox_api_key",)
    assert m.auth_any_of == (("sandbox_api_key",),)
    bad = text.replace(
        'auth = { scheme = "header", header = "X-Key" }', 'auth = { scheme = "digest" }'
    )
    with pytest.raises(ProviderManifestError):
        parse_manifest(bad)
    bad = text.replace("sandbox_domain =", "region =")
    with pytest.raises(ProviderManifestError):
        parse_manifest(bad)
    with pytest.raises(ProviderManifestError):
        parse_manifest(text.replace("https://api.example.com", "ftp://x"))


def test_field_details():
    m = parse_manifest(
        BASE
        + """
[config.fields.api_token]
type = "string"
secret = true
credential = true
required = true
env = ["DEMO_TOKEN"]
description = "tok"
description_zh = "令牌"
[config.fields.mode]
type = "enum"
choices = ["a", "b"]
default = "a"
"""
    )
    tok, mode = m.fields
    assert tok.secret and tok.credential and tok.required and tok.env == ("DEMO_TOKEN",)
    assert tok.type == "str"
    assert mode.choices == ("a", "b") and mode.default == "a"


@pytest.mark.parametrize(
    ("ver", "spec", "ok"),
    [
        ("0.3.0", ">=0.3", True),
        ("0.3.0", ">=0.4", False),
        ("1.0", ">=1.0,<2", True),
        ("2.0", ">=1.0,<2", False),
        ("1.2.9", "~=1.2", True),
        ("1.3.0", "~=1.2", True),
        ("2.0.0", "~=1.2", False),
        ("1.2.9", "~=1.2.3", True),
        ("1.3.0", "~=1.2.3", False),
        ("1.0rc1", ">=1.0", False),
        ("1.0", ">1.0rc1", True),
        ("1.0.0", "==1.0", True),
        ("1.0", "!=1.0", False),
        ("5", "", True),
    ],
)
def test_version_satisfies(ver, spec, ok):
    assert version_satisfies(ver, spec) is ok


@pytest.mark.parametrize("spec", ["~~1", ">=", "foo", ">=x"])
def test_bad_specs_raise_value_error(spec):
    with pytest.raises(ValueError):
        version_satisfies("1.0", spec)


def test_check_requires_raises_e8013():
    m = parse_manifest(BASE + '\n[compat]\nrequires = { sdk = ">=9", cli = ">=0.1" }\n')
    with pytest.raises(ProviderVersionError):
        check_requires(m, component="sdk", host_version="0.3.0")
    check_requires(m, component="cli", host_version="0.3.0")
    check_requires(m, component="other", host_version="0.0.1")


def test_sha_is_stable_hex():
    assert re.fullmatch(r"[0-9a-f]{64}", parse_manifest(BASE).sha256)
