# Readiness of the providers that have no live backend yet

> Status: 2026-10-14. OpenSandbox and Alibaba Cloud Express already have live calls. This page reviews the other three: CubeSandbox, E2B, and the container edition. Their source is `awesome-providers/`. Install is `awesome-providers/docs/en/install.md`. The comparison is the current upstream SDK and OpenAPI, not the fake TCP server in the unit tests. The same verdict is `awesome-providers/docs/en/catalog.md`.

All three catalog adapters reuse the E2B-shaped `SandboxProtocol`. The control-plane calls (`POST /sandboxes` with `templateID`, `X-API-Key`, `DELETE`, `POST /timeout`, `POST /pause`) match the upstream docs and can be sent as soon as a backend exists. The rows below are the mismatches that would have failed on that backend, and the ones already changed.

## Verdict

| Provider | Logically usable | First check once a backend exists |
|---|---|---|
| E2B | Yes. Create, exec, files, ports, and pause use the HTTP shape in the current OpenAPI | Set `ABX_E2B_API_KEY`. Template `base` |
| CubeSandbox | Yes for create, commands, files, pause, and directory watch. `run_code` posts to Jupyter `:49999/execute` | API on `:3000`, `ABX_CUBESANDBOX_DOMAIN=cube.app`, and a template id that exists on that cluster. Do not assume a template named `base` |
| Container edition | Yes for the native protocol. The private data-plane URL is filled on create, connect, and get | `ABX_ALICLOUD_CONTAINER_DOMAIN` and `ABX_ALICLOUD_CONTAINER_API_KEY`. The documented sample template is `code-interpreter` |

None of them reads `E2B_API_KEY`. E2B and the container edition refuse before any request when their own key is missing.

## Mismatches already aligned

Unit tests lock the new behavior.

| Issue | What used to happen | Now |
|---|---|---|
| E2B default domain `e2b.dev` | The data plane became `49983-{id}.e2b.dev`. The current SDK's domain is `e2b.app` and the API is `https://api.e2b.app` | Defaults are `api.e2b.app` / `e2b.app`. An older account sets the env vars back to `e2b.dev` |
| Cube default domain `localhost` | envd dialed `49983-{id}.localhost`, which never reaches CubeProxy. The upstream default is `cube.app` | Default `cube.app` |
| `connect` sent only GET | Cube and current E2B resume a paused sandbox with `POST /sandboxes/{id}/connect` | All three try POST, then GET on 4xx |
| Cube process and file calls omitted the user | The upstream SDK says envd rejects an empty user and sends `root` | `user`, `username`, and `Authorization: Basic` are `root` |
| Cube omits `envdAccessToken` | The client raised `TokenExpiredError` before any request | A missing token omits `X-Access-Token` and the request continues |
| Cube data plane used https | That dials port 443. CubeProxy HTTP is port 80; `49983` in the hostname is only a route prefix | The URL is `http://49983-{id}.{domain}`. A `domain` field on the create response wins over the configured suffix |
| Cube `resume` had no JSON body | Axum returns 422 when the body is missing | `POST /resume` sends `{}` |
| Cube `run_code` called the envd CodeInterpreter | Upstream is `POST /execute` on Jupyter port 49999 | That URL is used, and the ndjson body is read |
| Process Start body | Cube envd treats the first 5 bytes of raw JSON as a frame header | Cube envd requests add the 5-byte frame and `Connect-Protocol-Version: 1`. Express still sends raw JSON |
| `state: pausing` | Validation failed | `SandboxStatus` accepts `pausing` |
| Cube directory watch was E8004 | The upstream SDK has `files.watch_dir` on the same envd | `files.watch` is declared |

## Still needs a live look

These are gaps against the upstream API, not guesses. When a backend is available, check them in this order.

| Provider | Call | What to expect |
|---|---|---|
| Cube | `run_code` twice, the second reading a variable from the first | Depends on the Jupyter kernel keeping state outside one `/execute`. The request now goes to port 49999 |
| Cube | Off the node | Set `ABX_CUBESANDBOX_PROXY=host:80`. TCP dials the proxy and the Host header stays `49983-{id}.cube.app` |
| Cube | `Sandbox.list(status=...)` | `GET /sandboxes` ignores `status` and `offset`. A filtered list still needs `GET /v2/sandboxes` |
| E2B | `get_terminal` | Undeclared, `E8004`. Public envd starts a PTY with `process.Process/Start` and a `pty` field, not a `/terminal` WebSocket |
| E2B | `Sandbox.connect` on a paused sandbox | Should hit `POST /connect` and resume. `POST /resume` is deprecated in the OpenAPI; `resume()` after `pause()` still uses that older path |
| Container, native | Create response omits `envdUrl` | The SDK fills `https://49983-{id}.{domain}`. Commands hit the wrong host if that cluster's envd port is not 49983 |
| Container, private | Create | The data plane is `https://{domain}/kruise/{id}/49983`. A port URL is `https://{domain}/kruise/{id}/{port}` |
| Container | `pause` | Undeclared, so `E8004`. Do not reuse Express pause behavior to probe it |

## How to run once the resources exist

```bash
cd python-sdk/e2e
python -m pytest test_08_providers.py -s -ra
```

Cube needs `127.0.0.1:3000` or `ABX_CUBESANDBOX_BASE_URL`. E2B needs `ABX_E2B_API_KEY`. The container edition needs `ABX_ALICLOUD_CONTAINER_DOMAIN` and `ABX_ALICLOUD_CONTAINER_API_KEY`. A missing piece skips that test and does not send another provider's key.
