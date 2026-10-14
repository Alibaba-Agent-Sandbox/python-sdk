# Command and SDK map

Each row is the closest entry point for the same job in the three products. It is not parameter-for-parameter compatibility, and it does not shrink Agent Sandbox to a subset of either product.

`abx` is the Agent Sandbox command line. The Python SDK is `agent-sandbox`. The default provider is Alibaba Cloud Express. After the `opensandbox` provider is installed, the `abx` command names stay the same and the calls go to an OpenSandbox server. That is a different command from running `osb`.

Public surfaces used for this map:

| Product | CLI | SDK |
|---|---|---|
| Agent Sandbox | `abx` (`@agent-sandbox/cli`) | `agent-sandbox`, `from agent_sandbox.api.sandbox import Sandbox` |
| E2B | `e2b` (`@e2b/cli`, docs for 2.16.1) | `e2b`, `from e2b import Sandbox` |
| OpenSandbox | `osb` (`opensandbox-cli`, [CLI](https://open-sandbox.ai/cli/)) | `opensandbox`, `from opensandbox import Sandbox` ([Python SDK](https://open-sandbox.ai/sdks/python)) |

A small set of E2B-shaped methods is also available from `agent_sandbox.compat`. Differences and the move are in [Migrating from E2B](migrate-from-e2b.md). The HTTP field map for the OpenSandbox provider is the design note [provider-opensandbox-mapping](../design/provider-opensandbox-mapping.md).

A cell with "—" means that side has no matching public command or method.

## Install and credentials

| Job | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Install | `npm install -g @agent-sandbox/cli` | `pip install agent-sandbox` | `npm install -g @e2b/cli` | `pip install e2b` | `pip install opensandbox-cli` | `pip install opensandbox` |
| Store a credential | `abx config set sandbox_api_key` | environment variable `ABX_SANDBOX_API_KEY` | `e2b auth login` | environment variable `E2B_API_KEY` | `osb config set connection.api_key` | `ConnectionConfig(api_key=…)` or `OPEN_SANDBOX_API_KEY` |
| Show the effective config | `abx config list` | — | `e2b auth info` | — | `osb config show` | — |

Alibaba Cloud access keys keep the official names `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`. The OpenSandbox address is `osb config set connection.domain`, and the environment variable is `OPEN_SANDBOX_DOMAIN`.

## Sandbox lifecycle

| Job | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Create | `abx create --template <name>` | `Sandbox.create(template=…)` | `e2b sandbox create [template]` | `Sandbox.create(template)` | `osb sandbox create --image <image>` | `Sandbox.create("<image>")` |
| Attach to an existing sandbox | `abx connect <id>` | `Sandbox.connect(id)` | `e2b sandbox connect <id>` | `Sandbox.connect(id)` | — | `Sandbox.connect(sandbox_id)` |
| List | `abx list` | `Sandbox.list()` | `e2b sandbox list` | `Sandbox.list()` | `osb sandbox list` | a manager lists sandboxes |
| Inspect one | `abx info <id>` | `sandbox.refresh_info()` | `e2b sandbox info <id>` | read the object after create or connect | `osb sandbox get <id>` | read the object after connect |
| Destroy | `abx kill <id>` | `sandbox.kill()`, or `Sandbox.kill_by_id(id)` | `e2b sandbox kill <id>` | `sandbox.kill()`, or `Sandbox.kill(id)` | `osb sandbox kill <id>` | `sandbox.kill()`; `destroy()` terminates the remote sandbox and then closes local resources |
| Extend lifetime | `abx create --timeout <seconds>` (set at create) | `sandbox.set_timeout(seconds)` | `e2b sandbox create --timeout` | `sandbox.set_timeout(seconds)` | `osb sandbox renew <id> --timeout 30m` | `sandbox.renew(timedelta)` |
| Pause | — | `sandbox.pause()` | `e2b sandbox pause <id>` | `sandbox.pause()` | `osb sandbox pause <id>` | `sandbox.pause()` |
| Resume | — | `sandbox.resume()` | `e2b sandbox resume <id>` | `Sandbox.connect` attaches to a paused sandbox | `osb sandbox resume <id>` | `Sandbox.resume(sandbox_id=…)` |
| Check that it is up | — | `sandbox.is_running()` | `e2b sandbox list --state running` | `sandbox.is_running()` | `osb sandbox health <id>` | `is_healthy()` |
| Address for a port | — | `sandbox.network.get_host(port)`, `get_url(port)` | — | `sandbox.get_host(port)` | `osb sandbox endpoint <id> --port 8080` | `sandbox.get_endpoint(port)` |

The three create calls do not select the same kind of object. `abx create --template` and `Sandbox.create(template=…)` take a template name. `e2b sandbox create` takes an E2B template, and the build result is a snapshot. `osb sandbox create --image` and `Sandbox.create("python:3.12")` take an image URI. OpenSandbox can also take `--template` or `--snapshot-id`, and those three flags are mutually exclusive.

`abx connect` is a line-at-a-time REPL, not a PTY. E2B's `e2b sandbox connect` attaches a terminal to the sandbox. OpenSandbox's persistent shell is `osb command session`.

Pause depends on the runtime. On Docker, OpenSandbox pause is a cgroup freeze, and resume is `Sandbox.resume`. E2B pause can continue after a timeout. Agent Sandbox forwards `pause` and `resume` to the current provider.

## Run something inside

| Job | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Run one command | `abx exec <id> <command>` | `sandbox.commands.run(cmd)` | `e2b sandbox exec <id> <command>` | `sandbox.commands.run(cmd)` | `osb command run <id> -- <command>`; the short form is `osb exec` | `sandbox.commands.run(cmd)` |
| Background command | `abx sandbox process start` | `sandbox.commands.start(…, background=True)` | `e2b sandbox exec -b` | the background argument of `commands.run` | `osb command run --background` | `commands.run`, then `get_command_status` |
| Read background output | — | `commands.stream` | — | the command stream | `osb command logs <id> <execution-id>` | `commands.get_background_command_logs` |
| Interrupt | `abx sandbox process signal` | `commands.send_signal(pid, 15 or 9)` | — | stop that process | `osb command interrupt <id> <execution-id>` | `commands.interrupt(execution.id)` |
| List processes | `abx sandbox process list` | `commands.list()` | — | — | — | — |
| Persistent shell | each line of `abx connect` is a new process | — | `e2b sandbox connect` | PTY | `osb command session create`, then `session run` | `commands.create_session`, `run_in_session`, `delete_session` |
| Interactive terminal | `abx sandbox shell-stream` | `sandbox.get_terminal()` | `e2b sandbox connect` | `sandbox.pty` | — | execd's PTY WebSocket |
| Run a snippet | — | `sandbox.run_code(code)` | — | `sandbox.run_code(code)` | — | `/code` on a code-interpreter image; the package is `opensandbox-code-interpreter` |
| Registered command | `abx run <id> <name> --arg k=v` | `sandbox.run(name, **kwargs)` | — | — | — | — |
| List registered commands | `abx command list <id>` | `sandbox.list_commands()` | — | — | — | — |

Agent Sandbox sends only signal 15 (SIGTERM) and signal 9 (SIGKILL). OpenSandbox `interrupt` stops one execd execution, not an arbitrary numeric pid.

## Files

| Job | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Read | `abx download` writes a local file | `files.read`, `read_bytes` | — | `files.read` | `osb file cat`, `osb file download` | `files.read_file` |
| Write | `abx upload` | `files.write` | — | `files.write` | `osb file write`, `osb file upload` | `files.write_files` |
| List a directory | `abx sandbox files list` | `files.list` | — | `files.list` | — | `files.list_directory` |
| Metadata | `abx sandbox files stat` | `files.get_info` | — | the info object from the files API | `osb file info` | entries from list or search |
| Make a directory | `abx sandbox files mkdir` | `files.make_dir` | — | `files.make_dir` | — | upload creates parent directories |
| Delete | `abx sandbox files rm` | `files.remove` | — | `files.remove` | — | `files.delete_files` |
| Move | `abx sandbox files mv` | `files.move`, `rename` | — | `files.rename` | — | — |
| Search | `abx sandbox files search` | — | — | — | `osb file search` | `files.search` |
| Exists | — | `files.exists` | — | `files.exists` | — | a failed read or stat means it is absent |
| Watch | — | `files.watch` | — | `files.watch_dir` | — | — |
| Signed file URL | — | `upload_url` / `download_url` raise `FileOperationError`. `files.upload_url` still requires `X-Access-Token` | — | `upload_url`, `download_url` | — | `get_endpoint` resolves a port, not a signed URL for one file |

E2B file operations live on the SDK. The CLI reaches files through `e2b sandbox exec`. OpenSandbox `file download` replaces the local destination only after the whole download succeeds.

## Templates

| Job | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Scaffold a local project | `abx template init` | — | `e2b template init` | the `Template()` builder | — | — |
| Build and publish | `abx template deploy`; the steps are `build` and `push` | — (the CLI builds and deploys) | `e2b template create <name>` (`template build` is deprecated) | `Template.build` | `osb template create --image … --publish …` | the SDK template API |
| List | `abx template list` | — | `e2b template list` | the template API | `osb template list` | the same API |
| Inspect | `abx template info` | — | — | — | `osb template get <id>` | the same API |
| Delete | `abx template delete` | — | `e2b template delete` | — | `osb template delete` | the same API |
| Search a catalog | `abx template search`; install with `abx template install` | — | — | — | — | — |
| Snapshot | — | a provider capability | the template build is the snapshot | `Template.build` | `osb snapshot create <sandbox-id>` | the snapshot API |
| Publish or unpublish | — | — | `e2b template publish`, `unpublish` | — | — | — |

"Template" is not the same object in the three products. An Agent Sandbox template is `template.yaml` plus an image. The default provider hands that to Alibaba Cloud Express. An E2B template build produces a snapshot that can start directly. `osb template` builds a golden image on a Kubernetes runtime; the Docker runtime does not serve that API. Start OpenSandbox from a snapshot with `osb sandbox create --snapshot-id`.

## Capabilities that belong to one side

| Capability | Where | The other two |
|---|---|---|
| Swappable sandbox providers | `abx provider`, and the SDK provider plugins | E2B and OpenSandbox each own their control plane |
| Modal-style functions | `@sandbox`, see [Declarative usage](declarative-usage.md) | no decorator of that name |
| Registered commands | `abx run`, `sandbox.run()` | no equivalent layer |
| Agents API | in-sandbox HTTP. Codex and Qwen Code are supported today. See [Agents API](agents-api.md) | no `/v1/agents/sessions` |
| MCP | `abx mcp install/start/status/deploy` | E2B has no command group of that name. OpenSandbox has `osb skills`, which installs its own skill packs |
| Egress policy | provider policy | E2B uses its own network limits. OpenSandbox uses `osb egress get/patch` |
| Credential store | inject environment variables at create | OpenSandbox also has `osb credential-vault`, which needs `--credential-proxy` at create |
| Diagnostic logs | `abx sandbox system metrics` | `e2b sandbox logs`, `e2b sandbox metrics`. OpenSandbox uses `osb diagnostics logs/events`; the older entry is `osb devops` |
| Per-endpoint route policy | `agent-sandbox-server` policy, see [Fine-grained capabilities](fine-grained-capabilities.md) | that is the HTTP server inside the sandbox, not the E2B or OpenSandbox control plane |

## Related

- [Migrating from E2B](migrate-from-e2b.md)
- [Comparison](comparison.md)
- [CLI reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/cli-reference.md)
- [Providers](providers.md)
