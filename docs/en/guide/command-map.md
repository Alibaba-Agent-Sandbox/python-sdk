# Command and SDK map

Each row is the closest entry point for the same job in the three products. It is not parameter-for-parameter compatibility, and it does not shrink Easy Sandbox to a subset of either product.

`ebx` is the Easy Sandbox command line. The Python SDK is `easy-sandbox`. The default provider is Alibaba Cloud Express. After the `opensandbox` provider is installed, the `ebx` command names stay the same and the calls go to an OpenSandbox server. That is a different command from running `osb`.

Public surfaces used for this map:

| Product | CLI | SDK |
|---|---|---|
| Easy Sandbox | `ebx` (`@easy-sandbox/cli`) | `easy-sandbox`, `from easy_sandbox.api.sandbox import Sandbox` |
| E2B | `e2b` (`@e2b/cli`, docs for 2.16.1) | `e2b`, `from e2b import Sandbox` |
| OpenSandbox | `osb` (`opensandbox-cli`, [CLI](https://open-sandbox.ai/cli/)) | `opensandbox`, `from opensandbox import Sandbox` ([Python SDK](https://open-sandbox.ai/sdks/python)) |

A small set of E2B-shaped methods is also available from `easy_sandbox.compat`. Differences and the move are in [Migrating from E2B](migrate-from-e2b.md). The HTTP field map for the OpenSandbox provider is the design note [provider-opensandbox-mapping](../design/provider-opensandbox-mapping.md).

A cell with "—" means that side has no matching public command or method.

## Install and credentials

| Job | ebx | Easy Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Install | `npm install -g @easy-sandbox/cli` | `pip install easy-sandbox` | `npm install -g @e2b/cli` | `pip install e2b` | `pip install opensandbox-cli` | `pip install opensandbox` |
| Store a credential | `ebx config set sandbox_api_key` | environment variable `EBX_SANDBOX_API_KEY` | `e2b auth login` | environment variable `E2B_API_KEY` | `osb config set connection.api_key` | `ConnectionConfig(api_key=…)` or `OPEN_SANDBOX_API_KEY` |
| Show the effective config | `ebx config list` | — | `e2b auth info` | — | `osb config show` | — |

Alibaba Cloud access keys keep the official names `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`. The OpenSandbox address is `osb config set connection.domain`, and the environment variable is `OPEN_SANDBOX_DOMAIN`.

## Sandbox lifecycle

| Job | ebx | Easy Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Create | `ebx create --template <name>` | `Sandbox.create(template=…)` | `e2b sandbox create [template]` | `Sandbox.create(template)` | `osb sandbox create --image <image>` | `Sandbox.create("<image>")` |
| Attach to an existing sandbox | `ebx connect <id>` | `Sandbox.connect(id)` | `e2b sandbox connect <id>` | `Sandbox.connect(id)` | — | `Sandbox.connect(sandbox_id)` |
| List | `ebx list` | `Sandbox.list()` | `e2b sandbox list` | `Sandbox.list()` | `osb sandbox list` | a manager lists sandboxes |
| Inspect one | `ebx info <id>` | `sandbox.refresh_info()` | `e2b sandbox info <id>` | read the object after create or connect | `osb sandbox get <id>` | read the object after connect |
| Destroy | `ebx kill <id>` | `sandbox.kill()`, or `Sandbox.kill_by_id(id)` | `e2b sandbox kill <id>` | `sandbox.kill()`, or `Sandbox.kill(id)` | `osb sandbox kill <id>` | `sandbox.kill()`; `destroy()` terminates the remote sandbox and then closes local resources |
| Extend lifetime | `ebx create --timeout <seconds>` (set at create) | `sandbox.set_timeout(seconds)` | `e2b sandbox create --timeout` | `sandbox.set_timeout(seconds)` | `osb sandbox renew <id> --timeout 30m` | `sandbox.renew(timedelta)` |
| Pause | — | `sandbox.pause()` | `e2b sandbox pause <id>` | `sandbox.pause()` | `osb sandbox pause <id>` | `sandbox.pause()` |
| Resume | — | `sandbox.resume()` | `e2b sandbox resume <id>` | `Sandbox.connect` attaches to a paused sandbox | `osb sandbox resume <id>` | `Sandbox.resume(sandbox_id=…)` |
| Check that it is up | — | `sandbox.is_running()` | `e2b sandbox list --state running` | `sandbox.is_running()` | `osb sandbox health <id>` | `is_healthy()` |
| Address for a port | — | `sandbox.network.get_host(port)`, `get_url(port)` | — | `sandbox.get_host(port)` | `osb sandbox endpoint <id> --port 8080` | `sandbox.get_endpoint(port)` |

The three create calls do not select the same kind of object. `ebx create --template` and `Sandbox.create(template=…)` take a template name. `e2b sandbox create` takes an E2B template, and the build result is a snapshot. `osb sandbox create --image` and `Sandbox.create("python:3.12")` take an image URI. OpenSandbox can also take `--template` or `--snapshot-id`, and those three flags are mutually exclusive.

`ebx connect` is a line-at-a-time REPL, not a PTY. E2B's `e2b sandbox connect` attaches a terminal to the sandbox. OpenSandbox's persistent shell is `osb command session`.

Pause depends on the runtime. On Docker, OpenSandbox pause is a cgroup freeze, and resume is `Sandbox.resume`. E2B pause can continue after a timeout. Easy Sandbox forwards `pause` and `resume` to the current provider.

## Run something inside

| Job | ebx | Easy Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Run one command | `ebx exec <id> <command>` | `sandbox.commands.run(cmd)`, also `sandbox.run(cmd)` | `e2b sandbox exec <id> <command>` | `sandbox.commands.run(cmd)` | `osb command run <id> -- <command>`; the short form is `osb exec` | `sandbox.commands.run(cmd)` |
| Background command | `ebx sandbox process start` | `sandbox.commands.start(…, background=True)` | `e2b sandbox exec -b` | the background argument of `commands.run` | `osb command run --background` | `commands.run`, then `get_command_status` |
| Read background output | — | `commands.stream` | — | the command stream | `osb command logs <id> <execution-id>` | `commands.get_background_command_logs` |
| Interrupt | `ebx sandbox process signal` | `commands.send_signal(pid, 15 or 9)` | — | stop that process | `osb command interrupt <id> <execution-id>` | `commands.interrupt(execution.id)` |
| List processes | `ebx sandbox process list` | `commands.list()` | — | — | — | — |
| Persistent shell | each line of `ebx connect` is a new process | — | `e2b sandbox connect` | PTY | `osb command session create`, then `session run` | `commands.create_session`, `run_in_session`, `delete_session` |
| Interactive terminal | `ebx sandbox shell-stream` | `sandbox.get_terminal()` | `e2b sandbox connect` | `sandbox.pty` | — | execd's PTY WebSocket |
| Run a snippet | — | `sandbox.run_code(code)` | — | `sandbox.run_code(code)` | — | `/code` on a code-interpreter image; the package is `opensandbox-code-interpreter` |
| Template custom command | `ebx run <name>` | `sandbox.custom(name, **kwargs)` | — | — | — | — |

Easy Sandbox sends only signal 15 (SIGTERM) and signal 9 (SIGKILL). OpenSandbox `interrupt` stops one execd execution, not an arbitrary numeric pid.

## Files

| Job | ebx | Easy Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Read | `ebx download` writes a local file | `files.read`, `read_bytes` | — | `files.read` | `osb file cat`, `osb file download` | `files.read_file` |
| Write | `ebx upload` | `files.write` | — | `files.write` | `osb file write`, `osb file upload` | `files.write_files` |
| List a directory | `ebx sandbox files list` | `files.list` | — | `files.list` | — | `files.list_directory` |
| Metadata | `ebx sandbox files stat` | `files.get_info` | — | the info object from the files API | `osb file info` | entries from list or search |
| Make a directory | `ebx sandbox files mkdir` | `files.make_dir` | — | `files.make_dir` | — | upload creates parent directories |
| Delete | `ebx sandbox files rm` | `files.remove` | — | `files.remove` | — | `files.delete_files` |
| Move | `ebx sandbox files mv` | `files.move`, `rename` | — | `files.rename` | — | — |
| Search | `ebx sandbox files search` | — | — | — | `osb file search` | `files.search` |
| Exists | — | `files.exists` | — | `files.exists` | — | a failed read or stat means it is absent |
| Watch | — | `files.watch` | — | `files.watch_dir` | — | — |
| Signed file URL | — | `sandbox.get_upload_url(path)`, `get_download_url(path)` | — | `get_upload_url`, `get_download_url` | — | `get_endpoint` resolves a port, not a signed URL for one file |

E2B file operations live on the SDK. The CLI reaches files through `e2b sandbox exec`. OpenSandbox `file download` replaces the local destination only after the whole download succeeds.

## Templates

| Job | ebx | Easy Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| Scaffold a local project | `ebx template init` | — | `e2b template init` | the `Template()` builder | — | — |
| Build and publish | `ebx template deploy`; the steps are `build` and `push` | `Sandbox.deploy` | `e2b template create <name>` (`template build` is deprecated) | `Template.build` | `osb template create --image … --publish …` | the SDK template API |
| List | `ebx template list` | — | `e2b template list` | the template API | `osb template list` | the same API |
| Inspect | `ebx template info` | — | — | — | `osb template get <id>` | the same API |
| Delete | `ebx template delete` | — | `e2b template delete` | — | `osb template delete` | the same API |
| Search a catalog | `ebx template search`; install with `ebx template install` | — | — | — | — | — |
| Snapshot | — | a provider capability | the template build is the snapshot | `Template.build` | `osb snapshot create <sandbox-id>` | the snapshot API |
| Publish or unpublish | — | — | `e2b template publish`, `unpublish` | — | — | — |

"Template" is not the same object in the three products. An Easy Sandbox template is `template.yaml` plus an image. The default provider hands that to Alibaba Cloud Express. An E2B template build produces a snapshot that can start directly. `osb template` builds a golden image on a Kubernetes runtime; the Docker runtime does not serve that API. Start OpenSandbox from a snapshot with `osb sandbox create --snapshot-id`.

## Capabilities that belong to one side

| Capability | Where | The other two |
|---|---|---|
| Swappable sandbox providers | `ebx provider`, and the SDK provider plugins | E2B and OpenSandbox each own their control plane |
| Modal-style functions | `@sandbox`, see [Declarative usage](declarative-usage.md) | no decorator of that name |
| Template custom commands | `ebx run`, `sandbox.custom()` | no equivalent layer |
| Agents API | in-sandbox HTTP. Codex and Qwen Code are supported today. See [Agents API](agents-api.md) | no `/v1/agents/sessions` |
| MCP | `ebx mcp install/start/status/deploy` | E2B has no command group of that name. OpenSandbox has `osb skills`, which installs its own skill packs |
| Egress policy | provider policy | E2B uses its own network limits. OpenSandbox uses `osb egress get/patch` |
| Credential store | inject environment variables at create | OpenSandbox also has `osb credential-vault`, which needs `--credential-proxy` at create |
| Diagnostic logs | `ebx sandbox system metrics` | `e2b sandbox logs`, `e2b sandbox metrics`. OpenSandbox uses `osb diagnostics logs/events`; the older entry is `osb devops` |
| Per-endpoint route policy | `easy-sandbox-server` policy, see [Fine-grained capabilities](fine-grained-capabilities.md) | that is the HTTP server inside the sandbox, not the E2B or OpenSandbox control plane |

## Related

- [Migrating from E2B](migrate-from-e2b.md)
- [Comparison](comparison.md)
- [CLI reference](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/cli-reference.md)
- [Providers](providers.md)
