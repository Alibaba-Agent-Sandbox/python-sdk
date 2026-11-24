"""Default-context interpreter for SandboxSets that expose Jupyter on port 49999."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from agent_sandbox.models.errors import ProviderFeatureNotSupportedError, ProviderProtocolError
from agent_sandbox.providers.shared.e2b.code_interpreter import UnsupportedCodeProtocol

from .sandbox import PROVIDER_ID, Gateway

if TYPE_CHECKING:
    from agent_sandbox.providers.shared.e2b.auth import EnvdTokenManager
    from agent_sandbox.transport.http import HttpClient

_CODE_PORT = 49999


def _result(body: str) -> dict[str, Any]:
    stdout: list[str] = []
    stderr: list[str] = []
    text = ""
    exit_code = 0
    completed = False
    for line in body.splitlines():
        if not line.strip():
            continue
        if completed:
            raise ProviderProtocolError(
                "Container Edition returned output after interpreter completion."
            )
        try:
            event = json.loads(line)
        except ValueError:
            raise ProviderProtocolError(
                "Container Edition returned malformed interpreter output."
            ) from None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ProviderProtocolError("Container Edition returned invalid interpreter events.")
        kind = event["type"]
        if kind == "end_of_execution":
            completed = True
        elif kind == "stdout":
            stdout.append(str(event.get("text") or ""))
        elif kind == "stderr":
            stderr.append(str(event.get("text") or ""))
        elif kind == "result" and (event.get("is_main_result") or not text):
            text = str(event.get("text") or text)
        elif kind in {"error", "unexpected_end_of_execution"}:
            exit_code = 1
            stderr.append(str(event.get("text") or event.get("value") or event.get("name") or ""))
    if not completed:
        raise ProviderProtocolError(
            "Container Edition interpreter output ended without completion."
        )
    output = "".join(stdout)
    return {
        "stdout": output,
        "stderr": "".join(stderr),
        "text": text or output,
        "exitCode": exit_code,
    }


class JupyterProtocol:
    def __init__(self, http: HttpClient, gateway: Gateway) -> None:
        self._unsupported = UnsupportedCodeProtocol(PROVIDER_ID)
        self._http = http
        self._gateway = gateway

    def __getattr__(self, name: str) -> Any:
        return getattr(self._unsupported, name)

    async def run_code(
        self,
        sandbox_id: str,
        envd_url: str,
        envd_token: EnvdTokenManager,
        *,
        code: str,
        language: str = "python",
        mode: str = "stateless",
        timeout: int = 30,
        envs: dict[str, str] | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        if mode != "default-context" or options.get("context_id") is not None:
            return await self._unsupported.run_code(mode=mode, **options)
        if any(options.get(name) is not None for name in ("on_stdout", "on_stderr", "on_result")):
            raise ProviderFeatureNotSupportedError(PROVIDER_ID, "code.stream")
        if timeout <= 0:
            raise ValueError("Interpreter timeout must be positive.")
        payload: dict[str, Any] = {"code": code, "language": language}
        if envs:
            payload["env_vars"] = envs
        response = await asyncio.wait_for(
            self._http.envd_http_request(
                self._gateway.url(sandbox_id, _CODE_PORT),
                "POST",
                "/execute",
                envd_token=envd_token,
                headers={"Content-Type": "application/json", "E2b-Sandbox-Port": str(_CODE_PORT)},
                content=json.dumps(payload).encode(),
                request_timeout=timeout,
            ),
            timeout=timeout,
        )
        return _result(response.text)
