"""Policy parsing, validation, presets, merge order and catalogue completeness."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent_sandbox.server import SandboxServer  # noqa: F401  (registers routes)
from agent_sandbox.server.endpoints import ENDPOINTS, OPT_IN_GROUPS, endpoints_of
from agent_sandbox.server.policy import (
    CORE_ENDPOINTS,
    PRESETS,
    PolicyConfigError,
    ServerPolicy,
    parse_size,
    scope_granted,
)
from agent_sandbox.server.router import CapabilityGroup, default_table


def _engine(data: dict[str, Any]) -> Any:
    return ServerPolicy.from_dict(data).bind()


class TestCatalogue:
    def test_every_declared_endpoint_is_mounted_or_virtual(self) -> None:
        mounted = {r.name for r in default_table()._routes}
        assert mounted, "routes not registered"
        virtual = {e.name for e in ENDPOINTS.values() if e.virtual}
        assert set(ENDPOINTS) == mounted | virtual
        assert virtual == {"pty_connect"}

    def test_mounted_routes_carry_their_declaration(self) -> None:
        for route in default_table()._routes:
            declared = ENDPOINTS[route.name]
            assert (route.method, route.path_pattern) == (declared.method, declared.path)
            assert route.group is declared.group
            assert route.spec is declared.spec

    def test_group_is_the_expansion_of_declared_endpoints(self) -> None:
        assert len(endpoints_of("agents")) == 70
        assert "files_upload_stream" in endpoints_of("file_ops")
        assert sum(len(endpoints_of(g)) for g in CapabilityGroup) == len(ENDPOINTS)

    def test_core_endpoints_cannot_be_disabled(self) -> None:
        eng = _engine({"endpoints": {"*": {"enabled": False}}})
        for name in CORE_ENDPOINTS:
            assert eng.rule_for(name).enabled

    def test_core_group_cannot_be_disabled(self) -> None:
        with pytest.raises(PolicyConfigError, match="core"):
            ServerPolicy.from_dict({"groups": {"core": False}})

    def test_agents_endpoints_enable_one_at_a_time(self) -> None:
        eng = ServerPolicy.only("agents_sessions_create").bind()
        create = eng.rule_for("agents_sessions_create")
        assert create.enabled
        assert create.scopes == ("agents:use",)
        assert not eng.rule_for("agents_sessions_events_create").enabled
        assert not eng.rule_for("agents_definitions_create").enabled
        assert not eng.rule_for("shell").enabled
        with pytest.raises(PolicyConfigError, match="not applicable"):
            ServerPolicy.from_dict(
                {"endpoints": {"agents_sessions_create": {"paths": {"allow": ["/srv"]}}}}
            ).bind()


class TestValidation:
    def test_unknown_top_level_key_with_hint(self) -> None:
        with pytest.raises(PolicyConfigError, match="did you mean 'endpoints'"):
            ServerPolicy.from_dict({"endpoint": {}})

    def test_unknown_rule_key_has_json_path(self) -> None:
        with pytest.raises(PolicyConfigError, match=r"endpoints\.files_list\.paths\.alow"):
            ServerPolicy.from_dict({"endpoints": {"files_list": {"paths": {"alow": ["/x"]}}}})

    def test_unknown_exact_endpoint_is_error_with_hint(self) -> None:
        with pytest.raises(PolicyConfigError, match="did you mean 'files_list'"):
            _engine({"endpoints": {"file_list": {"enabled": False}}})

    def test_glob_matching_nothing_is_not_an_error(self) -> None:
        _engine({"endpoints": {"zzz_*": {"enabled": False}}})

    def test_unknown_group_selector(self) -> None:
        with pytest.raises(PolicyConfigError, match="unknown group"):
            _engine({"endpoints": {"group:nope": {"enabled": False}}})

    def test_knob_not_applicable_to_exact_endpoint(self) -> None:
        with pytest.raises(PolicyConfigError, match="not applicable"):
            _engine({"endpoints": {"health": {"limits": {"max_bytes": 5}}}})

    def test_glob_skips_inapplicable_knobs(self) -> None:
        eng = _engine({"endpoints": {"files_*": {"limits": {"max_bytes": 5}}}})
        assert eng.rule_for("files_download_stream").limits["max_bytes"] == 5
        assert "max_bytes" not in eng.rule_for("files_list").limits

    def test_allow_must_be_absolute(self) -> None:
        with pytest.raises(PolicyConfigError, match="absolute"):
            ServerPolicy.from_dict({"endpoints": {"files_list": {"paths": {"allow": ["rel"]}}}})

    @pytest.mark.parametrize("bad", [0, -1, True, "x", 1.5])
    def test_limit_values_validated(self, bad: Any) -> None:
        with pytest.raises(PolicyConfigError):
            ServerPolicy.from_dict({"endpoints": {"files_list": {"limits": {"max_entries": bad}}}})

    def test_bad_version(self) -> None:
        with pytest.raises(PolicyConfigError, match="version"):
            ServerPolicy.from_dict({"version": 2})

    def test_bad_json(self) -> None:
        with pytest.raises(PolicyConfigError, match="JSON"):
            ServerPolicy.from_json("{nope")

    def test_bad_scope_syntax(self) -> None:
        with pytest.raises(PolicyConfigError, match="invalid scope"):
            ServerPolicy.from_dict({"endpoints": {"files_list": {"scopes": ["Bad Scope"]}}})

    def test_input_not_mutated(self) -> None:
        data = {"endpoints": {"files_download_stream": {"limits": {"max_bytes": "5KB"}}}}
        ServerPolicy.from_dict(data)
        assert data["endpoints"]["files_download_stream"]["limits"]["max_bytes"] == "5KB"


class TestSizes:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (5, 5),
            ("5", 5),
            ("5MB", 5_000_000),
            ("5 MB", 5_000_000),
            ("5MiB", 5 * 1024 * 1024),
            ("1GiB", 1024**3),
            ("1.5KB", 1500),
            ("2kib", 2048),
        ],
    )
    def test_parse(self, raw: Any, expected: int) -> None:
        assert parse_size(raw) == expected

    @pytest.mark.parametrize("bad", [0, -3, "abc", "5XB", "", True, None, 1.5])
    def test_parse_rejects(self, bad: Any) -> None:
        with pytest.raises(PolicyConfigError):
            parse_size(bad)

    def test_size_strings_normalised_in_policy(self) -> None:
        eng = _engine({"endpoints": {"files_download_stream": {"limits": {"max_bytes": "5MB"}}}})
        assert eng.rule_for("files_download_stream").limits["max_bytes"] == 5_000_000


class TestTokens:
    def test_plain_token_rejected(self) -> None:
        with pytest.raises(PolicyConfigError, match="plain tokens"):
            ServerPolicy.from_dict(
                {
                    "auth": {
                        "tokens": [
                            {"id": "a", "scopes": ["*"], "token_env": "X", "token_sha256": "a" * 64}
                        ]
                    }
                }
            )

    def test_sha256_must_be_hex64(self) -> None:
        with pytest.raises(PolicyConfigError, match="64 hex"):
            ServerPolicy.from_dict(
                {"auth": {"tokens": [{"id": "a", "scopes": ["*"], "token_sha256": "zz"}]}}
            )

    def test_duplicate_and_reserved_ids(self) -> None:
        tok = {"scopes": ["*"], "token_sha256": "a" * 64}
        with pytest.raises(PolicyConfigError, match="duplicate"):
            ServerPolicy.from_dict({"auth": {"tokens": [{"id": "a", **tok}, {"id": "a", **tok}]}})
        with pytest.raises(PolicyConfigError, match="non-empty"):
            ServerPolicy.from_dict({"auth": {"tokens": [{"id": "", **tok}]}})

    def test_missing_env_var_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ABX_TEST_TOK", raising=False)
        policy = ServerPolicy.from_dict(
            {"auth": {"tokens": [{"id": "a", "scopes": ["*"], "token_env": "ABX_TEST_TOK"}]}}
        )
        with pytest.raises(PolicyConfigError, match="not set"):
            policy.bind()
        with pytest.raises(PolicyConfigError, match="not set"):
            SandboxServer(policy=policy)


class TestScopes:
    @pytest.mark.parametrize(
        ("granted", "required", "ok"),
        [
            (["*"], "files:read", True),
            (["files:*"], "files:write", True),
            (["files:read"], "files:read", True),
            (["files:read"], "files:write", False),
            (["files"], "files:read", False),
            ([], "files:read", False),
            (["filesx:*"], "files:read", False),
        ],
    )
    def test_scope_granted(self, granted: list[str], required: str, ok: bool) -> None:
        assert scope_granted(granted, required) is ok


class TestPresetsAndHelpers:
    def test_default_preset_only_leaves_opt_in_groups_off(self) -> None:
        eng = ServerPolicy.preset("default").bind()
        for name, ep in ENDPOINTS.items():
            assert eng.rule_for(name).enabled is (ep.group not in OPT_IN_GROUPS)

    def test_transfer_only(self) -> None:
        eng = ServerPolicy.preset("transfer-only").bind()
        enabled = {n for n in ENDPOINTS if eng.rule_for(n).enabled}
        assert enabled == {
            "health",
            "capabilities",
            "capabilities_check",
            "files_upload_stream",
            "files_download_stream",
        }

    def test_only_with_paths_and_limits(self) -> None:
        pol = ServerPolicy.only(
            "transfer", paths={"allow": ["/srv/out"]}, limits={"max_bytes": 10, "max_entries": 3}
        )
        eng = pol.bind()
        rule = eng.rule_for("files_download_stream")
        assert rule.enabled and rule.allow == ("/srv/out",)
        assert rule.limits["max_bytes"] == 10
        assert "max_entries" not in rule.limits
        assert not eng.rule_for("files_list").enabled

    def test_only_unknown_endpoint_fails_at_bind(self) -> None:
        with pytest.raises(PolicyConfigError, match="unknown endpoint"):
            ServerPolicy.only("nope").bind()

    def test_read_only_preset_disables_writes_and_exec(self) -> None:
        eng = ServerPolicy.preset("read-only").bind()
        assert eng.rule_for("files_list").enabled
        assert not eng.rule_for("files_delete").enabled
        assert not eng.rule_for("files_upload_stream").enabled
        assert not eng.group_enabled(CapabilityGroup.PROCESS)

    def test_hardened_preset_denies_secrets(self) -> None:
        eng = ServerPolicy.preset("hardened").bind()
        deny = eng.rule_for("files_download_stream").deny
        assert "**/.env" in deny and "/proc" in deny

    def test_locked_preset(self) -> None:
        eng = ServerPolicy.preset("locked").bind()
        assert eng.rule_for("run_command").enabled
        assert not eng.rule_for("files_list").enabled

    def test_unknown_preset(self) -> None:
        with pytest.raises(PolicyConfigError, match="did you mean 'locked'"):
            ServerPolicy.preset("lockd")

    def test_with_endpoint_returns_new_policy(self) -> None:
        base = ServerPolicy.preset("transfer-only")
        derived = base.with_endpoint("files_download_stream", paths={"allow": ["/a"]})
        assert base.revision != derived.revision
        assert derived.bind().rule_for("files_download_stream").allow == ("/a",)
        assert base.bind().rule_for("files_download_stream").allow == ()

    def test_revision_is_stable_and_content_based(self) -> None:
        a = ServerPolicy.from_dict({"preset": "locked"})
        b = ServerPolicy.from_json(json.dumps({"preset": "locked", "version": 1}))
        assert a.revision == b.revision
        assert a.revision != ServerPolicy.from_dict({"preset": "read-only"}).revision

    def test_from_file_json(self, tmp_path: Any) -> None:
        f = tmp_path / "p.json"
        f.write_text(json.dumps({"preset": "locked"}))
        assert ServerPolicy.from_file(str(f)).preset_name == "locked"
        with pytest.raises(PolicyConfigError, match="cannot read"):
            ServerPolicy.from_file(str(tmp_path / "missing.json"))

    def test_from_environment(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        monkeypatch.delenv("ABX_SERVER_POLICY", raising=False)
        monkeypatch.delenv("ABX_SERVER_POLICY_FILE", raising=False)
        assert ServerPolicy.from_environment() is None
        monkeypatch.setenv("ABX_SERVER_POLICY", '{"preset":"locked"}')
        assert ServerPolicy.from_environment().preset_name == "locked"  # type: ignore[union-attr]
        monkeypatch.delenv("ABX_SERVER_POLICY")
        f = tmp_path / "p.json"
        f.write_text('{"preset":"read-only"}')
        monkeypatch.setenv("ABX_SERVER_POLICY_FILE", str(f))
        assert ServerPolicy.from_environment().preset_name == "read-only"  # type: ignore[union-attr]


class TestMergeOrder:
    def test_exact_beats_glob_beats_group_beats_defaults(self) -> None:
        eng = _engine(
            {
                "defaults": {"audit": "off"},
                "endpoints": {
                    "group:file_ops": {"audit": "deny"},
                    "files_*": {"audit": "all"},
                    "files_list": {"audit": "off"},
                },
            }
        )
        assert eng.rule_for("files_list").audit == "off"
        assert eng.rule_for("files_stat").audit == "all"
        assert eng.rule_for("files_upload_stream").audit == "all"
        assert eng.rule_for("shell").audit == "off"

    def test_disabled_wins_at_same_specificity(self) -> None:
        eng = _engine({"endpoints": {"files_*": {"enabled": True}, "*_list": {"enabled": False}}})
        assert not eng.rule_for("files_list").enabled
        assert eng.rule_for("files_stat").enabled

    def test_more_specific_true_overrides_glob_false(self) -> None:
        eng = _engine({"endpoints": {"*": {"enabled": False}, "files_stat": {"enabled": True}}})
        assert eng.rule_for("files_stat").enabled
        assert not eng.rule_for("files_list").enabled

    def test_deny_lists_union_allow_replaces(self) -> None:
        eng = _engine(
            {
                "endpoints": {
                    "files_*": {"paths": {"allow": ["/a"], "deny": ["*.pem"]}},
                    "files_list": {"paths": {"allow": ["/b"], "deny": ["*.key"]}},
                }
            }
        )
        rule = eng.rule_for("files_list")
        assert rule.allow == ("/b",)
        assert set(rule.deny) == {"*.pem", "*.key"}

    def test_deny_params_union(self) -> None:
        eng = _engine(
            {
                "endpoints": {
                    "shell*": {"params": {"deny_commands": ["rm"]}},
                    "shell": {"params": {"deny_commands": ["dd"]}},
                }
            }
        )
        assert set(eng.rule_for("shell").params["deny_commands"]) == {"rm", "dd"}

    def test_user_overrides_preset(self) -> None:
        eng = ServerPolicy.preset(
            "transfer-only",
            endpoints={"files_list": {"enabled": True}, "files_upload_stream": {"enabled": False}},
        ).bind()
        assert eng.rule_for("files_list").enabled
        assert not eng.rule_for("files_upload_stream").enabled

    def test_scopes_replace_catalogue_default(self) -> None:
        eng = _engine({"endpoints": {"files_download_stream": {"scopes": ["dl:get"]}}})
        assert eng.rule_for("files_download_stream").scopes == ("dl:get",)


class TestGroups:
    """A group is only an alias that expands to endpoint rules; there is no second layer."""

    def test_policy_groups_never_touch_the_table(self) -> None:
        before = default_table().group_overrides
        srv = SandboxServer(policy={"groups": {"process": False}})
        assert not srv.policy_engine.group_enabled(CapabilityGroup.PROCESS)
        assert default_table().group_overrides == before

    def test_policy_can_enable_default_off_group(self) -> None:
        eng = ServerPolicy.from_dict({"groups": {"dev_tools": True}}).bind()
        assert eng.group_enabled(CapabilityGroup.DEV_TOOLS)
        assert eng.rule_for("code_run").enabled

    def test_groups_accepts_a_list_of_aliases(self) -> None:
        eng = ServerPolicy.from_dict({"groups": ["browser", "dev_tools"]}).bind()
        assert eng.rule_for("browser_navigate").enabled
        assert eng.rule_for("git_status").enabled
        assert not eng.rule_for("agents_sessions_create").enabled

    def test_groups_list_rejects_unknown_names(self) -> None:
        with pytest.raises(PolicyConfigError, match="did you mean 'browser'"):
            ServerPolicy.from_dict({"groups": ["browsr"]})

    def test_exact_endpoint_rule_beats_group_alias(self) -> None:
        eng = ServerPolicy.from_dict(
            {
                "groups": {"file_ops": False},
                "endpoints": {"files_download_stream": {"enabled": True}},
            }
        ).bind()
        assert eng.rule_for("files_download_stream").enabled
        assert not eng.rule_for("files_upload_stream").enabled

    def test_exact_enable_inside_a_default_off_group_has_a_reason_for_the_rest(self) -> None:
        eng = ServerPolicy.only("agents_sessions_create").bind()
        assert eng.rule_for("agents_sessions_create").enabled
        rest = eng.rule_for("agents_definitions_list")
        assert not rest.enabled
        assert rest.disabled_by == "policy:endpoints.*"

    def test_default_off_group_names_the_way_to_enable_it(self) -> None:
        rule = ServerPolicy.from_dict({}).bind().rule_for("agents_sessions_create")
        assert not rule.enabled
        assert rule.disabled_by == "default:opt-in:agents"
        assert "ABX_SERVER_ENABLED_GROUPS=agents" in rule.disabled_message()

    def test_env_alias_expands_to_endpoints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ABX_SERVER_ENABLED_GROUPS", "agents, core")
        eng = ServerPolicy.from_dict({}).bind()
        assert all(eng.rule_for(n).enabled for n in endpoints_of("agents"))
        assert not eng.rule_for("code_run").enabled

    def test_env_alias_beats_policy_groups_but_not_exact_rules(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ABX_SERVER_ENABLED_GROUPS", "dev_tools")
        eng = ServerPolicy.from_dict(
            {"groups": {"dev_tools": False}, "endpoints": {"code_run": {"enabled": False}}}
        ).bind()
        assert eng.rule_for("git_status").enabled
        assert not eng.rule_for("code_run").enabled
        assert eng.rule_for("code_run").disabled_by == "policy:endpoints.code_run"

    def test_env_alias_rejects_unknown_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ABX_SERVER_ENABLED_GROUPS", "agent")
        with pytest.raises(PolicyConfigError, match="did you mean 'agents'"):
            ServerPolicy.from_dict({}).bind()

    def test_removed_disabled_groups_variable_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ABX_SERVER_DISABLED_GROUPS", "file_ops")
        assert ServerPolicy.from_dict({}).bind().rule_for("files_upload_stream").enabled

    def test_table_alias_is_a_lower_layer_than_the_policy(self) -> None:
        table = default_table()
        table.enable_group(CapabilityGroup.AGENTS)
        eng = ServerPolicy.from_dict({}).bind(table)
        assert eng.rule_for("agents_sessions_create").enabled
        eng_off = ServerPolicy.from_dict({"groups": {"agents": False}}).bind(table)
        assert not eng_off.rule_for("agents_sessions_create").enabled

    def test_engine_follows_later_table_changes(self) -> None:
        table = default_table()
        eng = ServerPolicy.from_dict({}).bind(table)
        assert not eng.rule_for("browser_navigate").enabled
        table.enable_group(CapabilityGroup.BROWSER)
        assert eng.rule_for("browser_navigate").enabled
        table.disable_group(CapabilityGroup.BROWSER)
        assert not eng.rule_for("browser_navigate").enabled

    def test_group_summary_is_derived_from_endpoints(self) -> None:
        eng = ServerPolicy.only("agents_sessions_create").bind()
        summary = eng.group_summary()
        assert summary["agents"] == {"enabled": 1, "total": 70}
        assert eng.groups()["agents"] is True
        assert eng.groups()["file_ops"] is False

    def test_custom_route_follows_its_group_alias(self) -> None:
        from agent_sandbox.server.router import RouteTable

        table = RouteTable()
        table.register("GET", "/x", lambda r: None, group=CapabilityGroup.BROWSER, name="x")
        eng = ServerPolicy.from_dict({}).bind(table)
        assert not eng.rule_for("x").enabled
        table.enable_group(CapabilityGroup.BROWSER)
        assert eng.rule_for("x").enabled

    def test_presets_reference_known_things(self) -> None:
        for name in PRESETS:
            ServerPolicy.preset(name).bind()


class TestLint:
    def test_l1_exec_with_path_scoping(self) -> None:
        pol = ServerPolicy.from_dict({"endpoints": {"files_*": {"paths": {"allow": ["/srv"]}}}})
        assert any(w.startswith("L1") for w in pol.lint())

    def test_l1_not_raised_when_exec_disabled(self) -> None:
        pol = ServerPolicy.from_dict(
            {
                "groups": {"process": False},
                "endpoints": {"files_*": {"paths": {"allow": ["/srv"]}}},
            }
        )
        assert not any(w.startswith("L1") for w in pol.lint())

    def test_l2_root_allow(self) -> None:
        pol = ServerPolicy.from_dict({"endpoints": {"files_list": {"paths": {"allow": ["/"]}}}})
        assert any(w.startswith("L2") for w in pol.lint())

    def test_l4_overwrite_without_allow(self) -> None:
        pol = ServerPolicy.from_dict(
            {"endpoints": {"files_upload_stream": {"params": {"overwrite": False}}}}
        )
        assert any(w.startswith("L4") for w in pol.lint())

    def test_clean_policy_has_no_warnings(self) -> None:
        assert ServerPolicy.preset("hardened").lint() == []

    def test_explain(self) -> None:
        pol = ServerPolicy.only("files_download_stream", paths={"allow": ["/srv/out"]})
        assert pol.explain("files_download_stream", path="/srv/out/x")["allowed"] is True
        denied = pol.explain("files_download_stream", path="/etc/passwd")
        assert denied["allowed"] is False and denied["code"] == "path_not_allowed"
        assert pol.explain("files_list")["code"] == "endpoint_disabled"
        assert (
            pol.explain("files_download_stream", scopes=["files:write"])["code"] == "missing_scope"
        )
        assert pol.explain("nope")["code"] == "unknown_endpoint"
