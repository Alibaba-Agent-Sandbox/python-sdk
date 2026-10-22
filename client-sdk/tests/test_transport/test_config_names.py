# ruff: noqa: E501, N812
"""Canonical names, legacy/compat aliases, precedence, audit and migration for ``load_config``."""

from __future__ import annotations

import pytest

import agent_sandbox.transport.config as cfgmod
from agent_sandbox.models.errors import ProviderConfigError
from agent_sandbox.providers import Provider, register_provider
from agent_sandbox.transport.config import (
    TransportConfig,
    explain_config,
    load_config,
)
from tests.iso import iso  # noqa: F401


class _Dummy(Provider):
    id = "my-prov"
    kind = "python"

    async def build_infra(self, config):
        raise NotImplementedError


DEFAULT_URL = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"


class TestCanonicalModel:
    def test_retired_constructor_names_are_ignored(self):
        c = TransportConfig(api_key="k", api_url="https://x", domain="d.example")
        assert c.sandbox_api_key is None
        assert c.sandbox_base_url == DEFAULT_URL
        assert c.sandbox_domain == "cn-hangzhou.e2b.fc.aliyuncs.com"
        assert not hasattr(c, "api_key") or "api_key" not in type(c).model_fields

    def test_canonical_constructor_names(self):
        c = TransportConfig(sandbox_api_key="k", sandbox_base_url="https://x", sandbox_domain="d")
        assert (c.sandbox_api_key, c.sandbox_base_url, c.sandbox_domain) == ("k", "https://x", "d")

    def test_defaults(self):
        c = TransportConfig()
        assert c.sandbox_base_url == DEFAULT_URL
        assert c.provider == "alicloud-express"
        assert c.region == "cn-hangzhou"


@pytest.mark.parametrize(
    ("env", "field", "value"),
    [
        ("ABX_SANDBOX_API_KEY", "sandbox_api_key", "v"),
        ("ABX_SANDBOX_BASE_URL", "sandbox_base_url", "https://v.example"),
        ("ABX_SANDBOX_DOMAIN", "sandbox_domain", "v.example"),
        ("ALIBABA_CLOUD_REGION_ID", "region", "cn-beijing"),
        ("ALICLOUD_ACCESS_KEY_ID", "access_key_id", "id"),
        ("ALICLOUD_ACCESS_KEY_SECRET", "access_key_secret", "sec"),
        ("ABX_HTTP_TIMEOUT", "http_timeout", 12.5),
        ("ABX_HTTP2", "http2", False),
    ],
)
class TestEveryNameInEveryLayer:
    def _raw(self, value):
        return "false" if value is False else str(value)

    def test_process_env(self, iso, monkeypatch, env, field, value):  # noqa: F811
        monkeypatch.setenv(env, self._raw(value))
        assert getattr(load_config(), field) == value

    def test_dotenv(self, iso, env, field, value):  # noqa: F811
        iso.write_env(f"{env}={self._raw(value)}\n")
        assert getattr(load_config(), field) == value

    def test_override_kwarg_by_field_name(self, iso, env, field, value):  # noqa: F811
        assert getattr(load_config(**{field: value}), field) == value


class TestPrecedence:
    def test_retired_process_names_are_ignored(self, iso, monkeypatch):  # noqa: F811
        monkeypatch.setenv("SANDBOX_API_KEY", "legacy")
        monkeypatch.setenv("E2B_API_KEY", "compat")
        cfgmod.reset_config()
        assert load_config().sandbox_api_key is None
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "canon")
        cfgmod.reset_config()
        assert load_config().sandbox_api_key == "canon"

    def test_process_env_beats_dotenv(self, iso, monkeypatch):  # noqa: F811
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "from-env")
        iso.write_env("ABX_SANDBOX_API_KEY=canon-dotenv\n")
        assert load_config().sandbox_api_key == "from-env"

    def test_secret_precedence_ignores_plaintext_toml(self, iso, monkeypatch):  # noqa: F811
        iso.write_toml('[transport]\nsandbox_api_key = "toml"\n')
        assert load_config().sandbox_api_key is None
        iso.write_env("ABX_SANDBOX_API_KEY=dotenv\n")
        assert load_config().sandbox_api_key == "dotenv"
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "env")
        cfgmod.reset_config()
        assert load_config().sandbox_api_key == "env"
        assert load_config(api_key="kw").sandbox_api_key == "env"
        assert load_config(sandbox_api_key="kw2").sandbox_api_key == "kw2"

    def test_blank_override_and_env_are_ignored(self, iso, monkeypatch):  # noqa: F811
        iso.write_env("ABX_SANDBOX_API_KEY=dotenv\n")
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "   ")
        assert load_config(sandbox_api_key="  ").sandbox_api_key == "dotenv"

    def test_toml_ignores_retired_names(self, iso):  # noqa: F811
        iso.write_toml('[transport]\napi_url = "https://legacy"\n')
        assert load_config().sandbox_base_url == DEFAULT_URL
        iso.write_toml(
            '[transport]\napi_url = "https://legacy"\nsandbox_base_url = "https://canon"\n'
        )
        assert load_config().sandbox_base_url == "https://canon"

    def test_flat_retired_toml_is_ignored(self, iso):  # noqa: F811
        iso.write_toml('api_url = "https://flat"\n')
        assert load_config().sandbox_base_url == DEFAULT_URL

    def test_builtin_scoped_toml_table(self, iso):  # noqa: F811
        iso.write_toml('[providers.alicloud-express]\nregion = "cn-shanghai"\n')
        assert load_config().region == "cn-shanghai"
        iso.write_toml(
            '[transport]\nregion = "cn-beijing"\n[providers.alicloud-express]\nregion = "cn-shanghai"\n'
        )
        assert load_config().region == "cn-shanghai"

    def test_cache_is_used_without_overrides_and_reset_clears(self, iso, monkeypatch):  # noqa: F811
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "one")
        assert load_config() is load_config()
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "two")
        assert load_config().sandbox_api_key == "one"
        cfgmod.reset_config()
        assert load_config().sandbox_api_key == "two"


class TestRegionDerivation:
    def test_region_derives_url_and_domain(self, iso):  # noqa: F811
        c = load_config(region="cn-beijing")
        assert c.sandbox_base_url == "https://api.cn-beijing.e2b.fc.aliyuncs.com"
        assert c.sandbox_domain == "cn-beijing.e2b.fc.aliyuncs.com"

    def test_explicit_process_env_url_wins_and_domain_stays_default(self, iso, monkeypatch):  # noqa: F811
        monkeypatch.setenv("ABX_SANDBOX_BASE_URL", "https://custom.example")
        c = load_config(region="cn-beijing")
        assert c.sandbox_base_url == "https://custom.example"
        assert c.sandbox_domain == "cn-hangzhou.e2b.fc.aliyuncs.com"

    def test_dotenv_url_is_kept_as_default_semantics(self, iso):  # noqa: F811
        iso.write_env(
            "ABX_SANDBOX_BASE_URL=https://dotenv.example\nALIBABA_CLOUD_REGION_ID=cn-beijing\n"
        )
        c = load_config()
        assert c.sandbox_base_url == "https://dotenv.example"


class TestProviderSelectionAndOptions:
    def test_default_provider(self, iso):  # noqa: F811
        assert load_config().provider == "alicloud-express"

    @pytest.mark.parametrize(
        "where",
        ["env", "dotenv", "toml", "override"],
    )
    def test_provider_from_each_layer(self, iso, monkeypatch, where):  # noqa: F811
        register_provider(_Dummy())
        if where == "env":
            monkeypatch.setenv("ABX_PROVIDER", "my-prov")
        elif where == "dotenv":
            iso.write_env("ABX_PROVIDER=my-prov\n")
        elif where == "toml":
            iso.write_toml('[core]\nprovider = "my-prov"\n')
        cfg = load_config(provider="my-prov") if where == "override" else load_config()
        assert cfg.provider == "my-prov"

    def test_builtin_options(self, iso):  # noqa: F811
        c = load_config(provider_options={"region": "cn-shanghai"})
        assert c.region == "cn-shanghai"

    def test_unknown_option_is_a_typed_error(self, iso):  # noqa: F811
        with pytest.raises(ProviderConfigError) as exc:
            load_config(provider_options={"nope": 1})
        assert exc.value.code == "E8002"


class TestExplain:
    def test_sources_and_masking(self, iso, monkeypatch):  # noqa: F811
        iso.write_toml('[transport]\nsandbox_base_url = "https://t.example"\n')
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "abcdefghijkl")
        info = explain_config()
        assert info["sandbox_api_key"]["source"] == "environ"
        assert info["sandbox_api_key"]["name"] == "ABX_SANDBOX_API_KEY"
        assert info["sandbox_api_key"]["value"] == "****ijkl"
        assert "abcdefgh" not in str(info)
        assert info["sandbox_base_url"]["source"] == "toml"
        assert info["http_timeout"]["source"] == "default"

    def test_short_secrets_fully_masked(self, iso, monkeypatch):  # noqa: F811
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "short")
        assert explain_config()["sandbox_api_key"]["value"] == "****"
