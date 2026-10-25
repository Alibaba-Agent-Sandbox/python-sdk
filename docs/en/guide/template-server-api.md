# Template server HTTP API

A generated template ships `Dockerfile`, `commands.py`, and `template.yaml`. After the sandbox starts, callers reach it over HTTP. `commands.py` is the container's main process: it registers named commands with `@command` and calls `start(9000)` (or `SandboxServer(...).serve(port=9000)`).

The `FROM` image in the Dockerfile varies by template. This HTTP API does not. Every template that starts `agent_sandbox.server` exposes the routes below. The server is the Python standard library only (`ThreadingHTTPServer`). It accepts `GET`, `POST`, and `DELETE`. A trailing slash is stripped before matching (`/health/` is `/health`).

A short client for a server that is already running is [`examples/templates/python-hello/call_api.py`](../../../examples/templates/python-hello/call_api.py).

---

## Reaching the sandbox

The server defaults to `0.0.0.0:9000`. The provider must implement the required port resolution and network path, and the service must actually listen. Do not treat every endpoint as a `{port}-{sandbox_id}.{domain}` hostname. Resolve application HTTP independently from internal envd/EPP transport:

This example uses the provider-native `ProviderSandbox` API in the published
`agent-sandbox-client==0.4.0a3` alpha; the standard `Sandbox`/`AsyncSandbox` classes
have a different interface. See [installation](install-python.md) for the exact
package/source choices. Set `SANDBOX_ID` to an existing sandbox whose application
server is running, and `ABX_SERVER_TOKEN` only if that server was started with it.

```python
import asyncio
import os
from agent_sandbox import ProviderSandbox

async def main() -> None:
    sandbox = await ProviderSandbox.connect(os.environ["SANDBOX_ID"])
    try:
        async with await sandbox.application_client(
            9000, token=os.environ.get("ABX_SERVER_TOKEN") or None
        ) as client:
            print(await client.commands.run("hello", name="Python"))
    finally:
        await sandbox.close()

asyncio.run(main())
```

`close()` releases this client connection; it leaves the existing sandbox running.
The creator remains responsible for `kill()` or `abx kill ID`.


This resolves the endpoint for that sandbox and port, preserving the full proxy prefix and signed query. Gateway headers and the application `ABX_SERVER_TOKEN` are separate; no control-plane API key is copied and no anonymous authentication retry occurs. Redirects (including another sandbox on the same origin), URL userinfo and authority overrides are rejected. Operation-signed endpoints require the provider's per-operation resolver, never generic prefix joining.

For a server you started locally, use an explicit `http://127.0.0.1:9000` application URL. Terminal WebSocket uses `ABX_PTY_PORT` (default `9001`) and requires its own declared/published port and protocol. Image port declarations, platform publication, network binding, application protocol and server policy are separate checks. See [explicit template workflows](template-workflows.md).

---

## Authentication

`SandboxServer` reads `ABX_SERVER_TOKEN` once at startup.

- Unset or empty: authentication defaults to `anonymous`; endpoint policy still applies. A presented credential that matches no configured token stays anonymous as well (a gateway `X-Access-Token` is not a server login).
- Set: routes registered with `auth_required=True` (the default) require the token in `X-Access-Token` or `Authorization: Bearer <token>`. Both headers are accepted on every route and compared with `hmac.compare_digest`. A missing or wrong token is `401`:

```json
{"error": "unauthorized", "type": "AuthError"}
```

Two different `X-Access-Token` values in one request are `400` `ambiguous_credentials`.

`GET /health` is the only built-in route registered with `auth_required=False`. It stays open when a token is set.

`GET /capabilities` and `POST /capabilities/check` are registered with `auth_required=True`. They answer without a header only while `ABX_SERVER_TOKEN` is unset. With a token set, send a credential.

Errors from the `/v1/` Agents handlers use the OpenAI envelope `{"error": {"message", "type", "param", "code"}}`.

Do not put the token in `commands.py`. Pass it as an environment variable. `POST /env` refuses to overwrite `ABX_SERVER_TOKEN` and any name whose uppercase form starts with `ABX_`.

The PTY WebSocket (port 9001, path `/pty`) checks the same credentials. It accepts `Authorization: Bearer`, `X-Access-Token`, or `?token=`, and requires the `pty_connect` endpoint to be enabled.

---

## Capability groups

Every route is an endpoint with one id, and one rule per endpoint decides whether it answers. A group is only a name for a set of endpoint ids. There is no separate group gate. A disabled endpoint answers `404` and names the rule that disabled it:

```json
{"error": "Endpoint 'code_run' is disabled: group 'dev_tools' is opt-in. Enable the group (ABX_SERVER_ENABLED_GROUPS=dev_tools, policy groups: [dev_tools]) or this endpoint (policy endpoints.code_run.enabled: true)",
 "type": "ValueError", "code": "endpoint_disabled", "endpoint": "code_run", "rule": "default:opt-in:dev_tools"}
```

`core` (`health`, `capabilities`, `capabilities_check`) is always on. `RouteTable.disable_group(CapabilityGroup.CORE)` raises `ValueError`. The other groups start like this:

| Group | Default | What it turns on |
|-------|---------|------------------|
| `core` | on, cannot disable | `GET /health`, `GET /capabilities`, `POST /capabilities/check` |
| `commands` | on | `GET /commands`, `POST /commands/{name}` |
| `file_ops` | on | `POST /upload`, `GET /download`, and `/files/*` |
| `process` | on | `POST /shell`, `POST /shell/stream`, `/process/*` |
| `terminal` | on | `/pty/sessions*` and the WebSocket on port 9001 |
| `system` | on | `/system/info`, `/system/metrics`, `/env`, `/ports`, `/packages` |
| `dev_tools` | off | `POST /code/run`, `GET /git/status`, `GET /git/diff` |
| `browser` | off | `/browser/*` (Playwright; `503` if Playwright is not installed) |
| `agents` | off | `/v1/agents/...`, `/v1/vaults`, `/v1/responses`, `/v1/models`, `/v1/files` and `/v1/webhook_endpoints`. Stays off until a layer enables it |

Ways to switch, all ending in the same per-endpoint rules:

| Where | Form |
|---|---|
| `commands.py` | `default_table().enable_group(CapabilityGroup.FILE_OPS)` / `disable_group(...)` |
| `template.yaml` `server:` | `groups: [agents, dev_tools]` or `groups: {process: false}`; `endpoints:` for single ids |
| environment | `ABX_SERVER_ENABLED_GROUPS=agents,dev_tools` (comma list, turns groups on only) |

There is no environment variable that turns a group off. Write `groups: {process: false}` in `server:` or an `endpoints` rule instead. Layers, specificity and the `rule` names are in [Fine-grained capabilities](fine-grained-capabilities.md).

`provides`, explicit workflows, exact provider operations and this endpoint policy are separate contracts. Retired template `capabilities` is rejected; a workflow never enables an endpoint automatically.

---

## Common response rules

Success and error bodies are JSON (`Content-Type: application/json; charset=utf-8`). Handler errors use:

```json
{"error": "<message>", "type": "<ExceptionName>"}
```

An unknown path is `404` `{"error": "Not found: <path>", "type": "ValueError"}`. An uncaught handler exception is `500` with `error` and `type`. A policy denial adds `code` (`endpoint_disabled`, `missing_scope`, `path_not_allowed`, `command_not_allowed`, `rate_limited`, ...) and `endpoint`. A disabled endpoint also carries `rule`. A repeated query parameter is `400` `duplicate_parameter`.

`POST` and `DELETE` read a JSON object body. The raw body limit is 10 MiB (`413`, `code` `payload_too_large`). An empty body becomes `{}`. Invalid JSON is `400`.

Streaming routes (`streaming=True`) return `text/event-stream`. Each chunk is `event: <name>\ndata: <json>\n\n`.

Every route that takes a path (file routes, and the `cwd` of `/shell` and process start) is confined to `ABX_SERVER_BASE_DIR` (default `/home/user`), or to the policy's `base_dir` or per-endpoint `paths.allow`. A path outside it is `403` `path_not_allowed`. Decoded upload size defaults to 100 MiB (`ABX_MAX_UPLOAD_SIZE`). The 10 MiB JSON body cap applies first, so a base64 body cannot actually reach 100 MiB.

`POST /shell` and process start split the command with `shlex.split` and run it with `shell=False`. Pipes, redirects, and `$VAR` are not interpreted. Use `bash -c '...'` when you need a shell.

---

## Built-in routes

### `core`

#### `GET /health`

No auth. Always `200`.

```json
{"status": "ok"}
```

#### `GET /capabilities`

Discovery document. With no policy loaded and no token set, `policy.configured` is `false` and `identity` is `{"id": "anonymous", "scopes": ["*"]}`.

```json
{
  "api_version": 2,
  "server_version": "<package version>",
  "groups": {"core": true, "commands": true, "file_ops": true, "process": true, "terminal": true, "system": true, "dev_tools": false, "browser": false, "agents": false},
  "group_summary": {"file_ops": {"enabled": 12, "total": 12}, "dev_tools": {"enabled": 0, "total": 3}},
  "identity": {"id": "anonymous", "scopes": ["*"]},
  "policy": {"preset": "default", "revision": "<16 hex chars>", "configured": false},
  "endpoints": {
    "health": {
      "method": "GET",
      "path": "/health",
      "group": "core",
      "summary": "Liveness probe (anonymous).",
      "streaming": false,
      "enabled": true,
      "allowed": true,
      "reason": null,
      "rule": null,
      "scopes": [],
      "limits": {},
      "params": {}
    }
  },
  "warnings": []
}
```

`endpoints` is the per-endpoint state, keyed by endpoint id, and it is the source of truth. It also includes `pty_connect` (`method` `WS`, path `/pty`), which is the WebSocket on port 9001, not an HTTP route on port 9000. `groups` (name to boolean: on when at least one endpoint of the group is on) and `group_summary` (`enabled` and `total` endpoint counts) are derived from it. When the endpoint is off or the caller may not use it, `reason` is `endpoint_disabled` or `missing_scope`, `rule` names the rule that decided (`policy:endpoints.shell`, `default:opt-in:browser`, ...), and `limits` / `params` are omitted. With no policy file and no `ABX_SERVER_POLICY`, `preset` is `default`, `revision` is the hash of an empty policy, and `configured` is `false`. A loaded policy sets `configured` to `true` and fills `preset` / `revision` from that document.

#### `POST /capabilities/check`

Body:

| Field | Required | Meaning |
|-------|----------|---------|
| `endpoint` | yes | Route name, such as `upload` or `shell` |
| `path` | no | One path to test |
| `paths` | no | List of paths |
| `op` | no | `read`, `write`, `delete`, or `exec` |

Does not report whether a path exists. `200`:

```json
{"endpoint": "upload", "allowed": true, "code": null, "reason": null}
```

A refusal sets `allowed` to `false` and fills `code` (`unknown_endpoint`, `endpoint_disabled`, `missing_scope`, or a path-policy code), a human `reason`, and `rule` when a rule decided. A bad body is `400`.

### `commands`

#### `GET /commands`

Visible commands from the command registry (hidden commands are omitted). Commands are registered with `@command` only; see [Named commands](#named-commands). `200`:

```json
{
  "commands": [
    {
      "name": "hello",
      "description": "Say hello.",
      "args": [
        {"name": "name", "type": "string", "required": false, "default": "World", "description": ""}
      ]
    }
  ]
}
```

`type` is `string`, `integer`, `float`, `boolean`, or `string_array`.

#### `POST /commands/{name}`

Body is a JSON object of arguments. `200`:

```json
{"result": "Hello, World!"}
```

`result` is whatever the function returned (must be JSON-serialisable; non-JSON values are stringified by the encoder).

| Status | Body |
|--------|------|
| `400` | Missing required arg, unexpected arg, or a value that cannot be coerced. `type` is `ValueError` or `TypeError` |
| `404` | `Unknown command '<name>'; available: <sorted names>` — the available list includes hidden commands |
| `500` | The function raised. `error` is `str(exc)`, `type` is the exception class name |

Coercion: `integer` via `int` after rejecting JSON booleans (`true`/`false` return `400` before the command runs), `float` via `float`, `boolean` from `true`/`false`/`yes`/`no`/`1`/`0` (case-insensitive). `string_array` accepts only a native JSON array whose elements are all strings; JSON encoded inside a string, mixed arrays, objects and null return `400`. Empty arrays are accepted. String arguments retain `str` conversion. A default is applied only when the field is omitted and the registered default is not `None`.


#### String-array command arguments

```python
@command("echo_args")
def echo_args(args: list[str]) -> list[str]:
    return args
```

`POST /commands/echo_args` with `{"args": ["-i", "literal file.wav", "中文"]}`
returns `{"result": ["-i", "literal file.wav", "中文"]}`. Spaces, Unicode and
shell metacharacters remain literal strings; the SDK does not execute them.
A declared `CommandArg(type="string_array", default='["seed"]', name="args")`
uses JSON text in metadata for compatibility with the existing string-valued
`default` field. The server validates it at registration and copies defaults
for every call. Supplied arrays are also copied before invoking the command.
Use the same annotation with `@sandbox.register` in the declarative client.

```python
result = await server_client.commands.run("echo_args", args=["-i", "literal file.wav"])
```

The extension requires a server containing the string-array implementation;
older servers coerce this annotation to a string. Rebuild the template with
the updated server before exposing this command. Existing scalar commands
keep their conversion behavior. Nested, numeric and arbitrary object arrays
are unsupported. Native CLI `--json-args` sends the same JSON object.

### `file_ops`

Paths are query parameters or body fields as noted. Timestamps are ISO 8601 UTC.

#### `POST /upload`

```json
{"path": "/home/user/note.txt", "content_base64": "<standard base64>"}
```

`200`: `{"path": "<resolved>", "bytes": <int>}`.

| Status | When |
|--------|------|
| `400` | Missing `path` or `content_base64`, or invalid base64 |
| `403` | `path_not_allowed`: the path is outside the allowed directories |
| `413` | Decoded size exceeds `ABX_MAX_UPLOAD_SIZE` (default 104857600). With a policy, the body also has `code: "payload_too_large"` and `limit` |
| `500` | The write failed |

Parent directories are created. With a policy, `allow_extensions` / `deny_extensions` can reject the suffix (`extension_not_allowed`) and `overwrite: false` returns `409` if the file exists.

#### `GET /download?path=`

`200`:

```json
{"path": "<resolved>", "content_base64": "<standard base64>"}
```

`400` missing path, `403` `path_not_allowed`, `404` not a file, `413` larger than the same byte limit, `500` on read errors.

#### `GET /files/list?path=`

| Query | Default | Meaning |
|-------|---------|---------|
| `path` | — | Directory (required) |
| `recursive` | `false` | `true` / `yes` / `1` walks subdirectories |
| `max_entries` | `1000` | Cap, also capped by a policy `max_entries` |

`200`: `{"entries": [{"name", "type", "size", "modified"}]}`. `type` is `directory` or `file` (`follow_symlinks=False`, so a symlink is `file`). Recursive depth stops at 3 (`max_depth` when a policy sets it). `404` if the path is not a directory.

#### `GET /files/stat?path=`

`200` even when the path is missing:

```json
{
  "name": "note.txt",
  "path": "/home/user/note.txt",
  "type": "file",
  "size": 12,
  "permissions": "644",
  "modified": "2026-10-12T00:00:00+00:00",
  "accessed": "2026-10-12T00:00:00+00:00",
  "created": "2026-10-12T00:00:00+00:00",
  "exists": true
}
```

`type` is `file`, `directory`, `symlink`, or `unknown` (with empty times and `exists: false`) when nothing is there. `permissions` is the last three octal digits of `st_mode`.

#### `POST /files/mkdir`

`{"path": "/home/user/out"}`. `200`: `{"path": "<resolved>", "created": true}`. `exist_ok` is true. `400` bad path, `500` on `OSError`.

#### `DELETE /files?path=`

Deletes a file or a directory tree. `200`: `{"path": "<resolved>", "deleted": true}`. `404` if it does not exist. With a policy, deleting the base directory itself, or a tree that contains a denied path, is rejected.

#### `POST /files/move`

`{"source": "/home/user/a", "destination": "/home/user/b"}`. `200`: `{"source": "<resolved>", "destination": "<resolved>"}`. `400` if either field is missing (the message is prefixed `source:` or `destination:`), `404` if the source is missing. The destination parent is created.

#### `POST /files/search`

```json
{"path": "/home/user", "pattern": "*.py", "max_depth": 5, "max_results": 100}
```

`pattern` is a `fnmatch` on the file name. Defaults: depth 5, 100 results, 10 second walk. `200`:

```json
{"results": [{"name": "a.py", "path": "/home/user/a.py"}], "timed_out": false}
```

`404` if `path` is not a directory. Non-integer limits are `400`.

#### `POST /files/upload-stream`

Same body and success shape as `POST /upload` (`path`, `bytes`). The handler still receives one JSON body; it writes the decoded bytes in 64 KiB chunks.

#### `GET /files/download-stream?path=`

Same as `GET /download`, plus `bytes`:

```json
{"path": "<resolved>", "content_base64": "...", "bytes": 12}
```

#### `POST /files/archive`

```json
{"paths": ["/home/user/proj"], "format": "tar.gz"}
```

`format` is `tar.gz` (default) or `zip`. `200`:

```json
{"content_base64": "...", "format": "tar.gz", "bytes": 1200}
```

Limits: 10000 files and 100 MiB of archive bytes (policy `max_files` / `max_bytes` can lower them). Too many files is `400`. An oversized archive is `413`. A missing input path is `404`. Symlinks that point outside the base directory are skipped.

#### `GET /files/watch?path=`

SSE. Query: `recursive` (`false`), `interval` seconds (default `0.5`, clamped to `0.1`–`5`), `timeout` seconds (default `300`, minimum `0.1`, capped by policy `max_duration_seconds`).

| Event | Data |
|-------|------|
| `ready` | `{"path": "<resolved>"}` |
| `change` | `{"type": "created"\|"modified"\|"deleted", "path": "...", "is_dir": false}` |
| `end` | `{"reason": "timeout"}` |

`400` for a bad interval or timeout, `404` if `path` is not a directory. The walk is polled; it is not an inotify stream. At most 5000 entries are tracked.

### `process`

`cwd`, `env`, and `timeout` on the shell and process-start bodies are optional. `cwd` must be a string and an existing directory inside the allowed directories (`403` `path_not_allowed` otherwise). `env` must be an object of strings. `timeout` defaults to 300 seconds; a non-positive or non-numeric value is replaced with 300. A policy can lower the timeout (`timeout_seconds`) and cap output (`max_output_bytes`, which sets `"truncated": true` on `/shell`).

#### `POST /shell`

```json
{"command": "ls -la /tmp", "cwd": "/tmp", "env": {"A": "1"}, "timeout": 30}
```

`200`:

```json
{"stdout": "...", "stderr": "", "exit_code": 0}
```

`exit_code` is the process return code, including non-zero. `400` if `command` is missing or `cwd`/`env` is the wrong type. `shlex` failure is `500`. A timeout is `500` `{"error": "Command timed out after <n>s", "type": "TimeoutError"}`.

#### `POST /shell/stream`

Same body. SSE lines, one per output line (trailing newline stripped):

| Event | Data |
|-------|------|
| `stdout` | `{"data": "<line>"}` |
| `stderr` | `{"data": "<line>"}` |
| `error` | `{"error": "timeout"}` or `{"error": "output_limit"}` or `{"error": "<message>"}` |
| `exit` | `{"exit_code": 0}` |

`shlex` failure here is `400`, not `500`.

#### `POST /process/start`

```json
{"command": "sleep 30", "cwd": "/tmp", "env": {}, "capture_output": false, "stdin": false}
```

`200`: `{"pid": 123, "command": "sleep 30"}`. The server keeps at most 100 live processes (`429` `ResourceError` when full; already-exited rows are dropped first). `capture_output: true` stores stdout and stderr (default cap 1 MiB; older chunks are dropped). `stdin: true` leaves stdin open for `/process/{pid}/stdin`. `400` bad command or `shlex` error, `500` if `Popen` fails.

#### `GET /process/list`

`200`: `{"processes": [{"pid", "command", "state", "started_at"}]}`. `state` is `running` (exited processes are removed by this call). `started_at` is a Unix timestamp (`time.time()`).

#### `GET /process/{pid}`

`200`:

```json
{"pid": 123, "command": "sleep 30", "state": "running", "started_at": 1700000000.0, "exit_code": null}
```

`state` is `running` or `exited`. `exit_code` is `null` until it exits. `400` if `pid` is not an integer, `404` if this server did not start that pid.

#### `POST /process/{pid}/signal`

`{"signal": 15}`. Allowed signals: `2` (SIGINT), `9` (SIGKILL), `15` (SIGTERM), `18` (SIGCONT), `20` (SIGTSTP). `200`: `{"pid": 123, "signal": 15}`. Other signals are `400`. Pid 1 and the server's own pid are `403`. Unknown pid is `404`.

#### `POST /process/{pid}/stdin`

For a process started with `stdin: true`.

```json
{"data": "hello\n", "eof": false}
```

`data` is UTF-8 text. `data_base64` is an alternative. `eof: true` closes stdin. At least one of `data`, `data_base64`, or `eof` is required. `200`: `{"pid": 123, "written": 6, "closed": false}`. `409` if stdin was not enabled or is already closed. `400` for bad base64 or a non-string `data`.

#### `GET /process/{pid}/output?since=0&wait=0`

Only when `capture_output` was true (`409` otherwise). `since` is a sequence number (default `0`). `wait` seconds (default `0`, max `30`) blocks until new data or the process ends. `200`:

```json
{
  "pid": 123,
  "events": [{"seq": 0, "stream": "stdout", "data": "hi"}],
  "next": 1,
  "state": "running",
  "exit_code": null,
  "dropped": false
}
```

`dropped: true` means the capture buffer discarded older events.

### `terminal`

The HTTP routes manage sessions. Keystrokes go over a WebSocket on `ABX_PTY_PORT` (default `9001`), started only while this group is enabled. Shells allowed at create time: `/bin/bash`, `/bin/sh`, `/bin/zsh`, `/usr/bin/bash`, `/usr/bin/zsh`. At most 10 sessions. A session idle for 1800 seconds is reaped when the manager next creates or lists sessions.

#### `POST /pty/sessions`

```json
{"shell": "/bin/bash", "cols": 80, "rows": 24, "env": {"LANG": "C.UTF-8"}}
```

`200`:

```json
{"session_id": "<12 hex chars>", "ws_url": "ws://localhost:9001/pty?session_id=<id>", "pid": 123}
```

`ws_url` is built with `localhost` and, when `ABX_SERVER_TOKEN` is set and the server is not using per-identity tokens, `&token=<url-encoded token>`. From outside the sandbox, open the WebSocket on `sandbox.network.get_url(9001)` at path `/pty` with the same query. `429` when the session limit is hit. `400` for a shell outside the list or a non-integer size. `LD_PRELOAD`, `LD_LIBRARY_PATH`, and `DYLD_INSERT_LIBRARIES` are stripped from `env`.

#### `GET /pty/sessions`

`200`: `{"sessions": [{"id", "pid", "created_at", "cols", "rows", "alive"}]}`.

#### `GET /pty/sessions/{id}`

`200`: one session object (`id`, `pid`, `created_at`, `cols`, `rows`, `alive`). `404` if it is gone.

#### `POST /pty/sessions/{id}/resize`

`{"cols": 120, "rows": 40}`. Both are required integers from 1 to 1000. `200` returns the session object.

#### `DELETE /pty/sessions/{id}`

`200`: `{"status": "closed", "session_id": "<id>"}`. `404` if it does not exist.

#### WebSocket `/pty?session_id=`

Client → server:

```json
{"type": "input", "data": "ls\n"}
{"type": "resize", "cols": 120, "rows": 40}
{"type": "signal", "signal": "SIGINT"}
```

`signal` accepts `SIGINT`, `SIGTERM`, `SIGKILL`, `SIGHUP`, `SIGQUIT`.

Server → client:

```json
{"type": "output", "data": "..."}
{"type": "event", "event": "started", "session_id": "<id>", "pid": 123}
{"type": "event", "event": "exited", "session_id": "<id>"}
```

Auth failure closes the socket with code `4001`. A disabled terminal closes with `4003`.

### `system`

#### `GET /system/info`

`200`:

```json
{
  "os": "Linux",
  "arch": "x86_64",
  "cpu_count": 2,
  "memory_total_mb": 2048,
  "memory_available_mb": 1024,
  "disk_total_gb": 20.0,
  "disk_free_gb": 10.0,
  "python_version": "3.11.0",
  "hostname": "sandbox"
}
```

Memory comes from `/proc/meminfo` when present. Disk is `shutil.disk_usage("/")`.

#### `GET /system/metrics`

`200`: `cpu_load_1m`, `cpu_load_5m`, `cpu_load_15m`, `memory_used_mb`, `memory_total_mb`, `memory_percent`, `disk_used_gb`, `disk_total_gb`, `disk_percent`, `uptime_seconds`. Uptime is seconds since the server process imported this module.

#### `GET /env`

`200`: `{"variables": {"HOME": "/home/user"}}`. Names containing `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, or `CREDENTIAL` (any case) are omitted. Query `filter` is a comma-separated allow-list of names. A policy can add `allow_vars` / `deny_vars` globs.

#### `POST /env`

`{"vars": {"LANG": "C.UTF-8"}}`. `200`: `{"updated": ["LANG"]}`. `403` if any key is `PATH`, `HOME`, `USER`, `SHELL`, or starts with `ABX_` (compared in uppercase). `400` if `vars` is not an object. Values are stored with `str()`.

#### `GET /ports`

`200`: `{"listening": [{"port": 9000, "protocol": "tcp", "address": "0.0.0.0", "pid": null}]}`. Read from `/proc/net/tcp` and `/proc/net/tcp6` (listen state only). If both are empty, the handler runs `ss -tlnp`. `pid` is filled only by the `ss` fallback.

#### `GET /packages?manager=pip`

`manager` is `pip` (default) or `npm`. `pip` runs `python -m pip list --format json`. `npm` runs `npm list --json --depth=0`. `200`: `{"manager": "pip", "packages": [{"name": "pip", "version": "24.0"}]}`. An unknown manager is `400`. A missing binary returns an empty `packages` list. Timeout is 10 seconds (`500` `TimeoutError`).

### `dev_tools` (off until enabled)

#### `POST /code/run`

```json
{"code": "print('hello')", "language": "python", "timeout": 30}
```

`language` is `python` (`python3 -c`), `node` (`node -e`), or `bash` (`bash -c`). Default timeout 30 seconds, maximum 300. `200`:

```json
{
  "stdout": "hello\n",
  "stderr": "",
  "exit_code": 0,
  "language": "python",
  "execution_time_ms": 12.34,
  "_security_note": "Security relies on container isolation, not application-level restrictions"
}
```

`408` on timeout. `500` if the runtime binary is missing. A policy `languages` list can reject a language.

This `/code/run` is an opt-in application HTTP subprocess route, separate from the provider context-interpreter contract. Its existence does not claim persistent contexts or realtime streaming. A missing route never silently selects a different execution path.

#### `GET /git/status?path=.`

`200`: `{"branch": "main", "clean": true, "files": [{"path": "a.py", "status": "modified"}]}`. `status` is `modified`, `added`, `deleted`, `renamed`, `untracked`, `copied`, or `unmerged`. `400` `GitError` when git fails (not a repository). `500` if `git` is not installed. `408` on a 30 second timeout. `path` must stay inside the allowed directories (`403` `path_not_allowed`).

#### `GET /git/diff`

Query: `path` (default `.`), `staged` (`true`/`yes`/`1` adds `--staged`), `file` (optional pathspec). `200`:

```json
{"diff": "<unified diff>", "stats": {"files_changed": 1, "insertions": 2, "deletions": 0}}
```

Diff text is cut at 1 MiB with a truncation line. Same git errors as status.

### `browser` (off until enabled)

All of these need Playwright. If `import playwright` fails the handler returns `503` `RuntimeError` with the install hint `pip install playwright && playwright install chromium`. One shared headless Chromium page is created on first use. There is no per-request browser id.

| Route | Body or query | `200` body |
|-------|----------------|------------|
| `POST /browser/navigate` | `url` (required), `wait_until` default `networkidle`, `timeout` ms default `30000` | `url`, `title`, `status` (HTTP status of the navigation, or `0`) |
| `POST /browser/screenshot` | `selector` optional, `full_page` default `true`, `format` `png` or `jpeg` | `image_base64`, `width`, `height` |
| `GET /browser/content` | `type` query `html` (default) or `text` | `content`, `url`, `title` |
| `POST /browser/click` | `selector` (required), `timeout` ms default `5000` | `clicked: true`, `selector` |
| `POST /browser/type` | `selector`, `text` (required), `delay` ms default `50`, `clear` default `false` | `typed: true`, `selector`, `text` |
| `POST /browser/evaluate` | `script` (required), `timeout` ms default `10000` | `result` (the JSON value `page.evaluate` returned) |
| `POST /browser/pdf` | `format` default `A4`, `landscape` default `false` | `pdf_base64`, `pages` |
| `GET /browser/console` | none | `logs`: `[{type, text, timestamp}]`, then the buffer is cleared (max 1000) |

`404` from screenshot when `selector` matches nothing. A policy may restrict `url` on navigate (`url_allow`, `url_deny`, `block_private_networks`). Redirects after the first URL are not filtered.

### `agents` (off until enabled)

Turn the group on with `ABX_SERVER_ENABLED_GROUPS=agents`, `groups: [agents]` in `server:`, or `default_table().enable_group(CapabilityGroup.AGENTS)` before `serve()`. All 70 routes are implemented. Two runtimes have a local backend: Codex CLI (`codex`) and Qwen Code (`qwen-code`, also `qwen` and `qwencode`). `claude-code`, `cursor` and `command` are declared adapters without a local backend. `GET /v1/agents/runtimes` lists every declared runtime with `implemented` and `installed`. Selecting a runtime that is not implemented is `404` `not_found_error` (`agents.not_implemented_locally`) with `x-should-retry: false`, and the body points to `GET /v1/agents/runtimes`. When the body and `agents.default` (`ABX_AGENTS_DEFAULT`) do not name an adapter, create calls use `codex`. Each Agents route can be enabled on its own. Endpoint ids are in [Fine-grained capabilities](fine-grained-capabilities.md). The default scope is `agents:use`. The full route table is in the [Agents API reference](../reference/agents-api.md).

Every response carries `X-Agent-Sandbox-Local: 1` and every object an `x_agent_sandbox` label (`local`, `compute`, `differences`). A field the server cannot honor is `400` with `param`, never accepted and ignored. Objects belong to the caller; a foreign id answers like an unknown id.

| Route | Behavior |
|------|------|
| `POST /v1/agents/sessions` | Creates a session from an inline `agent` or an `agent_id`, optional `environment` (`{"id": "env_..."}`) and `vault_ids`. A string `input` queues the first turn. |
| `GET /v1/agents/sessions` | Lists sessions (`agent_id` filter). |
| `GET`, `POST`, `DELETE /v1/agents/sessions/{id}` | One session. `POST` updates `metadata` only. |
| `POST /v1/agents/sessions/{id}/events` | Queues a turn. **HTTP 202, empty body.** The same `Idempotency-Key` replays that 202. |
| `GET /v1/agents/sessions/{id}/events` | SSE (`Accept: text/event-stream`) of mapped session events. |
| `GET .../items`, `.../turns`, `.../turns/{turn_id}`, `.../turns/{turn_id}/items` | Items and turns. |
| `GET .../artifacts`, `GET` and `DELETE .../artifacts/{id}`, `GET .../artifacts/{id}/content` | Immutable copies of the paths the CLI reported. Delete removes the copy only. |
| `GET .../traces` | Empty unless `ABX_AGENTS_TRACES=1` (timing-only spans). |
| `GET .../subagents`, `.../subagents/{id}`, `/items`, `/turns`, `/turns/{turn_id}`, `/turns/{turn_id}/items` | Only ids the CLI emitted. |
| `POST`, `GET /v1/agents`, `GET`, `POST`, `DELETE /v1/agents/{agent_id}` | Agent definitions. Only `mcp` tools. |
| `POST`, `GET /v1/agents/environments`, `GET /v1/agents/environments/{id}` | Directory bindings. |
| `POST`, `GET /v1/agents/environments/{id}/files` | Write (never overwrite) and list files under the workspace. |
| `/v1/agents/environments/templates[...]` | Reduced templates: `{name, env, inline files}`. |
| `POST /v1/files` | Local `user_data` blobs so `file_id` works (JSON body with base64 `data`). |
| `/v1/vaults[...]`, `/v1/vaults/{id}/credentials[...]` | Memory-only vaults and write-only `static_bearer` / `mcp_oauth` credentials. |
| `POST /v1/responses`, `GET`, `DELETE /v1/responses/{id}`, `POST .../cancel`, `GET .../input_items`, `POST /v1/responses/compact` | A labeled one-shot CLI turn. |
| `GET /v1/models`, `GET /v1/models/{id}` | Definitions and the implemented runtimes. |
| `/v1/webhook_endpoints[...]`, `GET /v1/webhook_event_types` | Local signed webhook endpoints. |
| `GET /v1/agents/runtimes` | Every declared runtime with `implemented` and `installed`. |

Four routes exist to refuse with a typed `404` `not_found_error` (`x-should-retry: false`) because the server has no such capability: `POST /v1/responses/input_tokens`, `DELETE /v1/models/{id}`, and executor registration and channel (`agents_cannot_*`). They are declared, counted and tested like every other route.

The CLIs are not installed until a session uses them. See [Hosted agents](hosted-agents.md) for every refusal, environment variable and difference code.

---

## Custom commands and custom routes

### Named commands

A named command has one mechanism: register a function with `@command`. `GET /commands` lists it and `POST /commands/{name}` runs it. The client's `@sandbox.register` decorator ends in the same registry.

```python
from agent_sandbox.server import command, start

@command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"

@command(hidden=True)
def _debug_info() -> dict:
    return {"ok": True}

start(9000)
```

`GET /commands` lists `hello` and not `_debug_info`. `POST /commands/hello` with `{"name": "Ada"}` returns `{"result": "Hello, Ada!"}`. `POST /commands/_debug_info` with `{}` still runs. The name defaults to the function name. Argument types come from annotations: `int` → `integer`, `float` → `float`, `bool` → `boolean`, `list[str]` (also `typing.List[str]`) → `string_array`, anything else → `string`. A parameter with no default is `required: true` and `default: null`. `description` on each arg stays `""` unless you pass an explicit `args` list of `CommandArg`. `scopes=(...)` requires those scopes from the caller; a caller without them neither sees the command in `GET /commands` nor can run it. `hidden=True` omits the command from `GET /commands`. Raise to return `500`. The registry is frozen when the server starts, so register at import time.

Tests that need isolation can create a private `CommandRegistry()` and pass it as `SandboxServer(registry=...)`. Production templates use `@command`.

### Custom routes with `@table.route`

```python
from agent_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request: object) -> ServerResponse:
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})
```

The dispatcher calls `GET`, `POST`, and `DELETE` only. The handler receives a request with:

| Attribute | Contents |
|-----------|----------|
| `method` | `GET`, `POST`, or `DELETE` |
| `path` | Path with the trailing slash removed |
| `query` | `{name: [values]}` from the query string |
| `headers` | Header name → single value |
| `body` | Parsed JSON object, or `{}` when the method has no body |
| `path_params` | `{param: value}` from `{param}` segments (one path segment, no slash) |
| `context` | `registry` and `route_table` |

Return `ServerResponse.ok({...})` (`200` and that object as the body) or `ServerResponse.error(status, message)` (`{"error", "type"}`, `type` default `ValueError`).

`auth_required=False` leaves the route open when `ABX_SERVER_TOKEN` is set. The default is to require the token. `streaming=True` means return `SSEResponse(event_iterator=...)`; the iterator yields strings `event: <name>\ndata: <json>\n\n`.

The route does not appear in `GET /commands`. It appears in `GET /capabilities` under `endpoints`, keyed by the route `name` (default `"GET /hello/{name}"`), and counts in its group's `group_summary`. It is served only while its endpoint is enabled. A disabled endpoint is the same `404` as a built-in route.

---

## curl

These curl examples target a direct local server. For a remote sandbox, resolve the
application URL and any gateway headers through its provider. Keep the application
token in `Authorization: Bearer`; do not replace a provider-required `X-Access-Token`
with the application token, and do not copy control-plane API keys into requests.
A gateway header is required only when that provider's resolved endpoint requires it.
For an anonymous server, omit the application Authorization header.

Set the base URL and, when the server was started with a token, the token. Neither value belongs in the template image.

```bash
export ABX_TEMPLATE_URL="http://127.0.0.1:9000"
AUTH=()
if [ -n "${ABX_SERVER_TOKEN:-}" ]; then
  AUTH=(-H "Authorization: Bearer $ABX_SERVER_TOKEN")
fi
```

Health (open even when a token is set):

```bash
curl --fail-with-body -sS "$ABX_TEMPLATE_URL/health"
```

List commands (send the header whenever `ABX_SERVER_TOKEN` is set):

```bash
curl --fail-with-body -sS "${AUTH[@]}" "$ABX_TEMPLATE_URL/commands"
```

Run a command registered as `hello`:

```bash
curl --fail-with-body -sS "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada"}' \
  "$ABX_TEMPLATE_URL/commands/hello"
```

Upload and download. The path must stay under `ABX_SERVER_BASE_DIR` (default `/home/user`). `file_ops` must be enabled, which it is unless a `server:` policy or `commands.py` turned it off.

```bash
B64=$(printf 'hello' | base64)
curl --fail-with-body -sS "${AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d "{\"path\":\"/home/user/note.txt\",\"content_base64\":\"$B64\"}" \
  "$ABX_TEMPLATE_URL/upload"

curl --fail-with-body -sS "${AUTH[@]}" \
  "$ABX_TEMPLATE_URL/download?path=/home/user/note.txt"
```
