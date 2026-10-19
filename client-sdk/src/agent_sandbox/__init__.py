"""Agent Sandbox Client SDK — Create, manage, and interact with cloud sandboxes."""

from __future__ import annotations

from pkgutil import extend_path
from typing import TYPE_CHECKING, Any

from agent_sandbox._version import __version__

if TYPE_CHECKING:
    from agent_sandbox._standard import (
        ALL_TRAFFIC as ALL_TRAFFIC,
    )
    from agent_sandbox._standard import (
        ApiClient as ApiClient,
    )
    from agent_sandbox._standard import (
        ApiParams as ApiParams,
    )
    from agent_sandbox._standard import (
        AsyncCommandHandle as AsyncCommandHandle,
    )
    from agent_sandbox._standard import (
        AsyncSandbox as AsyncSandbox,
    )
    from agent_sandbox._standard import (
        AsyncSandboxPaginator as AsyncSandboxPaginator,
    )
    from agent_sandbox._standard import (
        AsyncSnapshotPaginator as AsyncSnapshotPaginator,
    )
    from agent_sandbox._standard import (
        AsyncTemplate as AsyncTemplate,
    )
    from agent_sandbox._standard import (
        AsyncVolume as AsyncVolume,
    )
    from agent_sandbox._standard import (
        AsyncWatchHandle as AsyncWatchHandle,
    )
    from agent_sandbox._standard import (
        AuthenticationException as AuthenticationException,
    )
    from agent_sandbox._standard import (
        BuildException as BuildException,
    )
    from agent_sandbox._standard import (
        BuildInfo as BuildInfo,
    )
    from agent_sandbox._standard import (
        BuildStatusReason as BuildStatusReason,
    )
    from agent_sandbox._standard import (
        CommandExitException as CommandExitException,
    )
    from agent_sandbox._standard import (
        CommandHandle as CommandHandle,
    )
    from agent_sandbox._standard import (
        CommandResult as CommandResult,
    )
    from agent_sandbox._standard import (
        ConnectionConfig as ConnectionConfig,
    )
    from agent_sandbox._standard import (
        CopyItem as CopyItem,
    )
    from agent_sandbox._standard import (
        EntryInfo as EntryInfo,
    )
    from agent_sandbox._standard import (
        FileNotFoundException as FileNotFoundException,
    )
    from agent_sandbox._standard import (
        FilesystemEvent as FilesystemEvent,
    )
    from agent_sandbox._standard import (
        FilesystemEventType as FilesystemEventType,
    )
    from agent_sandbox._standard import (
        FileType as FileType,
    )
    from agent_sandbox._standard import (
        FileUploadException as FileUploadException,
    )
    from agent_sandbox._standard import (
        Git as Git,
    )
    from agent_sandbox._standard import (
        GitAuthException as GitAuthException,
    )
    from agent_sandbox._standard import (
        GitBranches as GitBranches,
    )
    from agent_sandbox._standard import (
        GitFileStatus as GitFileStatus,
    )
    from agent_sandbox._standard import (
        GitHubMcpServer as GitHubMcpServer,
    )
    from agent_sandbox._standard import (
        GitHubMcpServerConfig as GitHubMcpServerConfig,
    )
    from agent_sandbox._standard import (
        GitResetMode as GitResetMode,
    )
    from agent_sandbox._standard import (
        GitStatus as GitStatus,
    )
    from agent_sandbox._standard import (
        GitUpstreamException as GitUpstreamException,
    )
    from agent_sandbox._standard import (
        InvalidArgumentException as InvalidArgumentException,
    )
    from agent_sandbox._standard import (
        LogEntry as LogEntry,
    )
    from agent_sandbox._standard import (
        LogEntryEnd as LogEntryEnd,
    )
    from agent_sandbox._standard import (
        LogEntryLevel as LogEntryLevel,
    )
    from agent_sandbox._standard import (
        LogEntryStart as LogEntryStart,
    )
    from agent_sandbox._standard import (
        McpServer as McpServer,
    )
    from agent_sandbox._standard import (
        NotEnoughSpaceException as NotEnoughSpaceException,
    )
    from agent_sandbox._standard import (
        NotFoundException as NotFoundException,
    )
    from agent_sandbox._standard import (
        OutputHandler as OutputHandler,
    )
    from agent_sandbox._standard import (
        ProcessInfo as ProcessInfo,
    )
    from agent_sandbox._standard import (
        ProxyTypes as ProxyTypes,
    )
    from agent_sandbox._standard import (
        PtyOutput as PtyOutput,
    )
    from agent_sandbox._standard import (
        PtySize as PtySize,
    )
    from agent_sandbox._standard import (
        RateLimitException as RateLimitException,
    )
    from agent_sandbox._standard import (
        ReadyCmd as ReadyCmd,
    )
    from agent_sandbox._standard import (
        Sandbox as Sandbox,
    )
    from agent_sandbox._standard import (
        SandboxException as SandboxException,
    )
    from agent_sandbox._standard import (
        SandboxInfo as SandboxInfo,
    )
    from agent_sandbox._standard import (
        SandboxInfoLifecycle as SandboxInfoLifecycle,
    )
    from agent_sandbox._standard import (
        SandboxLifecycle as SandboxLifecycle,
    )
    from agent_sandbox._standard import (
        SandboxMetrics as SandboxMetrics,
    )
    from agent_sandbox._standard import (
        SandboxNetworkInfo as SandboxNetworkInfo,
    )
    from agent_sandbox._standard import (
        SandboxNetworkOpts as SandboxNetworkOpts,
    )
    from agent_sandbox._standard import (
        SandboxNetworkRule as SandboxNetworkRule,
    )
    from agent_sandbox._standard import (
        SandboxNetworkRuleInfo as SandboxNetworkRuleInfo,
    )
    from agent_sandbox._standard import (
        SandboxNetworkRules as SandboxNetworkRules,
    )
    from agent_sandbox._standard import (
        SandboxNetworkSelector as SandboxNetworkSelector,
    )
    from agent_sandbox._standard import (
        SandboxNetworkSelectorContext as SandboxNetworkSelectorContext,
    )
    from agent_sandbox._standard import (
        SandboxNetworkTransform as SandboxNetworkTransform,
    )
    from agent_sandbox._standard import (
        SandboxNetworkUpdate as SandboxNetworkUpdate,
    )
    from agent_sandbox._standard import (
        SandboxNotFoundException as SandboxNotFoundException,
    )
    from agent_sandbox._standard import (
        SandboxOnTimeout as SandboxOnTimeout,
    )
    from agent_sandbox._standard import (
        SandboxPaginator as SandboxPaginator,
    )
    from agent_sandbox._standard import (
        SandboxQuery as SandboxQuery,
    )
    from agent_sandbox._standard import (
        SandboxState as SandboxState,
    )
    from agent_sandbox._standard import (
        SnapshotInfo as SnapshotInfo,
    )
    from agent_sandbox._standard import (
        SnapshotPaginator as SnapshotPaginator,
    )
    from agent_sandbox._standard import (
        Stderr as Stderr,
    )
    from agent_sandbox._standard import (
        Stdout as Stdout,
    )
    from agent_sandbox._standard import (
        Template as Template,
    )
    from agent_sandbox._standard import (
        TemplateBase as TemplateBase,
    )
    from agent_sandbox._standard import (
        TemplateBuildStatus as TemplateBuildStatus,
    )
    from agent_sandbox._standard import (
        TemplateBuildStatusResponse as TemplateBuildStatusResponse,
    )
    from agent_sandbox._standard import (
        TemplateClass as TemplateClass,
    )
    from agent_sandbox._standard import (
        TemplateException as TemplateException,
    )
    from agent_sandbox._standard import (
        TemplateTag as TemplateTag,
    )
    from agent_sandbox._standard import (
        TemplateTagInfo as TemplateTagInfo,
    )
    from agent_sandbox._standard import (
        TimeoutException as TimeoutException,
    )
    from agent_sandbox._standard import (
        Username as Username,
    )
    from agent_sandbox._standard import (
        Volume as Volume,
    )
    from agent_sandbox._standard import (
        VolumeAndToken as VolumeAndToken,
    )
    from agent_sandbox._standard import (
        VolumeApiParams as VolumeApiParams,
    )
    from agent_sandbox._standard import (
        VolumeConnectionConfig as VolumeConnectionConfig,
    )
    from agent_sandbox._standard import (
        VolumeEntryStat as VolumeEntryStat,
    )
    from agent_sandbox._standard import (
        VolumeException as VolumeException,
    )
    from agent_sandbox._standard import (
        VolumeFileType as VolumeFileType,
    )
    from agent_sandbox._standard import (
        VolumeInfo as VolumeInfo,
    )
    from agent_sandbox._standard import (
        WatchHandle as WatchHandle,
    )
    from agent_sandbox._standard import (
        WriteInfo as WriteInfo,
    )
    from agent_sandbox._standard import (
        client as client,
    )
    from agent_sandbox._standard import (
        default_build_logger as default_build_logger,
    )
    from agent_sandbox._standard import (
        get_signature as get_signature,
    )
    from agent_sandbox._standard import (
        wait_for_file as wait_for_file,
    )
    from agent_sandbox._standard import (
        wait_for_port as wait_for_port,
    )
    from agent_sandbox._standard import (
        wait_for_process as wait_for_process,
    )
    from agent_sandbox._standard import (
        wait_for_timeout as wait_for_timeout,
    )
    from agent_sandbox._standard import (
        wait_for_url as wait_for_url,
    )
    from agent_sandbox.api.sandbox import Sandbox as ProviderSandbox

# ``agent_sandbox`` is a shared namespace: ``agent_sandbox.server`` ships in the
# separate ``agent-sandbox-server`` distribution, possibly installed in another
# directory (editable installs, vendored layouts).
__path__ = extend_path(__path__, __name__)

__all__ = [
    "__version__",
    "Sandbox",
    "AsyncSandbox",
    "ProviderSandbox",
    "SandboxError",
    "AuthenticationError",
    "SandboxCreationError",
    "ExecutionError",
    "FileOperationError",
    "NetworkError",
    "sandbox",
]


def __getattr__(name: str) -> Any:
    if name == "ProviderSandbox":
        from agent_sandbox.api.sandbox import Sandbox

        return Sandbox
    if name in _STANDARD_EXPORTS:
        from agent_sandbox import _standard

        return getattr(_standard, name)
    if name in (
        "SandboxError",
        "AuthenticationError",
        "SandboxCreationError",
        "ExecutionError",
        "FileOperationError",
        "NetworkError",
    ):
        from agent_sandbox.models import errors

        return getattr(errors, name)
    if name == "sandbox":
        from agent_sandbox.declarative.decorator import sandbox as _sandbox

        return _sandbox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_STANDARD_EXPORTS = (
    "ApiClient",
    "client",
    "ConnectionConfig",
    "VolumeConnectionConfig",
    "ProxyTypes",
    "ApiParams",
    "VolumeApiParams",
    "Username",
    "SandboxException",
    "TimeoutException",
    "NotFoundException",
    "FileNotFoundException",
    "SandboxNotFoundException",
    "AuthenticationException",
    "GitAuthException",
    "GitUpstreamException",
    "InvalidArgumentException",
    "NotEnoughSpaceException",
    "TemplateException",
    "BuildException",
    "FileUploadException",
    "RateLimitException",
    "VolumeException",
    "SandboxInfo",
    "SandboxInfoLifecycle",
    "SandboxMetrics",
    "ProcessInfo",
    "SandboxQuery",
    "SandboxState",
    "SandboxMetrics",
    "GitStatus",
    "GitBranches",
    "GitFileStatus",
    "GitResetMode",
    "CommandResult",
    "Stderr",
    "Stdout",
    "CommandExitException",
    "PtyOutput",
    "PtySize",
    "FilesystemEvent",
    "FilesystemEventType",
    "EntryInfo",
    "WriteInfo",
    "FileType",
    "SandboxNetworkOpts",
    "SandboxNetworkInfo",
    "SandboxNetworkSelector",
    "SandboxNetworkSelectorContext",
    "SandboxNetworkRule",
    "SandboxNetworkRuleInfo",
    "SandboxNetworkRules",
    "SandboxNetworkTransform",
    "SandboxNetworkUpdate",
    "SandboxLifecycle",
    "SandboxOnTimeout",
    "ALL_TRAFFIC",
    "SnapshotInfo",
    "SnapshotPaginator",
    "AsyncSnapshotPaginator",
    "get_signature",
    "Sandbox",
    "SandboxPaginator",
    "WatchHandle",
    "CommandHandle",
    "OutputHandler",
    "AsyncSandboxPaginator",
    "AsyncSandbox",
    "AsyncWatchHandle",
    "AsyncCommandHandle",
    "Template",
    "AsyncTemplate",
    "TemplateBase",
    "TemplateClass",
    "CopyItem",
    "BuildInfo",
    "BuildStatusReason",
    "TemplateBuildStatus",
    "TemplateBuildStatusResponse",
    "TemplateTag",
    "TemplateTagInfo",
    "ReadyCmd",
    "wait_for_file",
    "wait_for_url",
    "wait_for_port",
    "wait_for_process",
    "wait_for_timeout",
    "LogEntry",
    "LogEntryStart",
    "LogEntryEnd",
    "LogEntryLevel",
    "default_build_logger",
    "McpServer",
    "GitHubMcpServer",
    "GitHubMcpServerConfig",
    "Git",
    "Volume",
    "AsyncVolume",
    "VolumeInfo",
    "VolumeAndToken",
    "VolumeEntryStat",
    "VolumeFileType",
)
__all__ = list(dict.fromkeys([*__all__, *_STANDARD_EXPORTS]))


def __dir__() -> list[str]:
    """Expose lazy public symbols to normal module introspection."""
    return sorted(set(globals()) | set(__all__))


def _resolve_provider_schema(provider_id: str) -> Any:
    """Composition adapter; discovery stays lazy and outside transport."""
    from agent_sandbox._provider_schema import ProviderSchema
    from agent_sandbox.providers.bundled_config import bundled_config

    metadata = bundled_config(provider_id)
    if metadata is not None:
        return ProviderSchema(
            metadata["id"],
            metadata["keys"],
            metadata["inherit"],
            dict(metadata["derive"]),
            dict(metadata["endpoint_defaults"]),
            legacy_fields=metadata["legacy_fields"],
            omit_default_options=metadata["omit_default_options"],
            legacy_url_builder=metadata["legacy_url_builder"],
            legacy_port_factory=metadata["legacy_port_factory"],
            legacy_pty_url_builder=metadata["legacy_pty_url_builder"],
        )
    from agent_sandbox.providers.registry import get_provider

    provider = get_provider(provider_id)
    return ProviderSchema(
        provider.id,
        provider.config_keys(),
        frozenset(provider.inherit),
        dict(provider.derive),
        dict(getattr(provider, "endpoint_defaults", {}) or {}),
        legacy_fields=frozenset(getattr(provider, "legacy_fields", ())),
        omit_default_options=bool(getattr(provider, "omit_default_options", False)),
        legacy_url_builder=getattr(provider, "legacy_session_url", None),
    )


from agent_sandbox._provider_schema import _set_resolver  # noqa: E402

_set_resolver(_resolve_provider_schema)
del _set_resolver
