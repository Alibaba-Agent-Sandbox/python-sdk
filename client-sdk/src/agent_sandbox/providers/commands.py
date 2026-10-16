"""Provider management commands over the shared Node engine.

These operations manage provider resources, not commands registered inside a sandbox.
The engine owns schemas, dispatch, cloud APIs and mutation confirmation. POST calls
are never replayed by this adapter, including after connection failure or HTTP 401.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from agent_sandbox.models.errors import ProviderConfigError, ProviderProtocolError
from agent_sandbox.providers.engine_client import EngineClient
from agent_sandbox.providers.manifest import COMMAND_ID_RE
from agent_sandbox.providers.registry import get_provider
from agent_sandbox.transport.config import load_config
from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID, validate_provider_id

__all__ = ["get_command", "list_commands", "run_command"]


def _validate_provider(provider: str) -> None:
    if not isinstance(provider, str) or (
        provider != BUILTIN_PROVIDER_ID and validate_provider_id(provider) is not None
    ):
        raise ProviderConfigError("A valid explicit provider id is required.")


def _client(
    provider: str, provider_options: dict[str, Any] | None, config: dict[str, Any]
) -> EngineClient:
    _validate_provider(provider)
    resolved = load_config(provider=provider, provider_options=provider_options, **config)
    if resolved.provider != provider:
        raise ProviderConfigError(
            "The command provider must match the resolved connection provider."
        )
    schema = get_provider(provider)
    options: dict[str, Any] = {}
    for field in schema.config_fields:
        value = resolved.provider_options.get(field.key, getattr(resolved, field.key, None))
        if value is not None and value != "":
            options[field.key] = value
    connection: dict[str, Any] = {"provider": provider, "provider_options": options}
    for name, wire in (
        ("sandbox_api_key", "api_key"),
        ("sandbox_base_url", "api_url"),
        ("sandbox_domain", "domain"),
    ):
        if name in schema.inherit and (value := getattr(resolved, name, None)):
            connection[wire] = value
    if provider == BUILTIN_PROVIDER_ID:
        connection["region"] = resolved.region
        for name in ("access_key_id", "access_key_secret"):
            if value := getattr(resolved, name, None):
                connection[name] = value
    return EngineClient(connection)


def _path(provider: str, command_id: str | None = None) -> str:
    _validate_provider(provider)
    path = f"/v1/providers/{quote(provider, safe='')}/commands"
    if command_id is not None:
        if (
            not isinstance(command_id, str)
            or len(command_id) > 80
            or not COMMAND_ID_RE.fullmatch(command_id)
        ):
            raise ProviderConfigError("A valid command id of at most 80 characters is required.")
        path += f"/{quote(command_id, safe='')}"
    return path


async def list_commands(provider: str) -> list[dict[str, Any]]:
    """List static command descriptors without resolving or sending credentials.

    Args:
        provider: Explicit provider id.

    Returns:
        Command descriptors with schemas and mutation metadata.
    """
    path = _path(provider)
    client = EngineClient({"provider": provider})
    try:
        result = await client.call("GET", path)
        entries = result.get("commands") if isinstance(result, dict) else None
        if not isinstance(entries, list) or not all(isinstance(c, dict) for c in entries):
            raise ProviderProtocolError("The engine returned an invalid provider command list.")
        return entries
    finally:
        await client.close()


async def get_command(provider: str, command_id: str) -> dict[str, Any]:
    """Return a static descriptor without resolving or sending credentials."""
    path = _path(provider, command_id)
    client = EngineClient({"provider": provider})
    try:
        result = await client.call("GET", path)
        if not isinstance(result, dict) or result.get("id") != command_id:
            raise ProviderProtocolError(
                "The engine returned an invalid provider command descriptor."
            )
        return result
    finally:
        await client.close()


async def run_command(
    provider: str,
    command_id: str,
    input: dict[str, Any] | None = None,
    *,
    confirm: bool = False,
    provider_options: dict[str, Any] | None = None,
    **config: Any,
) -> Any:
    """Invoke a provider command once, without replaying its POST request.

    Args:
        provider: Explicit provider id.
        command_id: A command declared by the provider, for example ``volumes.list``.
        input: JSON object validated by the engine against the command schema.
        confirm: Explicit mutation confirmation. Writes and deletes require ``True``.
        provider_options: Provider-scoped configuration overrides.
        **config: Canonical configuration overrides accepted by ``load_config``.

    Returns:
        The command's JSON result, validated by the engine.

    Raises:
        ProviderConfigError: Invalid ids, non-object input or non-boolean confirmation.
    """
    path = _path(provider, command_id)
    if input is not None and not isinstance(input, dict):
        raise ProviderConfigError("Provider command input must be a JSON object.")
    if not isinstance(confirm, bool):
        raise ProviderConfigError("Provider command confirmation must be a boolean.")
    client = _client(provider, provider_options, config)
    try:
        return await client.call(
            "POST",
            path,
            json_body={"input": input if input is not None else {}, "confirm": confirm},
            retry=False,
        )
    finally:
        await client.close()
