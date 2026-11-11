# CLI and SDK responsibilities

This guide describes the current CLI source. Standard Python `Sandbox` / `AsyncSandbox`, the cross-provider `ProviderSandbox`, and the application HTTP client are distinct entry points. Check the installed release’s `--help` before using these commands.

| Task | CLI | ProviderSandbox / Python |
| --- | --- | --- |
| Acquire and author source | `abx template list / info / init` | `—` |
| Prepare a reusable build | `abx template build SOURCE --yes` | `—` |
| Publish a source version | `abx template publish SOURCE --tag VERSION --yes` | `—` |
| Deploy source | `abx deploy SOURCE --name APP --yes` | `—` |
| Create from a native template | `abx deploy --template-id TEMPLATE --name APP --yes` | `await ProviderSandbox.create(template=..., provider=...)` |
| Inspect and delete | `abx list; abx status APP; abx delete APP --yes` | `await sandbox.refresh_info(); await sandbox.kill()` |
| Run a process | `abx sandbox exec APP -- COMMAND` | `await sandbox.commands.run(command)` |
| Invoke a registered function | `abx sandbox command run APP FUNCTION --arg key=value` | `await sandbox.run(name, **kwargs)` |
| List registered functions | `abx sandbox command list APP` | `await sandbox.list_commands()` |
| Provider-native operations | `abx provider command list PROVIDER; abx provider run OPERATION` | `agent_sandbox.providers.commands` |

A local CLI deployment name is not a remote Sandbox ID. Inspect `abx status APP`, then connect to its actual ID with `ProviderSandbox.connect(id, provider=...)` and the same provider. `close()` releases a client; the creator owns remote deletion. Managed applications expose their own HTTP API and are not a single Sandbox handle.

[Standard client migration](migrate-from-e2b.md) · [Application connections and authentication](template-workflows.md) · [Template authoring](authoring-templates.md)
