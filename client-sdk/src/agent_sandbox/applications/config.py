"""Explicit environment wiring for packaged application revisions."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .executors import ChatCompletionsModel, ExternalAgentExecutor, InSandboxAgentExecutor
from .models import Application, Principal
from .runtime import ApplicationRuntime
from .store import Store

if TYPE_CHECKING:
    from .runtime import ExecutionContext, Executor


class FileAuthenticator:
    """Reload a mounted SHA256 token allowlist for revocation on every request.

    Format: ``{"tokens":[{"sha256":"<64 hex>","owner":"team", "revisions":["rev"],
    "scopes":["runs:read","runs:write"]}]}``. No raw bearer tokens are stored.
    Production deployments may inject their own JWT/OIDC authenticator instead.
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def __call__(self, token: str) -> Principal | None:
        """Fail closed on missing/malformed/revoked credentials without logging."""
        if not token or len(token) > 4096:
            return None
        try:
            if self._path.stat().st_size > 262144:
                return None
            value = json.loads(self._path.read_text())
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            for entry in value["tokens"]:
                if hmac.compare_digest(token_hash, entry["sha256"]):
                    if (
                        not isinstance(entry["owner"], str)
                        or not entry["owner"]
                        or not isinstance(entry["revisions"], list)
                        or not isinstance(entry["scopes"], list)
                        or not all(isinstance(v, str) for v in entry["revisions"] + entry["scopes"])
                    ):
                        return None
                    return Principal(
                        entry["owner"], frozenset(entry["revisions"]), frozenset(entry["scopes"])
                    )
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None


def application_from_env() -> Application:
    """Read the CLI-packaged non-secret application subsection and ready sandbox ref."""
    spec = json.loads(os.environ["ABX_APP_SPEC_JSON"])
    if not isinstance(spec, dict):
        raise ValueError("Application spec must be a JSON object")
    runtime, sandbox, limits = spec["runtime"], spec["sandbox"], spec.get("limits", {})
    ready = os.environ["ABX_APP_SANDBOX_TEMPLATE"]
    provider = os.environ["ABX_APP_SANDBOX_PROVIDER"]
    # Retain execution-affecting references only. Hook bodies/deployment config
    # belong to the host/CLI and cannot run inside a run worker.
    snapshot = {
        "runtime": runtime,
        "sandbox": {**sandbox, "template": ready, "provider": provider},
        "state": spec.get("state", {}),
        "bindings": spec.get("bindings", {}),
    }
    if runtime["placement"] == "external":
        endpoint = os.environ["ABX_APP_MODEL_ENDPOINT"]
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Model endpoint must be a non-secret HTTPS URL without query or userinfo"
            )
        snapshot["model"] = {
            "name": os.environ["ABX_APP_MODEL"],
            "endpoint": endpoint,
            "credentialBinding": spec.get("bindings", {}).get("model-access", "model-access"),
        }
    else:
        snapshot["runtime"] = {**runtime, "localAgent": os.getenv("ABX_APP_LOCAL_AGENT", "codex")}
    return Application(
        os.environ["ABX_APP_REVISION"],
        runtime["placement"],
        snapshot,
        max_run_seconds=limits.get("maxRunSeconds", 900),
        max_tool_seconds=limits.get("maxToolSeconds", 60),
        max_concurrent_runs=limits.get("maxConcurrentRuns", 10),
        max_queued_runs=limits.get("maxQueuedRuns", 100),
        max_runs_per_minute=limits.get("maxRunsPerMinute", 60),
        max_output_bytes=limits.get("maxOutputBytes", 65536),
        max_events=limits.get("maxEventsPerRun", 10000),
        max_artifact_bytes=limits.get("maxArtifactBytes", 10485760),
    )


def default_factory() -> ApplicationRuntime:
    """Wire production PostgreSQL, explicit model access and signed FC task delivery.

    Binding references are resolved by the deployment environment into these env
    variables/mounted files. They are never treated as secret values themselves.
    A custom ``ABX_APP_FACTORY=module:function`` can supply different adapters.
    """
    from .fc import FCTaskSender

    app = application_from_env()
    store = Store(os.environ["ABX_APP_DATABASE_URL"], local=os.getenv("ABX_APP_LOCAL") == "1")
    auth = FileAuthenticator(os.environ["ABX_APP_AUTH_FILE"])

    async def sandbox_factory(context: ExecutionContext) -> Any:
        from agent_sandbox import AsyncSandbox, ProviderSandbox

        sandbox = app.snapshot["sandbox"]
        metadata = {"abxApplicationRun": context.run_id, "abxApplicationRevision": app.revision}
        if app.placement == "external" and sandbox["provider"] == "alicloud-express":
            return await AsyncSandbox.create(
                template=sandbox["template"], timeout=app.max_run_seconds + 60, metadata=metadata
            )
        return await ProviderSandbox.create(
            template=sandbox["template"],
            provider=sandbox["provider"],
            timeout=app.max_run_seconds + 60,
            metadata=metadata,
        )

    def executor_factory(application: Application) -> Executor:
        runtime = application.snapshot["runtime"]
        if application.placement == "in-sandbox":
            if runtime.get("profile", "server-core-agents") != "server-core-agents":
                raise ValueError("Managed B requires the core Agents API profile")
            return InSandboxAgentExecutor(sandbox_factory, runtime=runtime["localAgent"])
        return ExternalAgentExecutor(
            ChatCompletionsModel(
                application.snapshot["model"]["endpoint"],
                application.snapshot["model"]["name"],
                os.environ["ABX_APP_MODEL_API_KEY"],
            ),
            sandbox_factory,
            tool_seconds=application.max_tool_seconds,
        )

    return ApplicationRuntime(
        store,
        {app.revision: app},
        executor_factory,
        FCTaskSender(
            os.environ["ABX_APP_FC_ENDPOINT"],
            os.environ["ABX_APP_WORKER_FUNCTION"],
            os.environ["ABX_APP_INTERNAL_TOKEN"],
        ),
        auth,
    )
