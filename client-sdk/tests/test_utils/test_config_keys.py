"""Registry invariants and the pure resolver (precedence + alias table)."""

from __future__ import annotations

import pytest

from agent_sandbox.utils import config_keys as ck
from agent_sandbox.utils.config_keys import Sources, resolve_key

ALL_KEYS = (*ck.CORE_KEYS, *ck.ALICLOUD_EXPRESS_KEYS)


def _src(**kw):
    return Sources(
        overrides=kw.get("overrides", {}),
        environ=kw.get("environ", {}),
        dotenv=kw.get("dotenv", ()),
        toml=kw.get("toml", {}),
    )


class TestRegistry:
    def test_unique_keys_per_scope(self):
        seen = [(k.scope, k.key) for k in ALL_KEYS]
        assert len(seen) == len(set(seen))

    def test_every_canonical_env_name_is_unique(self):
        names = [k.env for k in ALL_KEYS]
        assert len(names) == len(set(names))

    def test_no_alias_collides_with_another_key(self):
        owners: dict[tuple[str, str], str] = {}
        for k in ALL_KEYS:
            for a in k.aliases:
                slot = (a.surface, a.name)
                # one alias name may only belong to one key per surface
                if slot in owners and owners[slot] != f"{k.scope}.{k.key}":
                    pytest.fail(f"alias {slot} used by {owners[slot]} and {k.scope}.{k.key}")
                owners[slot] = f"{k.scope}.{k.key}"

    def test_aliases_are_well_formed(self):
        for k in ALL_KEYS:
            for a in k.aliases:
                assert a.kind in ck.ALIAS_KINDS
                assert a.surface in ck.ALIAS_SURFACES

    def test_secrets_are_masked_kinds(self):
        secrets = {k.key for k in ALL_KEYS if k.secret}
        assert {
            "sandbox_api_key",
            "access_key_secret",
            "github_token",
            "mcp_auth_token",
        } <= secrets

    def test_registry_declares_only_keys_the_client_reads(self):
        # Template build (ACR) and template generation (LLM) settings belong to the CLI.
        names = {k.key for k in ALL_KEYS}
        assert not {n for n in names if n.startswith(("acr_", "llm_"))}
        assert "team_id" not in names

    def test_endpoint_descriptions_name_the_active_provider(self):
        for name in ("sandbox_api_key", "sandbox_base_url"):
            key = ck.get_key(name)
            assert key is not None
            assert "active provider" in key.description
            assert "E2B" not in key.description + key.description_zh

    def test_each_key_has_one_environment_name(self):
        for key in ALL_KEYS:
            assert key.aliases == ()
            assert ck.env_names(key) == (key.env,)

    def test_vendor_official_names_are_the_canonical_env(self):
        assert ck.get_key("access_key_id", "alicloud-express").env == "ALICLOUD_ACCESS_KEY_ID"
        secret = ck.get_key("access_key_secret", "alicloud-express")
        assert secret.env == "ALICLOUD_ACCESS_KEY_SECRET"
        assert ck.get_key("region", "alicloud-express").env == "ALIBABA_CLOUD_REGION_ID"
        assert ck.get_key("github_token").env == "GITHUB_TOKEN"
        assert ck.get_key("sandbox_api_key").env == "ABX_SANDBOX_API_KEY"

    def test_retired_names_are_not_resolved(self):
        retired = (
            "E2B_API_KEY",
            "SANDBOX_API_KEY",
            "E2B_API_URL",
            "SANDBOX_REGION",
            "AccessKey",
            "AccessSecret",
            "ABX_ALICLOUD_EXPRESS_ACCESS_KEY_ID",
            "ABX_ALICLOUD_EXPRESS_REGION",
            "OPENAI_API_KEY",
            "DASHSCOPE_API_KEY",
        )
        known = {k.env for k in ALL_KEYS}
        for name in retired:
            assert name not in known

    def test_env_names_order_is_scoped_then_canonical(self):
        key = ck.get_key("sandbox_api_key")
        assert ck.env_names(key, scoped_for="my-prov") == (
            "ABX_MY_PROV_SANDBOX_API_KEY",
            "ABX_SANDBOX_API_KEY",
        )

    def test_schema_export_is_stable_and_complete(self):
        schema = ck.export_schema()
        assert schema["builtin_provider"]["id"] == "alicloud-express"
        assert schema["builtin_provider"]["name_zh"] == "阿里云极速版"
        assert [r["key"] for r in schema["keys"]][: len(ck.CORE_KEYS)] == [
            k.key for k in ck.CORE_KEYS
        ]
        assert ck.export_schema() == schema

    @pytest.mark.parametrize(
        ("pid", "ok"),
        [
            ("my-provider", True),
            ("e2b", True),
            ("alicloud-container", True),
            ("e2b-compat", True),
            ("a", False),
            ("My-Provider", False),
            ("-x", False),
            ("a--b", False),
            ("alicloud-express", False),
            ("alicloud-foo", False),
            ("abx-foo", False),
            ("x" * 41, False),
            ("1abc", False),
            ("a_b", False),
        ],
    )
    def test_validate_provider_id(self, pid, ok):
        assert (ck.validate_provider_id(pid) is None) is ok

    def test_provider_env_name(self):
        assert ck.provider_env_name("my-provider", "api_token") == "ABX_MY_PROVIDER_API_TOKEN"


class TestCoerce:
    def test_blank_is_unset(self):
        key = ck.get_key("sandbox_api_key")
        assert ck.coerce(key, "   ") is None
        assert ck.coerce(key, None) is None

    @pytest.mark.parametrize(
        ("raw", "want"),
        [("true", True), ("1", True), ("No", False), ("off", False), ("maybe", None)],
    )
    def test_bool(self, raw, want):
        assert ck.coerce(ck.get_key("http2"), raw) is want

    def test_int_and_float(self):
        assert ck.coerce(ck.get_key("max_connections"), "5") == 5
        assert ck.coerce(ck.get_key("max_connections"), "5.0") == 5
        assert ck.coerce(ck.get_key("max_connections"), "x") is None
        assert ck.coerce(ck.get_key("http_timeout"), "2.5") == 2.5

    def test_enum_is_case_insensitive_and_validated(self):
        key = ck.get_key("log_level")
        assert ck.coerce(key, "debug") == "DEBUG"
        assert ck.coerce(key, "loud") is None


class TestResolvePrecedence:
    KEY = ck.get_key("sandbox_api_key")

    def test_layer_order(self):
        src = _src(
            overrides={"sandbox_api_key": "o"},
            environ={"ABX_SANDBOX_API_KEY": "e"},
            dotenv=[{"ABX_SANDBOX_API_KEY": "d1"}, {"ABX_SANDBOX_API_KEY": "d2"}],
            toml={"transport": {"sandbox_api_key": "t"}},
        )
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer) == ("o", "override")
        src.overrides = {}
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer) == ("e", "environ")
        src.environ = {}
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer, r.layer_index) == ("d1", "dotenv", 0)
        src.dotenv = [{}, {"ABX_SANDBOX_API_KEY": "d2"}]
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer_index) == ("d2", 1)
        src.dotenv = []
        r = resolve_key(self.KEY, src)
        assert r is None

    def test_retired_name_does_not_beat_the_canonical_name(self):
        src = _src(
            environ={"SANDBOX_API_KEY": "legacy-env", "E2B_API_KEY": "compat-env"},
            dotenv=[{"ABX_SANDBOX_API_KEY": "canon-dotenv"}],
        )
        assert resolve_key(self.KEY, src).value == "canon-dotenv"

    def test_blank_values_fall_through(self):
        src = _src(
            environ={"ABX_SANDBOX_API_KEY": "  "},
            dotenv=[{"ABX_SANDBOX_API_KEY": "from-dotenv"}],
        )
        assert resolve_key(self.KEY, src).value == "from-dotenv"

    def test_scoped_name_beats_canonical(self):
        src = _src(
            environ={"ABX_MY_PROV_SANDBOX_API_KEY": "scoped", "ABX_SANDBOX_API_KEY": "plain"}
        )
        assert resolve_key(self.KEY, src, scoped_for="my-prov").value == "scoped"
        assert resolve_key(self.KEY, src).value == "plain"

    def test_plaintext_toml_does_not_supply_secrets(self):
        toml = {
            "providers": {"my-prov": {"sandbox_api_key": "scoped"}},
            "transport": {"sandbox_api_key": "plain"},
        }
        assert resolve_key(self.KEY, _src(toml=toml), scoped_for="my-prov") is None
        assert resolve_key(self.KEY, _src(toml=toml)) is None

    def test_toml_ignores_retired_names(self):
        key = ck.get_key("sandbox_base_url")
        toml = {"transport": {"api_url": "legacy", "sandbox_base_url": "canon"}}
        assert resolve_key(key, _src(toml=toml)).value == "canon"
        toml = {"transport": {"api_base_url": "b", "api_url": "a"}}
        assert resolve_key(key, _src(toml=toml)).layer == "default"

    def test_flat_retired_toml_is_ignored(self):
        key = ck.get_key("sandbox_base_url")
        assert resolve_key(key, _src(toml={"api_url": "flat"})).layer == "default"

    def test_default_applies_last_and_can_be_disabled(self):
        key = ck.get_key("http_timeout")
        assert resolve_key(key, _src()).value == 30.0
        assert resolve_key(key, _src(), use_default=False) is None

    def test_overrides_ignore_retired_kwarg_names(self):
        key = ck.get_key("sandbox_base_url")
        assert resolve_key(key, _src(overrides={"api_url": "u"})).layer == "default"
        assert resolve_key(key, _src(overrides={"sandbox_base_url": "u2"})).value == "u2"


@pytest.mark.parametrize("key", ALL_KEYS, ids=lambda k: f"{k.scope}.{k.key}")
def test_every_env_name_resolves_its_key(key):
    for name in ck.env_names(key):
        raw = (
            "1"
            if key.type in ("int", "float")
            else "true"
            if key.type == "bool"
            else "DEBUG"
            if key.type == "enum"
            else "value"
        )
        r = resolve_key(key, _src(environ={name: raw}), use_default=False)
        assert r is not None and r.name == name and r.layer == "environ"


@pytest.mark.parametrize("key", ALL_KEYS, ids=lambda k: f"{k.scope}.{k.key}")
def test_every_env_name_resolves_from_dotenv(key):
    for name in ck.env_names(key):
        raw = (
            "1"
            if key.type in ("int", "float")
            else "true"
            if key.type == "bool"
            else "DEBUG"
            if key.type == "enum"
            else "value"
        )
        r = resolve_key(key, _src(dotenv=[{name: raw}]), use_default=False)
        assert r is not None and r.layer == "dotenv"
