"""Optional signed FC task delivery using Alibaba's maintained FC 20230330 SDK."""

from __future__ import annotations

import io
import json
from typing import Any

from .invocations import sign_invocation


class FCTaskSender:
    """Send durable outbox messages to a configured async Task function.

    The SDK's default credential chain supports function roles and local profiles.
    Function existence, IAM permissions, asyncTask settings and network ingress
    are deployment gates. This class creates no cloud resources.
    """

    def __init__(
        self,
        endpoint: str,
        function_name: str,
        internal_token: str,
        *,
        qualifier: str | None = None,
        client: Any = None,
    ) -> None:
        from alibabacloud_credentials.client import Client as CredentialClient
        from alibabacloud_fc20230330.client import Client
        from alibabacloud_tea_openapi.models import Config

        if not endpoint or "://" in endpoint or not function_name or len(internal_token) < 32:
            raise ValueError("FC endpoint, function name and private invocation token are required")
        self._client = client or Client(Config(credential=CredentialClient(), endpoint=endpoint))
        self._function, self._token, self._qualifier = function_name, internal_token, qualifier

    def __call__(self, payload: dict[str, str]) -> None:
        """Accept at-least-once task delivery; application claims prevent duplicate work."""
        from alibabacloud_fc20230330.models import InvokeFunctionHeaders, InvokeFunctionRequest
        from alibabacloud_tea_util.models import RuntimeOptions

        run_id = payload["runId"]
        response = self._client.invoke_function_with_options(
            self._function,
            InvokeFunctionRequest(
                body=io.BytesIO(
                    json.dumps(sign_invocation(payload, self._token, role="worker")).encode()
                ),
                qualifier=self._qualifier,
            ),
            InvokeFunctionHeaders(
                x_fc_invocation_type="Async",
                x_fc_async_task_id=run_id,
            ),
            RuntimeOptions(autoretry=False, connect_timeout=10000, read_timeout=15000),
        )
        if response.status_code != 202:
            raise RuntimeError("FC did not durably accept the application task")
