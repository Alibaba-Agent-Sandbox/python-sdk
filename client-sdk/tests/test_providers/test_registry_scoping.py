# ruff: noqa: E501, N812
"""Provider registry, credential scoping/isolation, rest preset, doctor and the module CLI."""

from __future__ import annotations

import json

import pytest

import agent_sandbox.transport.config as cfgmod
from agent_sandbox.models import errors as E
from agent_sandbox.providers import (
    Provider,
    ProviderInfra,
    doctor,
    get_provider,
    installer,
    list_providers,
    parse_sandbox_ref,
    qualify,
    register_provider,
    registry,
    resolve_provider_id,
)
from agent_sandbox.providers.__main__ import main as cli_main
from agent_sandbox.providers.rest_provider import HeaderKeyAuth, RestProvider
from agent_sandbox.transport.config import load_config
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import E2B_COMPATIBLE, LOCAL_PROCESS, write_plugin


class _Py(Provider):
    id = "py-prov"
    kind = "python"
    display_name = "Py"

    async def build_infra(self, config):
        return ProviderInfra(config=config, auth=None, http_client=None, sandbox_protocol=object())


class TestRegistry:
    def test_builtin_identity_and_default(self, iso):  # noqa: F811
        p = get_provider()
        assert p.id == "alicloud-express" == resolve_provider_id()
        assert p.display_name == "Alibaba Cloud Express Edition"
        assert p.display_name_zh == "阿里云极速版"
        assert p.kind == "builtin"
        assert p.supports("files.rw")
        assert not p.supports("storage.mount")
        assert not p.supports("ports.domain")
        assert not p.supports("network.vpc")
        assert not p.supports("templates.deploy")
        assert not p.supports("sandbox.pause")

    def test_register_and_conflicts(self, iso):  # noqa: F811
        register_provider(_Py())
        assert get_provider("py-prov").display_name == "Py"
        with pytest.raises(E.ProviderConflictError):
            register_provider(_Py())
        register_provider(_Py(), replace=True)
        bad = _Py()
        bad.id = "alicloud-express"
        with pytest.raises(E.ProviderConflictError):
            register_provider(bad)

    def test_list_order_and_trust(self, iso, tmp_path):  # noqa: F811
        register_provider(_Py())
        installer.install(str(LOCAL_PROCESS), yes=True)
        rows = list_providers()
        assert [r["id"] for r in rows] == [
            "alicloud-express",
            "local-process",
            "py-prov",
        ]
        assert {r["id"]: r["trust"] for r in rows} == {
            "alicloud-express": "builtin",
            "local-process": "local",
            "py-prov": "python",
        }

    def test_broken_install_is_listed_with_error_not_fatal(self, iso, tmp_path):  # noqa: F811
        installer.install(str(LOCAL_PROCESS), yes=True)
        (installer.store.provider_dir("local-process") / "abx-provider.toml").write_text(
            "garbage ["
        )
        rows = {r["id"]: r for r in list_providers()}
        assert "error" in rows["local-process"]

    def test_unknown_provider_suggests_close_match(self, iso):  # noqa: F811
        installer.install(str(LOCAL_PROCESS), yes=True)
        with pytest.raises(E.ProviderNotFoundError) as exc:
            get_provider("local-proces")
        assert "local-process" in exc.value.suggestion
        with pytest.raises(E.ProviderNotFoundError):
            get_provider("../../etc")

    def test_qualified_refs(self, iso):  # noqa: F811
        installer.install(str(LOCAL_PROCESS), yes=True)
        assert parse_sandbox_ref("local-process:abc") == ("local-process", "abc")
        assert parse_sandbox_ref("abc") == (None, "abc")
        assert parse_sandbox_ref("unknown-prov:abc") == (None, "unknown-prov:abc")
        assert parse_sandbox_ref("local-process:") == (None, "local-process:")
        assert qualify("alicloud-express", "sb1", ambient="alicloud-express") == "sb1"
        assert qualify("alicloud-express", "sb1", ambient="local-process") == "alicloud-express:sb1"
        assert qualify("local-process", "sb1", ambient="alicloud-express") == "local-process:sb1"

    def test_entry_point_discovery(self, iso, monkeypatch):  # noqa: F811
        class EP:
            name = "ep-prov"

            def load(self):
                class Ep(_Py):
                    id = "ep-prov"

                return Ep

        import importlib.metadata as md

        monkeypatch.setattr(md, "entry_points", lambda group=None: [EP()])
        registry.reset_registry()
        assert get_provider("ep-prov").id == "ep-prov"
        assert "ep-prov" in {r["id"] for r in list_providers()}


class TestProviderSelection:
    @pytest.mark.parametrize("where", ["override", "env", "dotenv", "toml"])
    def test_precedence_chain(self, iso, monkeypatch, where):  # noqa: F811
        register_provider(_Py())
        if where == "env":
            monkeypatch.setenv("ABX_PROVIDER", "py-prov")
        elif where == "dotenv":
            iso.write_env("ABX_PROVIDER=py-prov\n")
        elif where == "toml":
            iso.write_toml('[core]\nprovider = "py-prov"\n')
        got = resolve_provider_id("py-prov") if where == "override" else resolve_provider_id()
        assert got == "py-prov"

    def test_override_beats_env_beats_dotenv_beats_toml(self, iso, monkeypatch):  # noqa: F811
        iso.write_toml('[core]\nprovider = "t"\n')
        assert resolve_provider_id() == "t"
        iso.write_env("ABX_PROVIDER=d\n")
        assert resolve_provider_id() == "d"
        monkeypatch.setenv("ABX_PROVIDER", "e")
        assert resolve_provider_id() == "e"
        assert resolve_provider_id("o") == "o"


class TestCredentialIsolation:
    @pytest.fixture
    def installed(self, iso):  # noqa: F811
        installer.install(str(LOCAL_PROCESS), yes=True)
        installer.install(str(E2B_COMPATIBLE), yes=True)
        return iso

    def test_generic_keys_only_reach_builtin_and_consented_inheritors(self, installed, monkeypatch):
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "generic-key-1234")
        monkeypatch.setenv("ABX_SANDBOX_BASE_URL", "https://generic.example")
        assert load_config(provider="alicloud-express").sandbox_api_key == "generic-key-1234"
        assert load_config(provider="local-process").sandbox_api_key is None
        assert load_config(provider="local-process").sandbox_base_url != "https://generic.example"
        c = load_config(provider="e2b-compatible")
        assert (
            c.sandbox_api_key == "generic-key-1234"
            and c.sandbox_base_url == "https://generic.example"
        )

    def test_inherit_without_consent_is_dropped(self, installed, monkeypatch):
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "generic-key-1234")
        import json as _json

        path = installer.store.provider_dir("e2b-compatible") / ".abx-install.json"
        receipt = _json.loads(path.read_text())
        receipt["consented"]["inherit"] = []
        path.write_text(_json.dumps(receipt))
        assert load_config(provider="e2b-compatible").sandbox_api_key is None
        assert registry.get_provider("e2b-compatible").inherit == frozenset()

    def test_scoped_env_beats_generic_for_inheritor(self, installed, monkeypatch):
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "generic")
        monkeypatch.setenv("ABX_E2B_COMPATIBLE_SANDBOX_API_KEY", "scoped")
        assert load_config(provider="e2b-compatible").sandbox_api_key == "scoped"
        assert load_config(provider="alicloud-express").sandbox_api_key == "generic"

    def test_provider_defaults_beat_builtin_defaults(self, installed):
        c = load_config(provider="e2b-compatible")
        assert c.sandbox_base_url == "https://api.e2b.dev" and c.sandbox_domain == "e2b.dev"

    def test_provider_scoped_options_from_each_layer(self, installed, monkeypatch):
        assert load_config(provider="local-process").provider_options == {"debug": False}
        installed.write_toml("[providers.local-process]\ndebug = true\n")
        assert load_config(provider="local-process").provider_options["debug"] is True
        installed.write_env("ABX_LOCAL_PROCESS_TOKEN=from-dotenv\n")
        assert load_config(provider="local-process").provider_options["token"] == "from-dotenv"
        monkeypatch.setenv("ABX_LOCAL_PROCESS_TOKEN", "from-env")
        cfgmod.reset_config()
        assert load_config(provider="local-process").provider_options["token"] == "from-env"
        assert (
            load_config(
                provider="local-process", provider_options={"token": "kw"}
            ).provider_options["token"]
            == "kw"
        )

    def test_other_providers_options_do_not_leak(self, installed, monkeypatch):
        monkeypatch.setenv("ABX_LOCAL_PROCESS_TOKEN", "tok")
        assert "token" not in load_config(provider="alicloud-express").provider_options
        assert load_config(provider="alicloud-express").access_key_secret is None

    def test_builtin_scoped_credentials_do_not_reach_plugins(self, installed, monkeypatch):
        monkeypatch.setenv("ALICLOUD_ACCESS_KEY_ID", "ak")
        monkeypatch.setenv("ALICLOUD_ACCESS_KEY_SECRET", "sk")
        c = load_config(provider="local-process")
        assert c.access_key_id is None and c.access_key_secret is None
        assert "access_key_id" not in c.provider_options


class TestRestProvider:
    async def test_bearer_and_header_auth(self):
        assert await HeaderKeyAuth("k").get_headers() == {"Authorization": "Bearer k"}
        assert await HeaderKeyAuth(" k ", "header", "X-Key").get_headers() == {"X-Key": "k"}
        with pytest.raises(E.InvalidAPIKeyError):
            HeaderKeyAuth("  ")

    async def test_build_infra_uses_inherited_key(self, iso, monkeypatch):  # noqa: F811
        installer.install(str(E2B_COMPATIBLE), yes=True)
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "abcd1234")
        prov = registry.get_provider("e2b-compatible")
        assert isinstance(prov, RestProvider)
        infra = await prov.build_infra(load_config(provider="e2b-compatible"))
        try:
            assert await infra.auth.get_headers() == {"X-API-Key": "abcd1234"}
            assert infra.config.sandbox_base_url == "https://api.e2b.dev"
        finally:
            await infra.http_client.close()

    async def test_missing_key_is_credentials_error(self, iso):  # noqa: F811
        installer.install(str(E2B_COMPATIBLE), yes=True)
        with pytest.raises(E.InvalidCredentialsError):
            await registry.get_provider("e2b-compatible").build_infra(
                load_config(provider="e2b-compatible")
            )

    def test_describe_lists_inherit_and_features(self, iso):  # noqa: F811
        installer.install(str(E2B_COMPATIBLE), yes=True)
        d = registry.get_provider("e2b-compatible").describe()
        assert d["inherit"] == ["sandbox_api_key", "sandbox_base_url", "sandbox_domain"]
        assert "files.rw" in d["features"] and "storage.mount" not in d["features"]


class TestDoctor:
    def test_reference_plugin_passes(self, local_process):
        report = doctor.doctor("local-process")
        assert report["ok"], report
        assert [c["name"] for c in report["checks"]] == [
            "installed",
            "integrity",
            "config",
            "handshake",
        ]

    def test_not_installed(self, iso):  # noqa: F811
        report = doctor.doctor("nothing-here")
        assert not report["ok"] and report["checks"][0]["name"] == "installed"

    def test_tamper_stops_before_spawn(self, local_process):
        (installer.store.provider_dir("local-process") / "provider.py").write_text(
            "raise SystemExit(9)\n"
        )
        report = doctor.doctor("local-process")
        assert not report["ok"]
        assert [c["name"] for c in report["checks"]] == ["installed", "integrity"]

    def test_missing_config_stops_before_spawn(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(
            tmp_path / "s",
            extra='[config.fields.token]\ntype = "string"\nsecret = true\ncredential = true\nrequired = true\n',
        )
        installer.install(str(src), yes=True)
        report = doctor.doctor("demo-prov")
        assert [c["name"] for c in report["checks"]][-1] == "config" and not report["ok"]

    def test_handshake_failure_is_reported(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "s", files={"provider.py": "import sys\nsys.exit(5)\n"})
        installer.install(str(src), yes=True)
        report = doctor.doctor("demo-prov")
        assert report["checks"][-1]["name"] == "handshake" and not report["checks"][-1]["ok"]

    def test_verify_handshake_raises_install_error(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "s", files={"provider.py": "import sys\nsys.exit(5)\n"})
        with pytest.raises(E.ProviderInstallError):
            installer.install(str(src), yes=True, verify=doctor.verify_handshake)
        assert installer.store.list_installed_ids() == []

    async def test_doctor_inside_running_loop(self, local_process):
        assert doctor.doctor("local-process")["ok"]


class TestModuleCli:
    def run(self, capsys, *argv):
        code = cli_main(list(argv))
        out = capsys.readouterr()
        return code, out.out, out.err

    def test_full_lifecycle(self, iso, capsys):  # noqa: F811
        code, out, _ = self.run(capsys, "--json", "list")
        rows = json.loads(out)
        assert code == 0 and rows[0]["id"] == "alicloud-express" and rows[0]["default"] is True

        code, out, _ = self.run(capsys, "--json", "install", str(LOCAL_PROCESS), "--yes")
        assert code == 0 and json.loads(out)["id"] == "local-process"

        code, out, _ = self.run(capsys, "--json", "info", "local-process")
        info = json.loads(out)
        assert info["kind"] == "exec" and info["receipt"]["trust"] == "local"
        assert {f["key"] for f in info["config_fields"]} == {"token", "debug"}
        assert (
            next(f for f in info["config_fields"] if f["key"] == "token")["env"]
            == "ABX_LOCAL_PROCESS_TOKEN"
        )

        code, out, _ = self.run(capsys, "--json", "doctor", "local-process")
        assert code == 0 and json.loads(out)["ok"]

        code, out, _ = self.run(capsys, "default", "local-process")
        assert code == 0
        code, out, _ = self.run(capsys, "--json", "default")
        assert json.loads(out) == {"default": "local-process"}
        code, out, _ = self.run(capsys, "default", "alicloud-express")
        code, out, _ = self.run(capsys, "--json", "default")
        assert json.loads(out) == {"default": "alicloud-express"}

        code, out, _ = self.run(capsys, "--json", "uninstall", "local-process")
        assert code == 0 and json.loads(out)["removed"]

    def test_errors_map_to_exit_codes(self, iso, capsys):  # noqa: F811
        code, _, err = self.run(capsys, "info", "ghost-prov")
        assert code == 4 and "E8001" in err
        code, _, err = self.run(capsys, "--json", "install", "/definitely/not/here", "--yes")
        assert code == 1 and json.loads(err)["error"]["code"] == "E8010"
        code, _, err = self.run(capsys, "default", "ghost-prov")
        assert code == 4
        code, _, err = self.run(capsys, "install", str(LOCAL_PROCESS))
        assert code == 2 and "E8012" in err
        code, _, err = self.run(capsys, "uninstall", "alicloud-express")
        assert code == 1

    def test_update_all_skips_builtin(self, iso, capsys):  # noqa: F811
        code, out, _ = self.run(capsys, "--json", "update", "--check")
        assert code == 0 and json.loads(out) == []
