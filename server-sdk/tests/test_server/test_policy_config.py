"""Policy parsing, validation, presets, merge order and catalogue completeness."""

from __future__ import annotations

import json
from typing import Any

import pytest

from easy_sandbox.server import SandboxServer  # noqa: F401  (registers routes)
from easy_sandbox.server.policy import (
    CORE_ENDPOINTS,
    ENDPOINT_CATALOG,
    PRESETS,
    PolicyConfigError,
    ServerPolicy,
    parse_size,
    scope_granted,
)
from easy_sandbox.server.router import CapabilityGroup, default_table


def _engine(data: dict[str, Any]) -> Any:
    return ServerPolicy.from_dict(data).bind()


class TestCatalogue:
    def test_every_builtin_route_has_a_catalogue_entry(self) -> None:
        names = {r.name for r in default_table()._routes if r.group != CapabilityGroup.AGENTS}
        assert names, "routes not registered"
        assert names <= set(ENDPOINT_CATALOG), names - set(ENDPOINT_CATALOG)

    def test_every_catalogue_entry_is_registered_or_virtual(self) -> None:
        names = {r.name for r in default_table()._routes}
        assert set(ENDPOINT_CATALOG) - names <= {"pty_connect"}

    def test_core_endpoints_cannot_be_disabled(self) -> None:
        eng = _engine({"endpoints": {"*": {"enabled": False}}})
        for name in CORE_ENDPOINTS:
            assert eng.rule_for(name).enabled

    def test_core_group_cannot_be_disabled(self) -> None:
        with pytest.raises(PolicyConfigError, match="core"):
            ServerPolicy.from_dict({"groups": {"core": False}})


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
        data = {"endpoints": {"download": {"limits": {"max_bytes": "5KB"}}}}
        ServerPolicy.from_dict(data)
        assert data["endpoints"]["download"]["limits"]["max_bytes"] == "5KB"


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
        with pytest.raises(PolicyConfigError, match="legacy"):
            ServerPolicy.from_dict({"auth": {"tokens": [{"id": "legacy", **tok}]}})

    def test_missing_env_var_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EBX_TEST_TOK", raising=False)
        policy = ServerPolicy.from_dict(
            {"auth": {"tokens": [{"id": "a", "scopes": ["*"], "token_env": "EBX_TEST_TOK"}]}}
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
    def test_default_preset_changes_nothing(self) -> None:
        eng = ServerPolicy.preset("default").bind()
        for name in ENDPOINT_CATALOG:
            assert eng.rule_for(name).enabled

    def test_transfer_only(self) -> None:
        eng = ServerPolicy.preset("transfer-only").bind()
        enabled = {n for n in ENDPOINT_CATALOG if eng.rule_for(n).enabled}
        assert enabled == {
            "health",
            "capabilities",
            "capabilities_check",
            "upload",
            "download",
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
        assert not eng.rule_for("upload").enabled
        assert not eng.table.is_group_enabled(CapabilityGroup.PROCESS)

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
        monkeypatch.delenv("EBX_SERVER_POLICY", raising=False)
        monkeypatch.delenv("EBX_SERVER_POLICY_FILE", raising=False)
        assert ServerPolicy.from_environment() is None
        monkeypatch.setenv("EBX_SERVER_POLICY", '{"preset":"locked"}')
        assert ServerPolicy.from_environment().preset_name == "locked"  # type: ignore[union-attr]
        monkeypatch.delenv("EBX_SERVER_POLICY")
        f = tmp_path / "p.json"
        f.write_text('{"preset":"read-only"}')
        monkeypatch.setenv("EBX_SERVER_POLICY_FILE", str(f))
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
        assert eng.rule_for("upload").audit == "deny"
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
            endpoints={"files_list": {"enabled": True}, "upload": {"enabled": False}},
        ).bind()
        assert eng.rule_for("files_list").enabled
        assert not eng.rule_for("upload").enabled

    def test_scopes_replace_catalogue_default(self) -> None:
        eng = _engine({"endpoints": {"download": {"scopes": ["dl:get"]}}})
        assert eng.rule_for("download").scopes == ("dl:get",)


class TestGroups:
    def test_policy_groups_apply_to_copy_not_default_table(self) -> None:
        before = default_table().is_group_enabled(CapabilityGroup.PROCESS)
        srv = SandboxServer(policy={"groups": {"process": False}})
        assert not srv.route_table.is_group_enabled(CapabilityGroup.PROCESS)
        assert default_table().is_group_enabled(CapabilityGroup.PROCESS) is before

    def test_env_kill_switch_beats_policy_enable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EBX_SERVER_DISABLED_GROUPS", "dev_tools")
        eng = ServerPolicy.from_dict({"groups": {"dev_tools": True}}).bind()
        assert not eng.table.is_group_enabled(CapabilityGroup.DEV_TOOLS)

    def test_policy_can_enable_default_off_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EBX_SERVER_DISABLED_GROUPS", raising=False)
        eng = ServerPolicy.from_dict({"groups": {"dev_tools": True}}).bind()
        assert eng.table.is_group_enabled(CapabilityGroup.DEV_TOOLS)

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
        pol = ServerPolicy.from_dict({"endpoints": {"upload": {"params": {"overwrite": False}}}})
        assert any(w.startswith("L4") for w in pol.lint())

    def test_clean_policy_has_no_warnings(self) -> None:
        assert ServerPolicy.preset("hardened").lint() == []

    def test_explain(self) -> None:
        pol = ServerPolicy.only("download", paths={"allow": ["/srv/out"]})
        assert pol.explain("download", path="/srv/out/x")["allowed"] is True
        denied = pol.explain("download", path="/etc/passwd")
        assert denied["allowed"] is False and denied["code"] == "path_not_allowed"
        assert pol.explain("files_list")["code"] == "endpoint_disabled"
        assert pol.explain("download", scopes=["files:write"])["code"] == "missing_scope"
        assert pol.explain("nope")["code"] == "unknown_endpoint"
