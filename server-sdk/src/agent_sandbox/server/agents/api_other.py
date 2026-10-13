"""Models listing (O-01, O-02), local webhook endpoints (O-06..O-14) and the CANNOT routes.

``GET /v1/models`` lists stored definitions and the mounted adapters, labeled local. Webhook
endpoints are local records whose signing secret is returned once. The CANNOT operations
(``POST /responses/input_tokens``, ``DELETE /models/{id}``, executor registration and channel)
answer 404 ``not_found_error`` with ``x-should-retry: false``: never 501, never an empty 200.
"""

from __future__ import annotations

import shutil
import time
from typing import Any

from ..types import ServerRequest, ServerResponse
from .api_common import (
    DEFAULT_AGENT_ORDER,
    body_of,
    cannot,
    err,
    get_agent_runtime,
    label,
    page,
    principal_of,
)
from .errors import LocalApiError
from .local_state import Record, get_state
from .procenv import base_child_env
from .webhooks import (
    SUPPORTED_EVENTS,
    WebhookDeliveryError,
    build_event,
    check_endpoint_url,
    deliver,
    new_secret,
)

__all__ = [
    "handle_cannot_executor_channel",
    "handle_cannot_executor_registration",
    "handle_cannot_input_tokens",
    "handle_cannot_model_delete",
    "handle_event_types",
    "handle_models_get",
    "handle_models_list",
    "handle_webhooks_create",
    "handle_webhooks_delete",
    "handle_webhooks_get",
    "handle_webhooks_list",
    "handle_webhooks_rotate",
    "handle_webhooks_test",
    "handle_webhooks_update",
]

_STARTED = int(time.time())


# ---------------------------------------------------------------------- #
# Models
# ---------------------------------------------------------------------- #


def _installed(name: str) -> bool:
    runtime = get_agent_runtime()
    adapter = runtime.adapters.get(name)
    if adapter is None or not adapter.binary:
        return False
    path = base_child_env(runtime._environ).get("PATH")
    return shutil.which(adapter.binary, path=path) is not None


def _models(owner: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    installed = {name: _installed(name) for name in DEFAULT_AGENT_ORDER}
    for record in get_state().definitions.list(owner):
        out.append(
            {
                "id": record.id,
                "object": "model",
                "created": record.created_at,
                "owned_by": "agent-sandbox-local",
                "x_agent_sandbox": label(
                    compute="none",
                    kind="agent_definition",
                    installed=installed.get(record.data["adapter"], False),
                ),
            }
        )
    for name in DEFAULT_AGENT_ORDER:
        out.append(
            {
                "id": name,
                "object": "model",
                "created": _STARTED,
                "owned_by": "agent-sandbox-local",
                "x_agent_sandbox": label(compute="none", kind="adapter", installed=installed[name]),
            }
        )
    return out


def handle_models_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/models`` (O-01): definitions of the caller and the mounted adapters."""
    data = _models(principal_of(request))
    return ServerResponse.ok({"object": "list", "data": data})


def handle_models_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/models/{model}`` (O-02): only a listed id; no side effect."""
    model = request.path_params["model"]
    for entry in _models(principal_of(request)):
        if entry["id"] == model:
            return ServerResponse.ok(entry)
    return err(
        404,
        f"the model {model!r} does not exist",
        code="model_not_found",
        param="model",
        type_="not_found_error",
    )


# ---------------------------------------------------------------------- #
# Webhook endpoints
# ---------------------------------------------------------------------- #


def _endpoint_label() -> dict[str, Any]:
    return label("local_signer", "memory_only", compute="local_state")


def _endpoint_object(record: Record, *, secret: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": record.id,
        "object": "webhook_endpoint",
        "created_at": record.created_at,
        "event_types": list(record.data["event_types"]),
        "name": record.data["name"],
        "signing_secret_hint": None,
        "url": record.data["url"],
        "updated_at": record.updated_at,
        "x_agent_sandbox": _endpoint_label(),
    }
    if secret is not None:
        out["signing_secret"] = secret
    return out


def _event_types(raw: Any) -> list[str]:
    if not isinstance(raw, list) or not raw or not all(isinstance(e, str) for e in raw):
        raise LocalApiError("event_types: a non-empty list of strings", param="event_types")
    unknown = [e for e in raw if e not in SUPPORTED_EVENTS]
    if unknown:
        raise LocalApiError(
            f"event_types: this server does not send {unknown[0]!r}; see /v1/webhook_event_types",
            param="event_types",
        )
    return list(dict.fromkeys(raw))


def _name(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str) or len(raw) > 256:
        raise LocalApiError("name: expected a string up to 256 characters", param="name")
    return raw


def _endpoint_missing(endpoint_id: str) -> ServerResponse:
    return err(
        404,
        f"webhook endpoint {endpoint_id!r} not found",
        code="resource_not_found",
        param="webhook_endpoint_id",
    )


def _endpoint(request: ServerRequest) -> Record | ServerResponse:
    endpoint_id = request.path_params["webhook_endpoint_id"]
    record = get_state().webhooks.get(principal_of(request), endpoint_id)
    return record if record is not None else _endpoint_missing(endpoint_id)


def handle_webhooks_create(request: ServerRequest) -> ServerResponse:
    """``POST /v1/webhook_endpoints`` (O-07): the signing secret is returned once."""
    body = body_of(request)
    for key in body:
        if key not in ("url", "event_types", "name"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    check_endpoint_url(body.get("url"))
    secret = new_secret()
    record = get_state().webhooks.create(
        principal_of(request),
        {
            "url": body["url"],
            "event_types": _event_types(body.get("event_types")),
            "name": _name(body.get("name")),
        },
        {"secret": secret},
    )
    return ServerResponse.ok(_endpoint_object(record, secret=secret))


def handle_webhooks_get(request: ServerRequest) -> ServerResponse:
    """``GET /v1/webhook_endpoints/{webhook_endpoint_id}`` (O-08): no secret."""
    record = _endpoint(request)
    if isinstance(record, ServerResponse):
        return record
    return ServerResponse.ok(_endpoint_object(record))


def handle_webhooks_update(request: ServerRequest) -> ServerResponse:
    """``POST /v1/webhook_endpoints/{webhook_endpoint_id}`` (O-09)."""
    record = _endpoint(request)
    if isinstance(record, ServerResponse):
        return record
    body = body_of(request)
    for key in body:
        if key not in ("url", "event_types", "name"):
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    if "url" in body:
        check_endpoint_url(body["url"])
        record.data["url"] = body["url"]
    if "event_types" in body:
        record.data["event_types"] = _event_types(body["event_types"])
    if "name" in body:
        record.data["name"] = _name(body["name"])
    get_state().webhooks.touch(record)
    return ServerResponse.ok(_endpoint_object(record))


def handle_webhooks_list(request: ServerRequest) -> ServerResponse:
    """``GET /v1/webhook_endpoints`` (O-10)."""
    rows = get_state().webhooks.list(principal_of(request))
    return page([_endpoint_object(r) for r in rows], request.query)


def handle_webhooks_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/webhook_endpoints/{webhook_endpoint_id}`` (O-11)."""
    record = _endpoint(request)
    if isinstance(record, ServerResponse):
        return record
    get_state().webhooks.delete(principal_of(request), record.id)
    return ServerResponse.ok(
        {
            "id": record.id,
            "object": "webhook_endpoint.deleted",
            "deleted": True,
            "x_agent_sandbox": _endpoint_label(),
        }
    )


def handle_webhooks_rotate(request: ServerRequest) -> ServerResponse:
    """``POST /v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret`` (O-12)."""
    record = _endpoint(request)
    if isinstance(record, ServerResponse):
        return record
    body = body_of(request)
    for key in body:
        if key != "keep_old_secret_active_for_24_hours":
            raise LocalApiError(f"{key}: unknown or unsupported parameter", param=key)
    if body.get("keep_old_secret_active_for_24_hours"):
        raise LocalApiError(
            "keep_old_secret_active_for_24_hours: events are signed with one secret locally",
            param="keep_old_secret_active_for_24_hours",
        )
    secret = new_secret()
    record.private["secret"] = secret
    get_state().webhooks.touch(record)
    return ServerResponse.ok(_endpoint_object(record, secret=secret))


def handle_webhooks_test(request: ServerRequest) -> ServerResponse:
    """``POST /v1/webhook_endpoints/{webhook_endpoint_id}/test`` (O-13)."""
    record = _endpoint(request)
    if isinstance(record, ServerResponse):
        return record
    body = body_of(request)
    event_type = body.get("event_type")
    if event_type not in SUPPORTED_EVENTS:
        raise LocalApiError("event_type: not an event type this server sends", param="event_type")
    event = build_event(
        event_type,
        {"id": "agsess_test", "environment_type": "self_hosted", "environment_id": None},
    )
    try:
        status = deliver(record.data["url"], record.private["secret"], event)
    except WebhookDeliveryError as exc:
        raise LocalApiError(str(exc), param="url", code="agents.webhook_delivery_failed") from None
    return ServerResponse.ok(
        {
            "object": "webhook_endpoint.test",
            "event_type": event_type,
            "status_code": status,
            "success": True,
            "webhook_endpoint_id": record.id,
            "x_agent_sandbox": _endpoint_label(),
        }
    )


def handle_event_types(request: ServerRequest) -> ServerResponse:
    """``GET /v1/webhook_event_types`` (O-14): the types O-06 actually sends."""
    return ServerResponse.ok(
        {
            "object": "list",
            "data": list(SUPPORTED_EVENTS),
            "x_agent_sandbox": label("local_signer", compute="none"),
        }
    )


# ---------------------------------------------------------------------- #
# CANNOT routes
# ---------------------------------------------------------------------- #


def handle_cannot_input_tokens(request: ServerRequest) -> ServerResponse:
    """``POST /v1/responses/input_tokens`` (R-06): no tokenizer for the model the CLI calls."""
    return cannot(
        "input token counting is not available: no local tokenizer matches the model the CLI "
        "will call, and a generation would be needed to learn the real count"
    )


def handle_cannot_model_delete(request: ServerRequest) -> ServerResponse:
    """``DELETE /v1/models/{model}``: there are no fine-tuned model objects to delete."""
    return cannot(
        "models cannot be deleted: there are no fine-tuned models here; "
        "delete an agent definition with DELETE /v1/agents/{agent_id}"
    )


def handle_cannot_executor_registration(request: ServerRequest) -> ServerResponse:
    """O-04: executor registration is a client of OpenAI's hosted harness."""
    return cannot(
        "executor registration is not available: it registers with api.openai.com, which "
        "this local server cannot host"
    )


def handle_cannot_executor_channel(request: ServerRequest) -> ServerResponse:
    """O-05: the executor channel peer is OpenAI's hosted socket."""
    return cannot("the executor channel is not available: its peer is the hosted harness socket")
