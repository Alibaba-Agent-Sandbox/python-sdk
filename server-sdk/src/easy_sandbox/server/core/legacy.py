"""Every v1 route as an operation (stage S1 of the strangler migration).

``build_registry`` walks a v1 :class:`~easy_sandbox.server.router.RouteTable` and registers one
:class:`~easy_sandbox.server.core.registry.Operation` per route.  The operation does not copy any
logic: at call time the pipeline invokes the route's existing handler (``routes_*`` functions)
with a request built from the operation arguments.  IDs, effects and summaries below follow
design 04; routes this table does not know (custom ``table.route`` extensions) become
``ext.<name>`` operations that default to ``admin`` (explicit-only), and unknown ``agents_*``
routes get a mechanical ``agents.<a>.<b>`` ID.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from .ids import is_valid_id, mangle_custom_name
from .registry import HttpBinding, Operation, Param, Registry

if TYPE_CHECKING:
    from ..registry import CommandRegistry
    from ..router import RouteTable

__all__ = [
    "ALIAS_FAMILIES",
    "LEGACY_OPS",
    "VIRTUAL_ROUTES",
    "build_registry",
    "path_param_names",
]

R, W, D, X, N, A = "read", "write", "delete", "exec", "net", "admin"


@dataclasses.dataclass(frozen=True)
class _Spec:
    op_id: str
    effects: frozenset[str]
    summary: str
    agent_scope: bool = False


def _s(op_id: str, effects: str, summary: str, *, agent_scope: bool = False) -> _Spec:
    return _Spec(op_id, frozenset(effects.split("+")), summary, agent_scope)


#: v1 route name -> operation (design 04, sections 3-11).
LEGACY_OPS: dict[str, _Spec] = {
    "health": _s("core.health", R, "Liveness probe (anonymous)."),
    "capabilities": _s(
        "core.capabilities", R, "Capability groups and the per-endpoint discovery document."
    ),
    "capabilities_check": _s(
        "core.check", R, "Authoritative policy decision for a hypothetical call."
    ),
    "list_commands": _s("custom.list", R, "List the registered custom commands."),
    "upload": _s("files.upload", W, "Write base64 content to a file."),
    "download": _s("files.download", R, "Read a file as base64."),
    "files_list": _s("files.list", R, "List a directory."),
    "files_stat": _s("files.stat", R, "Stat a path."),
    "files_mkdir": _s("files.mkdir", W, "Create a directory."),
    "files_delete": _s("files.delete", D, "Delete a file or directory."),
    "files_move": _s("files.move", "read+delete+write", "Move or rename a path."),
    "files_search": _s("files.search", R, "Search file names or contents."),
    "files_upload_stream": _s("files.upload_stream", W, "Chunk-decoding upload."),
    "files_download_stream": _s("files.download_stream", R, "Chunked download."),
    "files_archive": _s("files.archive", "read+write", "Create a tar.gz or zip archive."),
    "files_watch": _s("files.watch", R, "Stream file-system events (SSE)."),
    "shell": _s("commands.run", X, "Run a command and return its output."),
    "shell_stream": _s("commands.stream", X, "Run a command and stream its output (SSE)."),
    "process_start": _s("process.start", X, "Start a background process."),
    "process_list": _s("process.list", R, "List server-started processes."),
    "process_detail": _s("process.get", R, "Status of one process."),
    "process_signal": _s("process.signal", X, "Send a signal to a process."),
    "process_stdin": _s("process.stdin", X, "Write to a process stdin."),
    "process_output": _s("process.output", R, "Read process output."),
    "pty_create_session": _s("terminal.create", X, "Create a PTY session."),
    "pty_list_sessions": _s("terminal.list", R, "List PTY sessions."),
    "pty_detail": _s("terminal.get", R, "Details of one PTY session."),
    "pty_resize": _s("terminal.resize", X, "Resize a PTY session."),
    "pty_delete_session": _s("terminal.delete", D, "Close a PTY session."),
    "system_info": _s("system.info", R, "OS, CPU, memory and disk information."),
    "system_metrics": _s("system.metrics", R, "Live system metrics."),
    "env_get": _s("system.env.get", R, "Read environment variables."),
    "env_set": _s("system.env.set", "admin+write", "Set environment variables."),
    "ports": _s("system.ports", R, "Listening ports."),
    "packages": _s("system.packages", R, "Installed packages."),
    "code_run": _s("devtools.code.run", "exec+write", "Run a code snippet."),
    "git_status": _s("devtools.git.status", "read+exec", "git status of a repository."),
    "git_diff": _s("devtools.git.diff", "read+exec", "git diff of a repository."),
    "browser_navigate": _s("browser.navigate", N, "Navigate the headless browser."),
    "browser_screenshot": _s("browser.screenshot", R, "Screenshot the current page."),
    "browser_content": _s("browser.content", R, "Page HTML or text."),
    "browser_click": _s("browser.click", X, "Click an element."),
    "browser_type": _s("browser.type", X, "Type into an element."),
    "browser_evaluate": _s("browser.evaluate", X, "Evaluate JavaScript in the page."),
    "browser_pdf": _s("browser.pdf", R, "Render the page to PDF."),
    "browser_console": _s("browser.console", R, "Console messages of the page."),
    "agents_sessions_create": _s(
        "agents.sessions.create", "exec+net", "Create an agent session.", agent_scope=True
    ),
    "agents_sessions_list": _s("agents.sessions.list", R, "List agent sessions."),
    "agents_sessions_get": _s("agents.sessions.get", R, "Get an agent session."),
    "agents_sessions_delete": _s("agents.sessions.delete", D, "Delete an agent session."),
    "agents_sessions_events_create": _s(
        "agents.sessions.send_event",
        "exec+net",
        "Send an input event to a session.",
        agent_scope=True,
    ),
    "agents_sessions_events_stream": _s(
        "agents.sessions.stream_events", R, "Stream session events (SSE)."
    ),
    "agents_sessions_items_list": _s("agents.sessions.list_items", R, "List session items."),
    "agents_sessions_turns_list": _s("agents.sessions.turns.list", R, "List session turns."),
    "agents_sessions_turns_get": _s("agents.sessions.turns.get", R, "Get one turn."),
    "agents_sessions_turns_items_list": _s(
        "agents.sessions.turns.list_items", R, "List the items of a turn."
    ),
    "agents_runtimes_list": _s("agents.runtimes.list", R, "List the available agent runtimes."),
    "agents_sessions_update": _s("agents.sessions.update", W, "Update session metadata."),
    "agents_artifacts_list": _s("agents.sessions.artifacts.list", R, "List session artifacts."),
    "agents_artifacts_get": _s("agents.sessions.artifacts.get", R, "Get artifact metadata."),
    "agents_artifacts_delete": _s(
        "agents.sessions.artifacts.delete", D, "Delete an artifact snapshot."
    ),
    "agents_artifacts_content": _s(
        "agents.sessions.artifacts.content", R, "Download the bytes of an artifact snapshot."
    ),
    "agents_traces_list": _s("agents.sessions.traces.list", R, "List session traces."),
    "agents_subagents_list": _s("agents.sessions.subagents.list", R, "List session subagents."),
    "agents_subagents_get": _s("agents.sessions.subagents.get", R, "Get one subagent."),
    "agents_subagents_items_list": _s(
        "agents.sessions.subagents.list_items", R, "List the items of a subagent."
    ),
    "agents_subagents_turns_list": _s(
        "agents.sessions.subagents.turns.list", R, "List the turns of a subagent."
    ),
    "agents_subagents_turns_get": _s(
        "agents.sessions.subagents.turns.get", R, "Get one turn of a subagent."
    ),
    "agents_subagents_turns_items_list": _s(
        "agents.sessions.subagents.turns.list_items", R, "List the items of a subagent turn."
    ),
    "agents_definitions_create": _s("agents.definitions.create", W, "Store an agent definition."),
    "agents_definitions_get": _s("agents.definitions.get", R, "Get an agent definition."),
    "agents_definitions_update": _s("agents.definitions.update", W, "Update an agent definition."),
    "agents_definitions_list": _s("agents.definitions.list", R, "List agent definitions."),
    "agents_definitions_delete": _s(
        "agents.definitions.delete", D, "Delete an agent definition."
    ),
    "agents_environments_create": _s(
        "agents.environments.create", W, "Bind a local directory as an environment."
    ),
    "agents_environments_get": _s("agents.environments.get", R, "Get an environment."),
    "agents_environments_list": _s("agents.environments.list", R, "List environments."),
    "agents_environment_files_create": _s(
        "agents.environments.files.create", W, "Stage a file in an environment workspace."
    ),
    "agents_environment_files_list": _s(
        "agents.environments.files.list", R, "List files of an environment workspace."
    ),
    "agents_environment_templates_create": _s(
        "agents.environments.templates.create", W, "Store a reduced environment template."
    ),
    "agents_environment_templates_get": _s(
        "agents.environments.templates.get", R, "Get an environment template."
    ),
    "agents_environment_templates_update": _s(
        "agents.environments.templates.update", W, "Update an environment template."
    ),
    "agents_environment_templates_list": _s(
        "agents.environments.templates.list", R, "List environment templates."
    ),
    "agents_environment_templates_delete": _s(
        "agents.environments.templates.delete", D, "Delete an environment template."
    ),
    "agents_cannot_executor_registration": _s(
        "agents.environments.register", W, "Refused: executor registration."
    ),
    "agents_cannot_executor_channel": _s(
        "agents.environments.connect", X, "Refused: executor channel."
    ),
    "agents_vaults_create": _s("agents.vaults.create", W, "Create a memory-only vault."),
    "agents_vaults_get": _s("agents.vaults.get", R, "Get a vault."),
    "agents_vaults_update": _s("agents.vaults.update", W, "Update a vault."),
    "agents_vaults_list": _s("agents.vaults.list", R, "List vaults."),
    "agents_vaults_delete": _s("agents.vaults.delete", D, "Delete a vault and its credentials."),
    "agents_vault_credentials_create": _s(
        "agents.vaults.credentials.create", W, "Store a write-only credential."
    ),
    "agents_vault_credentials_get": _s(
        "agents.vaults.credentials.get", R, "Get credential metadata."
    ),
    "agents_vault_credentials_update": _s(
        "agents.vaults.credentials.update", W, "Update or rotate a credential."
    ),
    "agents_vault_credentials_list": _s(
        "agents.vaults.credentials.list", R, "List credential metadata."
    ),
    "agents_vault_credentials_delete": _s(
        "agents.vaults.credentials.delete", D, "Delete a credential."
    ),
    "agents_responses_create": _s(
        "responses.create", "exec+net", "Run one local CLI turn as a response.", agent_scope=True
    ),
    "agents_responses_connect": _s(
        "responses.connect",
        "exec+net",
        "Responses WebSocket (response.create, queued response.steer).",
        agent_scope=True,
    ),
    "agents_responses_get": _s("responses.get", R, "Get or replay a stored response."),
    "agents_responses_delete": _s("responses.delete", D, "Delete a stored response."),
    "agents_responses_cancel": _s("responses.cancel", X, "Cancel the running turn of a response."),
    "agents_responses_input_items": _s(
        "responses.input_items.list", R, "List the input items of a response."
    ),
    "agents_responses_compact": _s(
        "responses.compact", "exec+net", "Summarize a conversation with the CLI.", agent_scope=True
    ),
    "agents_cannot_responses_input_tokens": _s(
        "responses.input_tokens.count", R, "Refused: input token counting."
    ),
    "agents_models_list": _s("agents.models.list", R, "List definitions and adapters as models."),
    "agents_models_get": _s("agents.models.get", R, "Get one model object."),
    "agents_cannot_models_delete": _s(
        "agents.models.delete", D, "Refused: model deletion."
    ),
    "agents_files_create": _s("files.create", W, "Store a local user_data blob."),
    "agents_webhooks_create": _s("webhooks.create", W, "Register a local webhook endpoint."),
    "agents_webhooks_get": _s("webhooks.get", R, "Get a webhook endpoint."),
    "agents_webhooks_update": _s("webhooks.update", W, "Update a webhook endpoint."),
    "agents_webhooks_list": _s("webhooks.list", R, "List webhook endpoints."),
    "agents_webhooks_delete": _s("webhooks.delete", D, "Delete a webhook endpoint."),
    "agents_webhooks_rotate_secret": _s(
        "webhooks.rotate_secret", W, "Rotate the signing secret of an endpoint."
    ),
    "agents_webhooks_test": _s("webhooks.test", "read+net", "Send a signed test event."),
    "agents_webhook_event_types": _s(
        "webhooks.event_types.list", R, "List the webhook event types."
    ),
}

#: Governed by the policy engine but not an HTTP route (the PTY WebSocket upgrade).
VIRTUAL_ROUTES: dict[str, _Spec] = {
    "pty_connect": _s("terminal.connect", X, "Attach to a PTY session over WebSocket (port 9001)."),
}

#: Routes that are not an operation of their own: one wire alias resolving to many operations.
ALIAS_FAMILIES: dict[str, str] = {"run_command": "custom.<name>"}

_PATH_PARAM = re.compile(r"\{(\w+)\}")
_NON_ID = re.compile(r"[^a-z0-9_]+")
_COMMAND_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}


def path_param_names(pattern: str) -> tuple[str, ...]:
    """The ``{name}`` placeholders of a route pattern, in order."""
    return tuple(_PATH_PARAM.findall(pattern))


def _free(registry: Registry, op_id: str) -> str:
    """*op_id*, or ``op_id_2``, ``op_id_3`` ... when taken."""
    candidate, n = op_id, 2
    while candidate in registry.all():
        candidate = f"{op_id}_{n}"
        n += 1
    return candidate


def _derive_id(route_name: str, group: str) -> tuple[str, bool]:
    """ID for a route the table above does not know: ``(op_id, declared_effects)``."""
    if group == "agents" and route_name.startswith("agents_"):
        derived = route_name.replace("_", ".")
        if is_valid_id(derived):
            return derived, False
    segment = _NON_ID.sub("_", route_name.lower())
    if not segment or not segment[0].isalpha():
        segment = f"c_{segment}"
    return f"ext.{segment}", False


def _register_route_op(
    registry: Registry,
    route_name: str,
    group: str,
    spec: _Spec | None,
    binding: HttpBinding | None,
    *,
    streaming: bool = False,
    auth_required: bool = True,
) -> Operation:
    if spec is not None:
        op_id, effects, summary = spec.op_id, spec.effects, spec.summary
        declared, agent_scope = True, spec.agent_scope
    else:
        op_id, _ = _derive_id(route_name, group)
        effects, summary, declared, agent_scope = frozenset({A}), "", False, False
        op_id = _free(registry, op_id)
        if not summary and binding is not None:
            summary = f"Custom route {binding.method} {binding.path}."
    path_names = path_param_names(binding.path) if binding is not None else ()
    operation = Operation(
        id=op_id,
        effects=effects,
        summary=summary,
        http=(binding,) if binding is not None else (),
        params=tuple(Param(name, "string", True) for name in path_names),
        group=group,
        stream="sse" if streaming else ("ws" if binding is None else "none"),
        aliases=(route_name,)
        if route_name != op_id and route_name not in registry._aliases
        else (),
        agent_scope=agent_scope,
        auth_required=auth_required,
        effects_declared=declared,
        legacy_route=route_name,
    )
    try:
        return registry.register(operation)
    except ValueError:
        if spec is not None:
            raise
        operation.id = _free(registry, f"ext.{_NON_ID.sub('_', route_name.lower())}")
        return registry.register(operation)


def build_registry(table: RouteTable, commands: CommandRegistry | None = None) -> Registry:
    """A registry with one operation per route of *table* plus ``custom.<name>`` per command."""
    from .discovery import register_native

    registry = Registry()
    register_native(registry)
    seen: dict[str, Operation] = {}
    for route in table._routes:
        if route.name in ALIAS_FAMILIES:
            continue
        binding = HttpBinding(route.method, route.path_pattern, legacy=True)
        existing = seen.get(route.name)
        if existing is not None:
            existing.http = (*existing.http, binding)
            continue
        seen[route.name] = _register_route_op(
            registry,
            route.name,
            route.group.value,
            LEGACY_OPS.get(route.name),
            binding,
            streaming=route.streaming,
            auth_required=route.auth_required,
        )
    for name, spec in VIRTUAL_ROUTES.items():
        if name not in seen:
            _register_route_op(registry, name, "terminal", spec, None)
    if commands is not None and any(r.name in ALIAS_FAMILIES for r in table._routes):
        for command_name, command in commands.list_all().items():
            op_id = _free(registry, mangle_custom_name(command_name))
            taken = command_name in registry._aliases or command_name in registry.all()
            registry.register(
                Operation(
                    id=op_id,
                    effects=frozenset({X}),
                    summary=command.description,
                    http=(HttpBinding("POST", f"/commands/{command_name}", legacy=True),),
                    params=tuple(
                        Param(
                            arg.name,
                            _COMMAND_TYPES.get(str(arg.type), "string"),
                            arg.required,
                            None if arg.required else arg.default,
                        )
                        for arg in command.args
                    ),
                    group="commands",
                    aliases=() if taken else (command_name,),
                    hidden=command.hidden,
                    legacy_route="run_command",
                    fixed_path_params={"name": command_name},
                )
            )
    return registry
