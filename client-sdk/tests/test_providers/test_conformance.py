"""Run the language-neutral conformance fixtures against the Python reference implementation."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest
import tomllib

from easy_sandbox.providers import store
from easy_sandbox.providers.base import ConfigField
from easy_sandbox.providers.epp import exit_code_for, map_error
from easy_sandbox.transport import config as cfg
from easy_sandbox.transport.config import ProviderSchema, _builtin_schema, resolve_all
from easy_sandbox.utils.config_keys import Sources
from easy_sandbox.utils.toml_write import dumps_toml

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CLI_COPY = Path(__file__).resolve().parents[4] / "cli" / "docs" / "design" / "fixtures"
NAMES = (
    "config-keys.json",
    "config-resolution-vectors.json",
    "tree-digest-vectors.json",
    "epp-error-mapping.json",
    "migration-vectors.json",
    "epp-methods.json",
)


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _generator():
    spec = importlib.util.spec_from_file_location("ebx_fixture_generate", FIXTURES / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixtures_are_up_to_date():
    gen = _generator()
    for name, doc in gen.build_all().items():
        assert (FIXTURES / name).read_text(encoding="utf-8") == gen.render(doc), (
            f"{name} is stale: run `python tests/fixtures/generate.py`"
        )


@pytest.mark.skipif(not CLI_COPY.is_dir(), reason="CLI repo not checked out next to the SDK")
@pytest.mark.parametrize("name", NAMES)
def test_cli_copy_is_identical(name):
    mirror = CLI_COPY / name
    assert mirror.is_file(), f"{mirror} missing: copy it from the Python SDK fixtures"
    assert mirror.read_bytes() == (FIXTURES / name).read_bytes()


def _vectors(name: str):
    return [pytest.param(v, id=v["name"]) for v in load(name)["vectors"]]


@pytest.mark.parametrize("vector", _vectors("config-resolution-vectors.json"))
def test_resolution_vectors(vector):
    src = vector["sources"]
    sources = Sources(
        overrides=src["overrides"], environ=src["environ"], dotenv=src["dotenv"], toml=src["toml"]
    )
    spec = vector.get("provider_schema")
    if spec is None:
        schema = _builtin_schema()
    else:
        keys = tuple(
            ConfigField(
                key=f["key"],
                type=f.get("type", "str"),
                secret=f.get("secret", False),
                default=f.get("default"),
                env=tuple(f.get("env", ())),
                choices=tuple(f.get("choices", ())),
            ).to_config_key(vector["provider"])
            for f in spec["fields"]
        )
        schema = ProviderSchema(
            vector["provider"],
            keys,
            frozenset(spec["inherit"]),
            dict(spec["derive"]),
            dict(spec["endpoint_defaults"]),
        )
    _, resolved = resolve_all(sources, schema)
    got = {k: {"value": r.value, "source": r.layer, "name": r.name} for k, r in resolved.items()}
    assert got == vector["expect"]


@pytest.mark.parametrize("vector", _vectors("tree-digest-vectors.json"))
def test_tree_digest_vectors(vector):
    entries = [
        store.FileEntry(f["path"], f["executable"], base64.b64decode(f["content_b64"]))
        for f in vector["files"]
    ]
    assert store.digest_files(entries) == vector["tree_sha256"]
    assert store.digest_files(list(reversed(entries))) == vector["tree_sha256"]


def test_tree_digest_of_an_installed_directory_matches_entries(tmp_path):
    vec = next(
        v
        for v in load("tree-digest-vectors.json")["vectors"]
        if v["name"] == "nested and unicode paths"
    )
    for f in vec["files"]:
        target = tmp_path / f["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(f["content_b64"]))
        target.chmod(0o755 if f["executable"] else 0o644)
    assert store.digest_dir(tmp_path) == vec["tree_sha256"]


@pytest.mark.parametrize("vector", _vectors("epp-error-mapping.json"))
def test_epp_error_vectors(vector):
    exc = map_error(vector["error"], vector["provider_id"], vector["secrets"])
    exp = vector["expect"]
    assert type(exc).__name__ == exp["class"]
    assert exc.code == exp["sdk_code"]
    assert exit_code_for(exc) == exp["exit_code"]
    assert exc.message == exp["message"]
    assert exc.suggestion == exp["suggestion"]
    for secret in vector["secrets"]:
        assert secret not in exc.message


@pytest.mark.parametrize("vector", _vectors("migration-vectors.json"))
def test_migration_vectors(vector, tmp_path):
    env_dict = {}
    if vector["env"]:
        (tmp_path / "in.env").write_text(vector["env"], encoding="utf-8")
        env_dict = cfg._read_dotenv(tmp_path / "in.env")
    assert cfg.plan_migration_data(vector["toml"], env_dict) == vector["plan"]
    (tmp_path / "config.toml").write_text(dumps_toml(vector["toml"]), encoding="utf-8")
    if vector["env"]:
        (tmp_path / ".env").write_text(vector["env"], encoding="utf-8")
    cfg.apply_migration(tmp_path / "config.toml", tmp_path / ".env", backup=False)
    assert (
        tomllib.loads((tmp_path / "config.toml").read_text(encoding="utf-8"))
        == vector["toml_after"]
    )
    env_file = tmp_path / ".env"
    assert (env_file.read_text(encoding="utf-8") if env_file.exists() else "") == vector[
        "env_after"
    ]


def test_config_keys_fixture_matches_registry():
    from easy_sandbox.utils.config_keys import export_schema

    assert load("config-keys.json") == export_schema()
    keys = {(k["scope"], k["key"]) for k in load("config-keys.json")["keys"]}
    assert ("core", "sandbox_api_key") in keys and ("alicloud-express", "region") in keys
