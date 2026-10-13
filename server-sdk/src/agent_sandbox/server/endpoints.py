"""The endpoint declaration table: the single registry of what the server can do.

Every built-in HTTP endpoint is declared exactly once, here: its stable ID (the *name* used by
policies, audit lines, ``GET /capabilities`` and the client), its HTTP binding (method and path),
its capability group, its default scopes and the knobs a policy may tune.  Route modules only
attach handlers to these IDs (:meth:`RouteTable.mount`); the route table, the policy catalogue and
the discovery document are all derived from this table, so they cannot drift apart.

A *group* is nothing but a named alias for the set of endpoints that declare it: policies,
``groups:`` and ``ABX_SERVER_ENABLED_GROUPS`` expand it to endpoint IDs, and there is no separate
group gate in front of the endpoint rules.

Stdlib only.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "CORE_ENDPOINTS",
    "ENDPOINTS",
    "OPT_IN_GROUPS",
    "TRANSFER_ENDPOINTS",
    "CapabilityGroup",
    "Endpoint",
    "EndpointSpec",
    "endpoints_of",
]


class CapabilityGroup(Enum):
    """A named alias for a family of endpoints.

    ``CORE`` is always on.  Every other group expands to the endpoint IDs that declare it in
    :data:`ENDPOINTS`; see :func:`endpoints_of`.
    """

    CORE = "core"
    COMMANDS = "commands"
    FILE_OPS = "file_ops"
    PROCESS = "process"
    TERMINAL = "terminal"
    SYSTEM = "system"
    DEV_TOOLS = "dev_tools"
    BROWSER = "browser"
    AGENTS = "agents"


G = CapabilityGroup

#: Groups whose endpoints start disabled; a policy, ``groups:`` or the environment turns them on.
OPT_IN_GROUPS = frozenset({G.DEV_TOOLS, G.BROWSER, G.AGENTS})


@dataclasses.dataclass(frozen=True)
class EndpointSpec:
    """What a policy may tune on one endpoint (default scopes and knobs)."""

    scopes: tuple[str, ...] = ()
    limits: frozenset[str] = frozenset()
    params: frozenset[str] = frozenset()
    paths: bool = False
    #: ``True`` when the endpoint can execute arbitrary programs / code.
    exec: bool = False


@dataclasses.dataclass(frozen=True)
class Endpoint:
    """One declared endpoint: identity, HTTP binding, group and policy defaults."""

    name: str
    method: str
    path: str
    group: CapabilityGroup
    spec: EndpointSpec
    summary: str = ""
    streaming: bool = False
    auth_required: bool = True
    #: ``True`` for endpoints served by another transport (the PTY WebSocket): governed by the
    #: policy but with no HTTP route to mount.
    virtual: bool = False


COMMON_LIMITS = frozenset({"max_request_bytes", "rate_per_minute", "max_concurrency"})

_UPLOAD_PARAMS = ("overwrite", "allow_extensions", "deny_extensions")
_EXEC_PARAMS = ("allow_commands", "deny_commands")
_EXEC_LIMITS = ("timeout_seconds", "max_output_bytes", "max_processes")


def _ep(
    name: str,
    method: str,
    path: str,
    group: CapabilityGroup,
    *,
    summary: str = "",
    scopes: tuple[str, ...] = (),
    limits: Iterable[str] = (),
    params: Iterable[str] = (),
    paths: bool = False,
    exec: bool = False,  # noqa: A002
    streaming: bool = False,
    auth_required: bool = True,
    virtual: bool = False,
) -> Endpoint:
    spec = EndpointSpec(
        scopes=scopes,
        limits=COMMON_LIMITS | frozenset(limits),
        params=frozenset(params),
        paths=paths,
        exec=exec,
    )
    return Endpoint(name, method, path, group, spec, summary, streaming, auth_required, virtual)


def _agent(name: str, method: str, path: str, summary: str, *, streaming: bool = False) -> Endpoint:
    return _ep(
        name,
        method,
        path,
        G.AGENTS,
        summary=summary,
        scopes=("agents:use",),
        streaming=streaming,
    )


_BUILTIN: tuple[Endpoint, ...] = (
    # CORE
    _ep(
        "health",
        "GET",
        "/health",
        G.CORE,
        summary="Liveness probe (anonymous).",
        auth_required=False,
    ),
    _ep(
        "capabilities",
        "GET",
        "/capabilities",
        G.CORE,
        summary="Capability groups and the per-endpoint discovery document.",
        scopes=("core:read",),
    ),
    _ep(
        "capabilities_check",
        "POST",
        "/capabilities/check",
        G.CORE,
        summary="Authoritative policy decision for a hypothetical call.",
        scopes=("core:read",),
    ),
    # COMMANDS
    _ep(
        "list_commands",
        "GET",
        "/commands",
        G.COMMANDS,
        summary="List the registered custom commands.",
        scopes=("commands:list",),
    ),
    _ep(
        "run_command",
        "POST",
        "/commands/{name}",
        G.COMMANDS,
        summary="Run a registered named command.",
        scopes=("commands:run",),
    ),
    # FILE_OPS
    _ep(
        "upload",
        "POST",
        "/upload",
        G.FILE_OPS,
        summary="Write base64 content to a file.",
        scopes=("files:write",),
        limits=("max_bytes",),
        params=_UPLOAD_PARAMS,
        paths=True,
    ),
    _ep(
        "download",
        "GET",
        "/download",
        G.FILE_OPS,
        summary="Read a file as base64.",
        scopes=("files:read",),
        limits=("max_bytes",),
        paths=True,
    ),
    _ep(
        "files_list",
        "GET",
        "/files/list",
        G.FILE_OPS,
        summary="List a directory.",
        scopes=("files:read",),
        limits=("max_depth", "max_entries"),
        paths=True,
    ),
    _ep(
        "files_stat",
        "GET",
        "/files/stat",
        G.FILE_OPS,
        summary="Stat a path.",
        scopes=("files:read",),
        paths=True,
    ),
    _ep(
        "files_mkdir",
        "POST",
        "/files/mkdir",
        G.FILE_OPS,
        summary="Create a directory.",
        scopes=("files:write",),
        paths=True,
    ),
    _ep(
        "files_delete",
        "DELETE",
        "/files",
        G.FILE_OPS,
        summary="Delete a file or directory.",
        scopes=("files:delete",),
        paths=True,
    ),
    _ep(
        "files_move",
        "POST",
        "/files/move",
        G.FILE_OPS,
        summary="Move or rename a path.",
        scopes=("files:write", "files:delete"),
        paths=True,
    ),
    _ep(
        "files_search",
        "POST",
        "/files/search",
        G.FILE_OPS,
        summary="Search file names or contents.",
        scopes=("files:read",),
        limits=("max_depth", "max_results", "timeout_seconds"),
        paths=True,
    ),
    _ep(
        "files_upload_stream",
        "POST",
        "/files/upload-stream",
        G.FILE_OPS,
        summary="Chunk-decoding upload.",
        scopes=("files:write",),
        limits=("max_bytes",),
        params=_UPLOAD_PARAMS,
        paths=True,
    ),
    _ep(
        "files_download_stream",
        "GET",
        "/files/download-stream",
        G.FILE_OPS,
        summary="Chunked download.",
        scopes=("files:read",),
        limits=("max_bytes",),
        paths=True,
    ),
    _ep(
        "files_archive",
        "POST",
        "/files/archive",
        G.FILE_OPS,
        summary="Create a tar.gz or zip archive.",
        scopes=("files:read",),
        limits=("max_bytes", "max_files"),
        paths=True,
    ),
    _ep(
        "files_watch",
        "GET",
        "/files/watch",
        G.FILE_OPS,
        summary="Stream file-system events (SSE).",
        scopes=("files:read",),
        limits=("max_duration_seconds",),
        paths=True,
        streaming=True,
    ),
    # PROCESS
    _ep(
        "shell",
        "POST",
        "/shell",
        G.PROCESS,
        summary="Run a command and return its output.",
        scopes=("process:run",),
        limits=_EXEC_LIMITS,
        params=_EXEC_PARAMS,
        paths=True,
        exec=True,
    ),
    _ep(
        "shell_stream",
        "POST",
        "/shell/stream",
        G.PROCESS,
        summary="Run a command and stream its output (SSE).",
        scopes=("process:run",),
        limits=_EXEC_LIMITS,
        params=_EXEC_PARAMS,
        paths=True,
        exec=True,
        streaming=True,
    ),
    _ep(
        "process_start",
        "POST",
        "/process/start",
        G.PROCESS,
        summary="Start a background process.",
        scopes=("process:run",),
        limits=_EXEC_LIMITS,
        params=_EXEC_PARAMS,
        paths=True,
        exec=True,
    ),
    _ep(
        "process_list",
        "GET",
        "/process/list",
        G.PROCESS,
        summary="List server-started processes.",
        scopes=("process:read",),
    ),
    _ep(
        "process_detail",
        "GET",
        "/process/{pid}",
        G.PROCESS,
        summary="Status of one process.",
        scopes=("process:read",),
    ),
    _ep(
        "process_signal",
        "POST",
        "/process/{pid}/signal",
        G.PROCESS,
        summary="Send a signal to a process.",
        scopes=("process:manage",),
        params=("allowed_signals",),
    ),
    _ep(
        "process_stdin",
        "POST",
        "/process/{pid}/stdin",
        G.PROCESS,
        summary="Write to a process stdin.",
        scopes=("process:manage",),
    ),
    _ep(
        "process_output",
        "GET",
        "/process/{pid}/output",
        G.PROCESS,
        summary="Read process output.",
        scopes=("process:read",),
    ),
    # TERMINAL
    _ep(
        "pty_create_session",
        "POST",
        "/pty/sessions",
        G.TERMINAL,
        summary="Create a PTY session.",
        scopes=("terminal:use",),
        limits=("max_sessions",),
        params=("env_deny", "shells"),
    ),
    _ep(
        "pty_list_sessions",
        "GET",
        "/pty/sessions",
        G.TERMINAL,
        summary="List PTY sessions.",
        scopes=("terminal:use",),
    ),
    _ep(
        "pty_detail",
        "GET",
        "/pty/sessions/{id}",
        G.TERMINAL,
        summary="Details of one PTY session.",
        scopes=("terminal:use",),
    ),
    _ep(
        "pty_resize",
        "POST",
        "/pty/sessions/{id}/resize",
        G.TERMINAL,
        summary="Resize a PTY session.",
        scopes=("terminal:use",),
    ),
    _ep(
        "pty_delete_session",
        "DELETE",
        "/pty/sessions/{id}",
        G.TERMINAL,
        summary="Close a PTY session.",
        scopes=("terminal:use",),
    ),
    # SYSTEM
    _ep(
        "system_info",
        "GET",
        "/system/info",
        G.SYSTEM,
        summary="OS, CPU, memory and disk information.",
        scopes=("system:read",),
    ),
    _ep(
        "env_get",
        "GET",
        "/env",
        G.SYSTEM,
        summary="Read environment variables.",
        scopes=("system:read",),
        params=("allow_vars", "deny_vars"),
    ),
    _ep(
        "env_set",
        "POST",
        "/env",
        G.SYSTEM,
        summary="Set environment variables.",
        scopes=("system:write",),
        params=("allow_vars", "deny_vars"),
    ),
    _ep("ports", "GET", "/ports", G.SYSTEM, summary="Listening ports.", scopes=("system:read",)),
    _ep(
        "packages",
        "GET",
        "/packages",
        G.SYSTEM,
        summary="Installed packages.",
        scopes=("system:read",),
    ),
    _ep(
        "system_metrics",
        "GET",
        "/system/metrics",
        G.SYSTEM,
        summary="Live system metrics.",
        scopes=("system:read",),
    ),
    # DEV_TOOLS
    _ep(
        "code_run",
        "POST",
        "/code/run",
        G.DEV_TOOLS,
        summary="Run a code snippet.",
        scopes=("devtools:run",),
        limits=("max_output_bytes", "timeout_seconds"),
        params=("languages",),
        exec=True,
    ),
    _ep(
        "git_status",
        "GET",
        "/git/status",
        G.DEV_TOOLS,
        summary="git status of a repository.",
        scopes=("devtools:read",),
        paths=True,
    ),
    _ep(
        "git_diff",
        "GET",
        "/git/diff",
        G.DEV_TOOLS,
        summary="git diff of a repository.",
        scopes=("devtools:read",),
        paths=True,
    ),
    # BROWSER
    _ep(
        "browser_navigate",
        "POST",
        "/browser/navigate",
        G.BROWSER,
        summary="Navigate the headless browser.",
        scopes=("browser:use",),
        params=("block_private_networks", "url_allow", "url_deny"),
        exec=True,
    ),
    _ep(
        "browser_screenshot",
        "POST",
        "/browser/screenshot",
        G.BROWSER,
        summary="Screenshot the current page.",
        scopes=("browser:use",),
    ),
    _ep(
        "browser_content",
        "GET",
        "/browser/content",
        G.BROWSER,
        summary="Page HTML or text.",
        scopes=("browser:use",),
    ),
    _ep(
        "browser_click",
        "POST",
        "/browser/click",
        G.BROWSER,
        summary="Click an element.",
        scopes=("browser:use",),
    ),
    _ep(
        "browser_type",
        "POST",
        "/browser/type",
        G.BROWSER,
        summary="Type into an element.",
        scopes=("browser:use",),
    ),
    _ep(
        "browser_evaluate",
        "POST",
        "/browser/evaluate",
        G.BROWSER,
        summary="Evaluate JavaScript in the page.",
        scopes=("browser:evaluate",),
        exec=True,
    ),
    _ep(
        "browser_pdf",
        "POST",
        "/browser/pdf",
        G.BROWSER,
        summary="Render the page to PDF.",
        scopes=("browser:use",),
    ),
    _ep(
        "browser_console",
        "GET",
        "/browser/console",
        G.BROWSER,
        summary="Console messages of the page.",
        scopes=("browser:use",),
    ),
    _ep(
        "pty_connect",
        "WS",
        "/pty",
        G.TERMINAL,
        summary="Attach to a PTY session over WebSocket (served on the PTY port).",
        scopes=("terminal:use",),
        streaming=True,
        virtual=True,
    ),
)

# Agents API (opt-in group). Every route is a real local operation; see GET /v1/agents/runtimes.
_AGENTS: tuple[Endpoint, ...] = (
    _agent("agents_sessions_create", "POST", "/v1/agents/sessions", "Create an agent session."),
    _agent("agents_sessions_list", "GET", "/v1/agents/sessions", "List agent sessions."),
    _agent("agents_sessions_get", "GET", "/v1/agents/sessions/{id}", "Get an agent session."),
    _agent(
        "agents_sessions_update", "POST", "/v1/agents/sessions/{id}", "Update session metadata."
    ),
    _agent(
        "agents_sessions_delete", "DELETE", "/v1/agents/sessions/{id}", "Delete an agent session."
    ),
    _agent(
        "agents_sessions_events_create",
        "POST",
        "/v1/agents/sessions/{id}/events",
        "Send an input event to a session.",
    ),
    _agent(
        "agents_sessions_events_stream",
        "GET",
        "/v1/agents/sessions/{id}/events",
        "Stream session events (SSE).",
        streaming=True,
    ),
    _agent(
        "agents_sessions_items_list", "GET", "/v1/agents/sessions/{id}/items", "List session items."
    ),
    _agent(
        "agents_sessions_turns_list", "GET", "/v1/agents/sessions/{id}/turns", "List session turns."
    ),
    _agent(
        "agents_sessions_turns_get",
        "GET",
        "/v1/agents/sessions/{id}/turns/{turn_id}",
        "Get one turn.",
    ),
    _agent(
        "agents_sessions_turns_items_list",
        "GET",
        "/v1/agents/sessions/{id}/turns/{turn_id}/items",
        "List the items of a turn.",
    ),
    _agent(
        "agents_artifacts_list",
        "GET",
        "/v1/agents/sessions/{id}/artifacts",
        "List session artifacts.",
    ),
    _agent(
        "agents_artifacts_get",
        "GET",
        "/v1/agents/sessions/{id}/artifacts/{artifact_id}",
        "Get artifact metadata.",
    ),
    _agent(
        "agents_artifacts_delete",
        "DELETE",
        "/v1/agents/sessions/{id}/artifacts/{artifact_id}",
        "Delete an artifact snapshot.",
    ),
    _agent(
        "agents_artifacts_content",
        "GET",
        "/v1/agents/sessions/{id}/artifacts/{artifact_id}/content",
        "Download the bytes of an artifact snapshot.",
        streaming=True,
    ),
    _agent("agents_traces_list", "GET", "/v1/agents/sessions/{id}/traces", "List session traces."),
    _agent(
        "agents_subagents_list",
        "GET",
        "/v1/agents/sessions/{id}/subagents",
        "List session subagents.",
    ),
    _agent(
        "agents_subagents_get",
        "GET",
        "/v1/agents/sessions/{id}/subagents/{subagent_id}",
        "Get one subagent.",
    ),
    _agent(
        "agents_subagents_items_list",
        "GET",
        "/v1/agents/sessions/{id}/subagents/{subagent_id}/items",
        "List the items of a subagent.",
    ),
    _agent(
        "agents_subagents_turns_list",
        "GET",
        "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns",
        "List the turns of a subagent.",
    ),
    _agent(
        "agents_subagents_turns_get",
        "GET",
        "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}",
        "Get one turn of a subagent.",
    ),
    _agent(
        "agents_subagents_turns_items_list",
        "GET",
        "/v1/agents/sessions/{id}/subagents/{subagent_id}/turns/{turn_id}/items",
        "List the items of a subagent turn.",
    ),
    _agent(
        "agents_runtimes_list", "GET", "/v1/agents/runtimes", "List the available agent runtimes."
    ),
    _agent(
        "agents_environments_create",
        "POST",
        "/v1/agents/environments",
        "Bind a local directory as an environment.",
    ),
    _agent("agents_environments_list", "GET", "/v1/agents/environments", "List environments."),
    _agent(
        "agents_environment_templates_create",
        "POST",
        "/v1/agents/environments/templates",
        "Store a reduced environment template.",
    ),
    _agent(
        "agents_environment_templates_list",
        "GET",
        "/v1/agents/environments/templates",
        "List environment templates.",
    ),
    _agent(
        "agents_environment_templates_get",
        "GET",
        "/v1/agents/environments/templates/{environment_template_id}",
        "Get an environment template.",
    ),
    _agent(
        "agents_environment_templates_update",
        "POST",
        "/v1/agents/environments/templates/{environment_template_id}",
        "Update an environment template.",
    ),
    _agent(
        "agents_environment_templates_delete",
        "DELETE",
        "/v1/agents/environments/templates/{environment_template_id}",
        "Delete an environment template.",
    ),
    _agent(
        "agents_environments_get",
        "GET",
        "/v1/agents/environments/{environment_id}",
        "Get an environment.",
    ),
    _agent(
        "agents_environment_files_create",
        "POST",
        "/v1/agents/environments/{environment_id}/files",
        "Stage a file in an environment workspace.",
    ),
    _agent(
        "agents_environment_files_list",
        "GET",
        "/v1/agents/environments/{environment_id}/files",
        "List files of an environment workspace.",
    ),
    _agent(
        "agents_cannot_executor_registration",
        "POST",
        "/v1/agents/environments/{environment_id}/register",
        "Refused: executor registration.",
    ),
    _agent(
        "agents_cannot_executor_channel",
        "GET",
        "/v1/agents/environments/{environment_id}/connect",
        "Refused: executor channel.",
    ),
    _agent("agents_definitions_create", "POST", "/v1/agents", "Store an agent definition."),
    _agent("agents_definitions_list", "GET", "/v1/agents", "List agent definitions."),
    _agent("agents_definitions_get", "GET", "/v1/agents/{agent_id}", "Get an agent definition."),
    _agent(
        "agents_definitions_update", "POST", "/v1/agents/{agent_id}", "Update an agent definition."
    ),
    _agent(
        "agents_definitions_delete",
        "DELETE",
        "/v1/agents/{agent_id}",
        "Delete an agent definition.",
    ),
    _agent("agents_vaults_create", "POST", "/v1/vaults", "Create a memory-only vault."),
    _agent("agents_vaults_list", "GET", "/v1/vaults", "List vaults."),
    _agent("agents_vaults_get", "GET", "/v1/vaults/{vault_id}", "Get a vault."),
    _agent("agents_vaults_update", "POST", "/v1/vaults/{vault_id}", "Update a vault."),
    _agent(
        "agents_vaults_delete",
        "DELETE",
        "/v1/vaults/{vault_id}",
        "Delete a vault and its credentials.",
    ),
    _agent(
        "agents_vault_credentials_create",
        "POST",
        "/v1/vaults/{vault_id}/credentials",
        "Store a write-only credential.",
    ),
    _agent(
        "agents_vault_credentials_list",
        "GET",
        "/v1/vaults/{vault_id}/credentials",
        "List credential metadata.",
    ),
    _agent(
        "agents_vault_credentials_get",
        "GET",
        "/v1/vaults/{vault_id}/credentials/{credential_id}",
        "Get credential metadata.",
    ),
    _agent(
        "agents_vault_credentials_update",
        "POST",
        "/v1/vaults/{vault_id}/credentials/{credential_id}",
        "Update or rotate a credential.",
    ),
    _agent(
        "agents_vault_credentials_delete",
        "DELETE",
        "/v1/vaults/{vault_id}/credentials/{credential_id}",
        "Delete a credential.",
    ),
    _agent(
        "agents_responses_create",
        "POST",
        "/v1/responses",
        "Run one local CLI turn as a response.",
        streaming=True,
    ),
    _agent(
        "agents_responses_connect",
        "GET",
        "/v1/responses",
        "Responses WebSocket (response.create, queued response.steer).",
    ),
    _agent(
        "agents_cannot_responses_input_tokens",
        "POST",
        "/v1/responses/input_tokens",
        "Refused: input token counting.",
    ),
    _agent(
        "agents_responses_compact",
        "POST",
        "/v1/responses/compact",
        "Summarize a conversation with the CLI.",
    ),
    _agent(
        "agents_responses_get",
        "GET",
        "/v1/responses/{response_id}",
        "Get or replay a stored response.",
        streaming=True,
    ),
    _agent(
        "agents_responses_delete",
        "DELETE",
        "/v1/responses/{response_id}",
        "Delete a stored response.",
    ),
    _agent(
        "agents_responses_cancel",
        "POST",
        "/v1/responses/{response_id}/cancel",
        "Cancel the running turn of a response.",
    ),
    _agent(
        "agents_responses_input_items",
        "GET",
        "/v1/responses/{response_id}/input_items",
        "List the input items of a response.",
    ),
    _agent("agents_models_list", "GET", "/v1/models", "List definitions and adapters as models."),
    _agent("agents_models_get", "GET", "/v1/models/{model}", "Get one model object."),
    _agent(
        "agents_cannot_models_delete", "DELETE", "/v1/models/{model}", "Refused: model deletion."
    ),
    _agent("agents_files_create", "POST", "/v1/files", "Store a local user_data blob."),
    _agent(
        "agents_webhooks_create",
        "POST",
        "/v1/webhook_endpoints",
        "Register a local webhook endpoint.",
    ),
    _agent("agents_webhooks_list", "GET", "/v1/webhook_endpoints", "List webhook endpoints."),
    _agent(
        "agents_webhooks_get",
        "GET",
        "/v1/webhook_endpoints/{webhook_endpoint_id}",
        "Get a webhook endpoint.",
    ),
    _agent(
        "agents_webhooks_update",
        "POST",
        "/v1/webhook_endpoints/{webhook_endpoint_id}",
        "Update a webhook endpoint.",
    ),
    _agent(
        "agents_webhooks_delete",
        "DELETE",
        "/v1/webhook_endpoints/{webhook_endpoint_id}",
        "Delete a webhook endpoint.",
    ),
    _agent(
        "agents_webhooks_rotate_secret",
        "POST",
        "/v1/webhook_endpoints/{webhook_endpoint_id}/rotate_secret",
        "Rotate the signing secret of an endpoint.",
    ),
    _agent(
        "agents_webhooks_test",
        "POST",
        "/v1/webhook_endpoints/{webhook_endpoint_id}/test",
        "Send a signed test event.",
    ),
    _agent(
        "agents_webhook_event_types",
        "GET",
        "/v1/webhook_event_types",
        "List the webhook event types.",
    ),
)

#: Every declared endpoint by ID.
ENDPOINTS: dict[str, Endpoint] = {e.name: e for e in (*_BUILTIN, *_AGENTS)}

#: Endpoints that can never be disabled / locked out.
CORE_ENDPOINTS = frozenset({"health", "capabilities", "capabilities_check"})

TRANSFER_ENDPOINTS = ("upload", "download", "files_upload_stream", "files_download_stream")


def endpoints_of(group: CapabilityGroup | str) -> tuple[str, ...]:
    """The endpoint IDs a group expands to (declaration order)."""
    wanted = group if isinstance(group, CapabilityGroup) else CapabilityGroup(group)
    return tuple(e.name for e in ENDPOINTS.values() if e.group is wanted)
