# Server HTTP API Reference

The wire contract of the in-sandbox server (`agent_sandbox.server`, port 9000; PTY WebSocket on 9001). The route-by-route behavior is in the [template server HTTP API](../guide/template-server-api.md). The Agents routes are in the [Agents API reference](agents-api.md). Design background is in [Server API Design](../design/server-api.md).

## One id per endpoint

Every route is one endpoint with one id (`files_download`, `shell`, `agents_sessions_create`). The same id is used by the policy, the audit log, `GET /capabilities`, and the client. There are 118 endpoints: `core` 3, `commands` 2, `file_ops` 12, `process` 8, `terminal` 6 (including the WebSocket `pty_connect`), `system` 6, `dev_tools` 3, `browser` 8, `agents` 70. The table is `agent_sandbox.server.endpoints.ENDPOINTS`. Nothing is served that is not in it, and there is no `/ops` or RPC route.

## One pipeline

Every request goes through the same steps, in this order:

1. Match method and path to an endpoint. No match is `404` `Not found: <path>`.
2. Authenticate: `Authorization: Bearer <token>` or `X-Access-Token`. Missing or wrong is `401` `unauthorized`. Two different `X-Access-Token` values are `400` `ambiguous_credentials`.
3. Admit through the policy engine: the endpoint must be on (`404` `endpoint_disabled`, with `rule`), the caller must hold the scopes (`403` `missing_scope`), and the rate and concurrency limits must have room (`429`).
4. A repeated query parameter is `400` `duplicate_parameter`.
5. The body limit (10 MiB) is checked before the body is read: `413` `payload_too_large`.
6. The handler runs. Path, command, process, environment, and URL guards answer here.
7. The audit entry is written (`audit: off|deny|all`).

`GET /health` is the only route that skips step 2.

## Error body

```json
{"error": "<message>", "type": "<ExceptionName>", "code": "<machine code>", "endpoint": "<endpoint id>"}
```

`code` and `endpoint` are present on policy and guard denials. A disabled endpoint also has `rule`. `/v1/` Agents routes use the OpenAI envelope `{"error": {"message", "type", "param", "code"}}`.

| `code` | Status | Meaning |
|---|---|---|
| `unauthorized` | 401 | Missing or wrong token |
| `ambiguous_credentials` | 400 | Two different credential values in one request |
| `endpoint_disabled` | 404 | The endpoint is off. `rule` names the layer, for example `policy:endpoints.shell`, `preset:read-only`, `code:enable_group:file_ops`, `env:ABX_SERVER_ENABLED_GROUPS:agents`, `default:opt-in:browser` |
| `missing_scope` | 403 | The caller lacks a scope the endpoint (or command) needs |
| `scope_required` | 403 | A command guard has no allow-list entry that could admit the call |
| `path_not_allowed` | 403 | The path is outside the allowed directories (includes shell `cwd`) |
| `path_denied` | 403 | The path matches a `paths.deny` pattern |
| `read_only` | 403 | The endpoint's `paths.read_only` rejects writes and deletes |
| `symlink_denied` | 403 | `paths.symlinks` refuses a symlink |
| `invalid_path` | 400 | Missing, NUL byte, or too long |
| `command_not_allowed` | 403 | `allow_commands` / `deny_commands` refuse the command |
| `command_invalid`, `process_invalid` | 400 | Empty or malformed executable |
| `process_denied` | 403 | A process guard refuses the program |
| `env_var_denied`, `env_var_not_allowed` | 403 | An environment variable is refused |
| `env_invalid`, `url_invalid` | 400 | Malformed environment map or URL |
| `url_denied` | 403 | `url_allow` / `url_deny` / private-network rules refuse the URL |
| `language_not_allowed` | 403 | `code_run` language not in `params.languages` |
| `extension_not_allowed` | 403 | Upload extension refused |
| `file_exists` | 409 | `overwrite: false` and the file exists |
| `payload_too_large` | 413 | Body or file over the limit |
| `rate_limited`, `concurrency_limited` | 429 | Limit exhausted. `Retry-After` is set |
| `duplicate_parameter` | 400 | A query parameter was repeated |

## Discovery

`GET /capabilities` returns the state of every endpoint for the caller (`enabled`, `allowed`, `reason`, `rule`, `scopes`, limits) and the derived `groups` and `group_summary`. `POST /capabilities/check` answers whether one endpoint (and optionally one path) would be allowed, without running it. Both are described in the [template server HTTP API](../guide/template-server-api.md#get-capabilities).

## Switching endpoints

One layer decides: the endpoint rule. A group name is an alias for its endpoint ids. See [Fine-grained capabilities](../guide/fine-grained-capabilities.md). The only group environment variable is `ABX_SERVER_ENABLED_GROUPS`.
