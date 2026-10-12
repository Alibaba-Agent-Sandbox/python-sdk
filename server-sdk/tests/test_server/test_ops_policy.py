"""``Policy.from_engine``: one decision source answers the v1 dispatcher and the pipeline."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from easy_sandbox.server.app import SandboxServer
from easy_sandbox.server.core import (
    OpNotEnabled,
    Pipeline,
    Policy,
    Principal,
    Registry,
    build_registry,
)
from easy_sandbox.server.policy import PolicyDenied
from easy_sandbox.server.registry import CommandRegistry
from easy_sandbox.server.router import default_table

READER = "reader-token-123456"
ADMIN = "admin-token-abcdef"


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def server_with(policy: dict[str, Any]) -> SandboxServer:
    return SandboxServer(host="127.0.0.1", registry=CommandRegistry(), policy=policy)


def tokens(**extra: Any) -> dict[str, Any]:
    return {
        "auth": {
            "tokens": [
                {"id": "reader", "token_sha256": sha(READER), "scopes": ["files:read"]},
                {"id": "admin", "token_sha256": sha(ADMIN), "scopes": ["*"]},
            ]
        },
        **extra,
    }


@pytest.fixture(autouse=True)
def _no_ambient_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EBX_SERVER_TOKEN", "EBX_SERVER_POLICY", "EBX_SERVER_POLICY_FILE"):
        monkeypatch.delenv(name, raising=False)


class TestFromEngine:
    def test_wraps_the_engine_of_the_server(self) -> None:
        server = server_with(tokens())
        assert server.policy_engine is not None
        policy = Policy.from_engine(server.policy_engine)
        assert policy.engine is server.policy_engine
        assert policy.table is server.policy_engine.table
        assert policy.configured and policy.revision == server.policy_engine.policy.revision

    @pytest.mark.parametrize(
        "extra",
        [
            {},
            {"endpoints": {"shell": {"enabled": False}}},
            {"groups": {"file_ops": False}},
            {"endpoints": {"files_list": {"paths": {"allow": ["/tmp"]}}}},
        ],
    )
    def test_peek_agrees_with_admit_for_every_operation(self, extra: dict[str, Any]) -> None:
        server = server_with(tokens(**extra))
        engine = server.policy_engine
        assert engine is not None
        policy = Policy.from_engine(engine)
        registry = build_registry(server.route_table, CommandRegistry())
        principals = [
            Principal("reader", scopes=frozenset({"files:read"})),
            Principal("admin", scopes=frozenset({"*"})),
            Principal("nobody", scopes=frozenset()),
        ]
        for operation in registry.all().values():
            for principal in principals:
                verdict = policy.peek(operation, principal)
                try:
                    policy.admit(operation, principal).close()
                    admitted = True
                except (OpNotEnabled, PolicyDenied):
                    admitted = False
                assert verdict.allowed == admitted, (operation.id, principal.id, verdict)

    def test_decision_matches_the_engine_directly(self) -> None:
        server = server_with(tokens(endpoints={"shell": {"enabled": False}}))
        engine = server.policy_engine
        assert engine is not None
        policy = Policy.from_engine(engine)
        registry = build_registry(server.route_table, CommandRegistry())
        reader = Principal("reader", scopes=frozenset({"files:read"}))
        with pytest.raises(PolicyDenied) as direct:
            engine.admit(engine._routes["system_info"], _identity(reader))
        with pytest.raises(PolicyDenied) as bridged:
            policy.admit(registry.get("system.info"), reader)  # type: ignore[arg-type]
        assert (direct.value.code, direct.value.status) == (
            bridged.value.code,
            bridged.value.status,
        )
        with pytest.raises(OpNotEnabled):
            policy.admit(registry.get("commands.run"), reader)  # type: ignore[arg-type]

    def test_rate_buckets_are_shared_with_the_v1_dispatcher(self) -> None:
        server = server_with(tokens(endpoints={"system_info": {"limits": {"rate_per_minute": 1}}}))
        engine = server.policy_engine
        assert engine is not None
        policy = Policy.from_engine(engine)
        registry = build_registry(server.route_table, CommandRegistry())
        admin = Principal("admin", scopes=frozenset({"*"}))
        engine.admit(engine._routes["system_info"], _identity(admin))[1]()
        with pytest.raises(PolicyDenied) as raised:
            policy.admit(registry.get("system.info"), admin)  # type: ignore[arg-type]
        assert raised.value.code == "rate_limited" and raised.value.status == 429

    def test_concurrency_slot_is_held_until_the_stream_is_closed(self) -> None:
        server = server_with(tokens(endpoints={"shell_stream": {"limits": {"max_concurrency": 1}}}))
        engine = server.policy_engine
        assert engine is not None
        pipeline = Pipeline(server.route_table, Policy.from_engine(engine), CommandRegistry())
        admin = Principal("admin", scopes=frozenset({"*"}))
        first = pipeline.call("commands.stream", {"command": "echo a"}, principal=admin)
        assert first.stream is not None and first.status == 200
        second = pipeline.call("commands.stream", {"command": "echo a"}, principal=admin)
        assert second.status == 429 and second.body["code"] == "concurrency_limited"
        first.close()
        first.close()
        third = pipeline.call("commands.stream", {"command": "echo a"}, principal=admin)
        assert third.status == 200
        third.close()

    def test_discovery_limits_come_from_the_rule(self) -> None:
        server = server_with(tokens(endpoints={"system_info": {"limits": {"rate_per_minute": 5}}}))
        engine = server.policy_engine
        assert engine is not None
        policy = Policy.from_engine(engine)
        registry = build_registry(server.route_table, CommandRegistry())
        effective = policy.limits_of(registry.get("system.info"))  # type: ignore[arg-type]
        assert effective == {"limits": {"rate_per_minute": 5}, "scopes": ["system:read"]}


def _identity(principal: Principal) -> Any:
    from easy_sandbox.server.policy import Identity

    return Identity(principal.id, principal.scopes)


class TestWithoutEngine:
    def test_open_policy_is_the_group_gate(self) -> None:
        table = default_table()
        policy = Policy.open(table)
        registry = build_registry(table, CommandRegistry())
        anyone = Principal.anonymous()
        assert policy.peek(registry.get("files.list"), anyone).allowed  # type: ignore[arg-type]
        verdict = policy.peek(registry.get("browser.click"), anyone)  # type: ignore[arg-type]
        assert not verdict.allowed and verdict.reason == "group_disabled"
        with pytest.raises(OpNotEnabled):
            policy.admit(registry.get("browser.click"), anyone)  # type: ignore[arg-type]
        assert not policy.configured and policy.revision == "" and policy.preset is None

    def test_authentication(self) -> None:
        table = default_table()
        assert Policy.open(table).authenticate({}) == Principal.anonymous()
        policy = Policy.open(table, auth_token="s3cret-token-value")
        assert policy.authenticate({}) is None
        assert policy.authenticate({"X-Access-Token": "wrong"}) is None
        principal = policy.authenticate({"x-access-token": "s3cret-token-value"})
        assert principal is not None and principal.id == "token" and "*" in principal.scopes
        assert policy.authenticate({"Authorization": "Bearer s3cret-token-value"}) is not None
        assert policy.authenticate({"Authorization": "bearer s3cret-token-value"}) is not None
        assert (
            policy.authenticate(
                {"Authorization": "Bearer s3cret-token-value", "X-Access-Token": "other"}
            )
            is None
        )

    def test_audit_is_a_noop(self) -> None:
        Policy.open(default_table()).audit(None, None, status=404, code="x", op_id="a.b")


class TestNativeOperations:
    def _pipeline(self) -> Pipeline:
        registry = Registry()

        @registry.op("custom.danger", effects="exec")
        def danger(ctx: Any) -> dict[str, bool]:
            return {"ran": True}

        @registry.op("core.describe", effects="read", group="core")
        def describe(ctx: Any) -> dict[str, str]:
            return {"who": ctx.principal.id}

        @registry.op("core.echo", effects="read", group="core")
        def echo(ctx: Any, text: str, times: int = 1) -> dict[str, Any]:
            return {"text": text * times}

        table = default_table()
        return Pipeline(table, Policy.open(table), registry=registry)

    def test_native_ops_without_a_v1_rule_stay_unmounted(self) -> None:
        pipeline = self._pipeline()
        outcome = pipeline.call("custom.danger")
        assert outcome.status == 404 and outcome.body["code"] == "op.not_enabled"
        assert pipeline.call("core.describe").body == {"who": "anonymous"}

    def test_argument_validation_of_native_handlers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from easy_sandbox.server.core import policy as policy_module

        monkeypatch.setattr(
            policy_module, "NATIVE_OPEN_IDS", policy_module.NATIVE_OPEN_IDS | {"core.echo"}
        )
        pipeline = self._pipeline()
        ok = pipeline.call("core.echo", {"text": "ab", "times": 2})
        assert (ok.status, ok.body) == (200, {"text": "abab"})
        assert pipeline.call("core.echo", {}).body["code"] == "args.missing"
        assert pipeline.call("core.echo", {"text": "a", "x": 1}).body["code"] == "args.unknown"
        assert pipeline.call("core.echo", {"text": 5}).body["code"] == "args.type"
        assert pipeline.call("core.echo", {"text": "a", "times": True}).body["code"] == "args.type"
        assert pipeline.call("core.echo", {"text": "a", "times": None}).status == 200
