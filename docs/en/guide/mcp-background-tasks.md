# Reconnectable Python MCP tasks

The Python MCP server provides `start_task`, `get_task`, and `cancel_task` for
background shell work in an existing Linux sandbox with `python3`, `/proc` and
process-group support. Both Python MCP transports use these handlers. The Node.js
CLI MCP server has a separate implementation; these three tools are Python-only.

## Start, reconnect and finish

Create a sandbox first, then explicitly start background work:

```json
{"name":"create_sandbox","arguments":{"template":"base","timeout":600}}
{"name":"start_task","arguments":{"command":"printf BEFORE; sleep 10; printf AFTER","timeout":120}}
```

Save both `sandbox_id` and the 32-character lowercase hexadecimal `task_id` from
the result. A successful submission returns the observed task state; a short task
may already have finished. A submission whose response is uncertain returns
`state: "unknown"` with that same handle, and may include an error. Inspect it or destroy its
sandbox; do not blindly resubmit work that may already have started.

**Starting a task explicitly retains that sandbox on MCP disconnect.** Other
sandboxes keep their normal session cleanup. No task tool extends platform TTL;
the existing sandbox deadline can stop a task before its requested timeout.
Subsequent ordinary execution/file tools keep their existing renewal policy.
Retention applies to the entire sandbox, including any other work sharing it.
Use a dedicated sandbox when that distinction matters.

A fresh MCP session or Python MCP process, with the same authorized provider and
region configuration, can query the saved handle:

```json
{"name":"get_task","arguments":{"sandbox_id":"REPLACE_ME","task_id":"0123456789abcdef0123456789abcdef","stdout_offset":0,"stderr_offset":0,"limit":16384}}
```

The result includes `state`, `exit_code`, `started_at`, `finished_at`, `stdout`,
`stderr`, each stream's next byte offset and saved byte size, and
`stdout_truncated` / `stderr_truncated`. States are `running`, `succeeded`,
`failed`, `cancelled`, `timed_out`, or `unknown`. `failed` means a nonzero exit or
supervisor failure; a missing supervisor is `unknown`, never fabricated success.
Progress reflects output/status, not a percentage. Times are Unix seconds.

Pass each returned offset into the next read. `limit` is bytes per stream,
default 16384, maximum 65536. Offset boundaries can split UTF-8 code points;
invalid fragments decode with replacement characters. Read the same page again
to replay it. A task retains at most 1 MiB per stream and keeps draining excess
output to avoid blocking the command; truncation is explicit at completion.
At most 128 task directories are accepted per sandbox OS user.

To cancel and then inspect its recorded outcome:

```json
{"name":"cancel_task","arguments":{"sandbox_id":"REPLACE_ME","task_id":"0123456789abcdef0123456789abcdef"}}
```

Cancellation requests TERM, then KILL for the task-owned process group. Completion,
nonzero exit and timeout also clean same-group descendants. Cancellation waits up
to three seconds for a confirmed terminal state; `running` or `unknown` does not
claim cancellation succeeded. Repeating cancellation on a terminal task returns its
saved outcome and never signals an arbitrary caller-supplied PID. A process that
creates a separate session/group escapes this ownership boundary; destroying the
sandbox is the complete cleanup operation.

After retrieving results, explicitly destroy the retained resource:

```json
{"name":"kill_sandbox","arguments":{"sandbox_id":"REPLACE_ME"}}
```

## Inputs and boundaries

| Tool | Arguments |
|---|---|
| `start_task` | `command` required, up to 65536 characters; optional existing `sandbox_id`, `cwd`, and task `timeout` (1–3600 seconds, default 300) |
| `get_task` | Required `sandbox_id`, `task_id`; optional byte offsets (0–1048576) and `limit` (1–65536) |
| `cancel_task` | The same handle and pagination arguments as `get_task` |

An omitted `sandbox_id` at start requires an existing session default. It never
creates one implicitly. Encoded JSON/quoting expansion is capped at 96 KiB before
any remote connection. Unexpected fields and malformed task IDs are rejected.
Task query/cancel connections are closed after use and never become session
shutdown ownership; they use the SDK's normal authorized provider connect path.

Logs and atomic status files live in a private OS-user directory inside the
sandbox. They survive MCP session/process replacement while that sandbox lives;
they do not survive its destruction, expiry, filesystem loss or recreation. No
host-local database, hosted task service, automatic retries or sandbox replacement
is provided. A process crash before a status record is written can leave an
unconfirmed handle; destroy the sandbox if it cannot be inspected.

Output is user data. Before writing logs, the supervisor masks exact known secret
values from sandbox environment variable names containing KEY, TOKEN, SECRET or
PASSWORD, including values split across pipe reads. The host additionally masks
its configured values on each returned page. This is not general secret detection:
encoded values, partial values and host-only secrets split across pages may remain.
Commands, logs and files share the sandbox OS identity; task handles are not a
multi-tenant authorization boundary. Do not put secrets into command text or
print them. Use separately authorized sandboxes for separate trust domains.

The real Express verification records native Start/Connect replay limitations and
start → disconnect → reconnect → saved exit/logs → cancellation → cleanup. Other
providers, Windows and hosted multi-user deployment are not accepted by that run.
