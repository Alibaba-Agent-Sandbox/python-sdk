"""Registry invariants and the pure resolver (precedence + alias table)."""

from __future__ import annotations

import pytest

from easy_sandbox.utils import config_keys as ck
from easy_sandbox.utils.config_keys import Sources, resolve_key

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
            "llm_api_key",
            "github_token",
            "acr_password",
            "mcp_auth_token",
        } <= secrets

    @pytest.mark.parametrize(
        "legacy",
        [
            "SANDBOX_API_KEY",
            "SANDBOX_API_BASE_URL",
            "SANDBOX_HTTP_TIMEOUT",
            "SANDBOX_LOG_LEVEL",
            "SANDBOX_TEMPLATE",
            "EBX_TEMPLATE",
            "EBX_QWEN_CODE_API_KEY",
            "SANDBOX_REGION",
            "AccessKey",
            "AccessSecret",
            "ACR_NAMESPACE",
            "ACR_REGISTRY",
            "ACR_REPO",
            "ACR_USERNAME",
            "ACR_PASSWORD",
            "ACREE_INSTANCE_ID",
            "ACR_VPC_ID",
            "ACR_VSWITCH_IDS",
            "ACR_SECURITY_GROUP_ID",
            "TEAM_ID",
        ],
    )
    def test_inventory_names_are_all_known(self, legacy):
        known = {a.name for k in ALL_KEYS for a in k.aliases if a.surface == "env"}
        assert legacy in known

    @pytest.mark.parametrize(
        "compat",
        [
            "E2B_API_KEY",
            "E2B_API_URL",
            "E2B_DOMAIN",
            "E2B_TEAM_ID",
            "ALICLOUD_ACCESS_KEY_ID",
            "ALICLOUD_ACCESS_KEY_SECRET",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "DASHSCOPE_API_KEY",
            "BAILIAN_CODING_PLAN_API_KEY",
        ],
    )
    def test_compat_and_native_names_are_known(self, compat):
        known = {
            a.name
            for k in ALL_KEYS
            for a in k.aliases
            if a.surface == "env" and a.kind in ("compat", "native")
        }
        assert compat in known

    def test_e2b_names_are_never_legacy(self):
        for k in ALL_KEYS:
            for a in k.aliases:
                if a.name.startswith("E2B_"):
                    assert a.kind == "compat"

    def test_env_names_order_scoped_canonical_compat_legacy(self):
        key = ck.get_key("sandbox_api_key")
        assert ck.env_names(key, scoped_for="my-prov") == (
            "EBX_MY_PROV_SANDBOX_API_KEY",
            "EBX_SANDBOX_API_KEY",
            "E2B_API_KEY",
            "SANDBOX_API_KEY",
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
            ("e2b", False),
            ("e2b-compat", True),
            ("a", False),
            ("My-Provider", False),
            ("-x", False),
            ("a--b", False),
            ("alicloud-express", False),
            ("alicloud-foo", False),
            ("ebx-foo", False),
            ("x" * 41, False),
            ("1abc", False),
            ("a_b", False),
        ],
    )
    def test_validate_provider_id(self, pid, ok):
        assert (ck.validate_provider_id(pid) is None) is ok

    def test_provider_env_name(self):
        assert ck.provider_env_name("my-provider", "api_token") == "EBX_MY_PROVIDER_API_TOKEN"


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
        assert ck.coerce(ck.get_key("max_retries"), "5") == 5
        assert ck.coerce(ck.get_key("max_retries"), "5.0") == 5
        assert ck.coerce(ck.get_key("max_retries"), "x") is None
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
            environ={"EBX_SANDBOX_API_KEY": "e"},
            dotenv=[{"EBX_SANDBOX_API_KEY": "d1"}, {"EBX_SANDBOX_API_KEY": "d2"}],
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
        src.dotenv = [{}, {"EBX_SANDBOX_API_KEY": "d2"}]
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer_index) == ("d2", 1)
        src.dotenv = []
        r = resolve_key(self.KEY, src)
        assert (r.value, r.layer) == ("t", "toml")

    def test_layer_beats_name_priority(self):
        """A legacy name in a higher layer beats a canonical name in a lower layer."""
        src = _src(
            environ={"SANDBOX_API_KEY": "legacy-env"},
            dotenv=[{"EBX_SANDBOX_API_KEY": "canon-dotenv"}],
        )
        assert resolve_key(self.KEY, src).value == "legacy-env"

    @pytest.mark.parametrize(
        "names",
        [
            ["EBX_SANDBOX_API_KEY", "E2B_API_KEY", "SANDBOX_API_KEY"],
        ],
    )
    def test_name_order_within_layer(self, names):
        environ = {n: n for n in names}
        for i, n in enumerate(names):
            r = resolve_key(self.KEY, _src(environ=environ))
            assert r.value == n, f"step {i}"
            environ.pop(n)

    def test_blank_values_fall_through(self):
        src = _src(
            environ={"EBX_SANDBOX_API_KEY": "  ", "E2B_API_KEY": ""},
            dotenv=[{"SANDBOX_API_KEY": "from-dotenv"}],
        )
        assert resolve_key(self.KEY, src).value == "from-dotenv"

    def test_scoped_name_beats_canonical(self):
        src = _src(
            environ={"EBX_MY_PROV_SANDBOX_API_KEY": "scoped", "EBX_SANDBOX_API_KEY": "plain"}
        )
        assert resolve_key(self.KEY, src, scoped_for="my-prov").value == "scoped"
        assert resolve_key(self.KEY, src).value == "plain"

    def test_scoped_toml_table_beats_transport(self):
        toml = {
            "providers": {"my-prov": {"sandbox_api_key": "scoped"}},
            "transport": {"sandbox_api_key": "plain"},
        }
        assert resolve_key(self.KEY, _src(toml=toml), scoped_for="my-prov").value == "scoped"
        assert resolve_key(self.KEY, _src(toml=toml)).value == "plain"

    def test_toml_name_order(self):
        key = ck.get_key("sandbox_base_url")
        toml = {"transport": {"api_url": "legacy", "sandbox_base_url": "canon"}}
        assert resolve_key(key, _src(toml=toml)).value == "canon"
        toml = {"transport": {"api_base_url": "b", "api_url": "a"}}
        assert resolve_key(key, _src(toml=toml)).value == "a"

    def test_flat_legacy_toml_only_without_transport_table(self):
        key = ck.get_key("sandbox_base_url")
        assert resolve_key(key, _src(toml={"api_url": "flat"})).value == "flat"
        got = resolve_key(key, _src(toml={"api_url": "flat", "transport": {"x": 1}}))
        assert got.layer == "default"

    def test_default_applies_last_and_can_be_disabled(self):
        key = ck.get_key("http_timeout")
        assert resolve_key(key, _src()).value == 30.0
        assert resolve_key(key, _src(), use_default=False) is None

    def test_overrides_accept_legacy_kwarg_names(self):
        key = ck.get_key("sandbox_base_url")
        assert resolve_key(key, _src(overrides={"api_url": "u"})).value == "u"
        assert resolve_key(key, _src(overrides={"api_base_url": "u2"})).value == "u2"


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
