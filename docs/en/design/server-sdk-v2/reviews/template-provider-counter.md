# Opposing review: a template's provider is not the server SDK's business

> Reviewer: opposing design. Read-only. Sources: `cli/src/agent/template_guide.ts`, `cli/src/agent/codegen.ts` (`validateTemplateWorkspace`), `python-sdk/docs/en/design/base-image-and-server-sdk.md`, and every `register` in `python-sdk/server-sdk/src/easy_sandbox/server/routes*.py` plus the dispatcher in `app.py` and the group defaults in `router.py`.
>
> Verdict: reject any design that puts an Alibaba registry URL, `ENTRYPOINT`, user, or reserved platform port into `easy_sandbox.server` or the client SDK. Generated templates default to a base image because the **CLI** default provider is `alicloud-express`, not because the server knows who is hosting the container.

## 1. What is the server SDK contract (stable on every provider)

A generated template is usable only if something inside the image serves this route table. That table is the public API of a template. The Dockerfile is not.

`SandboxServer` imports `routes`, `routes_browser`, `routes_devtools`, `routes_files`, `routes_process`, `routes_pty`, and `routes_system` (`app.py`). Those modules register on the process-wide `default_table()`. `commands.py` does not reimplement them; it calls `serve(port=9000)` (`template_guide.ts` `SERVER_PORT`).

Auth, from `app.py` `_check_auth` and `router.py` `RouteInfo.auth_required` (default `True`):

- Credential is env `EBX_SERVER_TOKEN`. Unset, and no policy engine: every route is open.
- Set, legacy dispatcher (`policy_engine is None`): header `X-Access-Token`, compared with `hmac.compare_digest`. `Authorization: Bearer` is accepted only when `route.group == CapabilityGroup.AGENTS`. No `routes*.py` module registers an AGENTS route, so Bearer does nothing for the table below.
- Policy dispatcher (`_dispatch_policy`): `auth_required` routes take `X-Access-Token` or `Authorization: Bearer` (`runtime.py` `authenticate`). `auth_required=False` skips that and becomes anonymous.
- The only registration with `auth_required=False` is `GET /health`. `GET /capabilities` and `POST /capabilities/check` set `auth_required=True`. `template_guide.ts` (the sentence under "鉴权") is wrong: it tells the generator that `/capabilities` is exempt. Callers who trust the guide will omit the token and get 401.

Group gate (`router.py`): `CORE` cannot be disabled. `_DEFAULT_DISABLED` is `DEV_TOOLS`, `BROWSER`, `AGENTS`. So `COMMANDS`, `FILE_OPS`, `PROCESS`, `TERMINAL`, and `SYSTEM` are **on** until `disable_group` or `EBX_SERVER_DISABLED_GROUPS`. Opt-in groups turn on via `enable_group` or `EBX_SERVER_ENABLED_GROUPS` (`app.py`). A disabled group is HTTP 404 `Built-in route '<name>' is disabled`, not 401.

`template.yaml` tokens `shell | files | code | terminal | ports` (`cli/src/models/template.ts` `STANDARD_CAPABILITIES`) do **not** enable routes. `code` is not `DEV_TOOLS`. Server default-on includes `TERMINAL` and `SYSTEM`; the CLI default capability set is `shell, files, code` and requires `terminal` and `ports` to be spelled out. Document the group column below as the switch. Do not document the YAML vocabulary as if it were the switch.

HTTP routes as registered (auth "token" = `auth_required` true). Streaming routes are SSE.

| Group | Default | Method | Path | Auth | Endpoint name |
|---|---|---|---|---|---|
| CORE | always | GET | `/health` | open | `health` |
| CORE | always | GET | `/capabilities` | token | `capabilities` |
| CORE | always | POST | `/capabilities/check` | token | `capabilities_check` |
| COMMANDS | on | GET | `/commands` | token | `list_commands` |
| COMMANDS | on | POST | `/commands/{name}` | token | `run_command` |
| FILE_OPS | on | POST | `/upload` | token | `upload` |
| FILE_OPS | on | GET | `/download` | token | `download` |
| FILE_OPS | on | GET | `/files/list` | token | `files_list` |
| FILE_OPS | on | GET | `/files/stat` | token | `files_stat` |
| FILE_OPS | on | POST | `/files/mkdir` | token | `files_mkdir` |
| FILE_OPS | on | DELETE | `/files` | token | `files_delete` |
| FILE_OPS | on | POST | `/files/move` | token | `files_move` |
| FILE_OPS | on | POST | `/files/search` | token | `files_search` |
| FILE_OPS | on | POST | `/files/upload-stream` | token | `files_upload_stream` |
| FILE_OPS | on | GET | `/files/download-stream` | token | `files_download_stream` |
| FILE_OPS | on | POST | `/files/archive` | token | `files_archive` |
| FILE_OPS | on | GET | `/files/watch` | token, SSE | `files_watch` |
| PROCESS | on | POST | `/shell` | token | `shell` |
| PROCESS | on | POST | `/shell/stream` | token, SSE | `shell_stream` |
| PROCESS | on | POST | `/process/start` | token | `process_start` |
| PROCESS | on | GET | `/process/list` | token | `process_list` |
| PROCESS | on | GET | `/process/{pid}` | token | `process_detail` |
| PROCESS | on | POST | `/process/{pid}/signal` | token | `process_signal` |
| PROCESS | on | POST | `/process/{pid}/stdin` | token | `process_stdin` |
| PROCESS | on | GET | `/process/{pid}/output` | token | `process_output` |
| TERMINAL | on | POST | `/pty/sessions` | token | `pty_create_session` |
| TERMINAL | on | GET | `/pty/sessions` | token | `pty_list_sessions` |
| TERMINAL | on | GET | `/pty/sessions/{id}` | token | `pty_detail` |
| TERMINAL | on | POST | `/pty/sessions/{id}/resize` | token | `pty_resize` |
| TERMINAL | on | DELETE | `/pty/sessions/{id}` | token | `pty_delete_session` |
| SYSTEM | on | GET | `/system/info` | token | `system_info` |
| SYSTEM | on | GET | `/env` | token | `env_get` |
| SYSTEM | on | POST | `/env` | token | `env_set` |
| SYSTEM | on | GET | `/ports` | token | `ports` |
| SYSTEM | on | GET | `/packages` | token | `packages` |
| SYSTEM | on | GET | `/system/metrics` | token | `system_metrics` |
| DEV_TOOLS | off | POST | `/code/run` | token | `code_run` |
| DEV_TOOLS | off | GET | `/git/status` | token | `git_status` |
| DEV_TOOLS | off | GET | `/git/diff` | token | `git_diff` |
| BROWSER | off | POST | `/browser/navigate` | token | `browser_navigate` |
| BROWSER | off | POST | `/browser/screenshot` | token | `browser_screenshot` |
| BROWSER | off | GET | `/browser/content` | token | `browser_content` |
| BROWSER | off | POST | `/browser/click` | token | `browser_click` |
| BROWSER | off | POST | `/browser/type` | token | `browser_type` |
| BROWSER | off | POST | `/browser/evaluate` | token | `browser_evaluate` |
| BROWSER | off | POST | `/browser/pdf` | token | `browser_pdf` |
| BROWSER | off | GET | `/browser/console` | token | `browser_console` |

Also part of the contract, not a `RouteTable` row: when `TERMINAL` is enabled, `SandboxServer.serve` starts `routes_pty.start_pty_server` on `EBX_PTY_PORT` (default 9001). The socket is `WS /pty?session_id=`. `runtime.py` lists it as virtual endpoint `pty_connect`. Legacy auth is query `token` equal to `EBX_SERVER_TOKEN`. With a policy engine, credentials are `Authorization: Bearer`, `X-Access-Token`, or `?token=`.

Also stable, and provider-blind, because `codegen.ts` already treats them as the fail-closed checks:

- The three files exist: `Dockerfile`, `commands.py`, `template.yaml`.
- `commands.py` parses, mentions `easy_sandbox.server`, and matches `/\.serve\s*\(|\bstart\s*\(/`.
- The Dockerfile text contains `commands.py` (so the server file is in the image).
- `template.yaml` parses and its capability tokens are inside `STANDARD_CAPABILITIES`.

`validateTemplateWorkspace` does **not** read the `FROM` image, `ENTRYPOINT`, `CMD`, `EXPOSE`, or port. That is the correct boundary. Keep it. Do not add a check for `aliyuncs.com` or for `CMD ["python3", "commands.py"]`.

Custom `@registry.command` names and `@table.route` paths are that template's own API. The stable part is only the mechanism: `POST /commands/{name}` with a JSON body, and custom routes limited to GET/POST/DELETE on the same auth and group rules.

Ports 9000 and 9001 are server constants. They stay in the server. They are not a provider fact.

## 2. What is allowed to vary, and the failure if it does not

Allowed to vary by provider, and only by provider:

- The `FROM` line, including registry host, image name, and tag.
- Whether `ENTRYPOINT` is left alone or replaced, and what `CMD` is.
- The control-plane `start_command` / `ready_command`, when the platform ignores Dockerfile `CMD`.
- User and workdir (`user` / `/home/user` on the FC image; anything else elsewhere).
- Platform constraints that are properties of that registry (`linux/amd64`, `/bin/bash` at a fixed path).

Not allowed to vary: the route table, the token header, the listen port of `SandboxServer`, and the wheel/`pip install easy-sandbox-server` fragment. That fragment is how the contract gets into the image. It is the same snippet on every `FROM`.

`base-image-and-server-sdk.md` §3 makes the opposite split. It freezes `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`, forbids overriding `ENTRYPOINT ["/.fce2b/entrypoint"]`, and forbids depending on `CMD`. Those are facts about one Alibaba image (`ENTRYPOINT` is a gateway that supervises envd on 49983 and a gateway on 5000). They are not facts about `easy_sandbox.server`.

If the generator writes that `FROM` into a template the user then deploys on OpenSandbox or local Docker:

1. `docker build` fails at `FROM`. That registry is region-scoped and documented as a public Aliyun pull. A laptop daemon and an OpenSandbox builder are not in that region. The build never produces an image.
2. A mirrored copy still fails at run. PID 1 is `/.fce2b/entrypoint`. The design says services are not started from `CMD`. There is no FC gateway, so nothing execs `commands.py`. Port 9000 never opens. The contract in §1 is unreachable, which is the only thing a caller can observe.
3. The region is baked into the image name. The same template cannot move to another Aliyun region, let alone another provider. `base-image-and-server-sdk.md` states the image region must equal the sandbox region.
4. OpenSandbox's path for a non-official image is copy plus envd inject. An image that already is the official FC image takes the "use as-is, no build" path and never grows the OpenSandbox runtime. The user gets whichever supervisor they did not ask for.

Today the generator contradicts itself, which is how this bug would ship. `template_guide.ts` §3 and `codegen.ts`'s prompt say `FROM` an official image such as `python:3.12-slim` and end with `CMD ["python3", "commands.py"]`. `cli/src/cli/scaffold.ts` hardcodes `FROM python:3.11-slim` and that same `CMD`. The base-image design says the opposite `FROM` and says not to use `CMD`. `validateTemplateWorkspace` accepts both, including a Dockerfile whose only mention of `commands.py` is a comment. Neither file may be the place that picks the registry.

## 3. Rejected couplings

Rejected:

- Provider Docker inside `easy_sandbox.server`. `server/contract.py` already does this: `ENVD_PORT = 49983`, `GATEWAY_PORT = 5000`, `CODE_INTERPRETER_PORT = 49999`, `DEFAULT_USER = "user"`, `DEFAULT_HOME = "/home/user"`, and `START_COMMAND = "easy-sandbox-server serve ..."`, with a module docstring that cites the Alibaba base image. Those names are not a server contract. A local container that uses port 5000 is not "violating" the SDK. Keep `DEFAULT_HTTP_PORT` and `DEFAULT_PTY_PORT`. Delete the platform ports and the user/home from the server package.
- A client SDK that imports a provider, or that inlines one, to build an image. `base-image-and-server-sdk.md` §4 puts `OFFICIAL_REGISTRY_FMT`, `official_base_image`, `Image.official_base`, and `lint_dockerfile` (warning unless the base is the FC image) in `easy_sandbox.api.base_image`. That makes every `Image.build()`, including OpenSandbox and local Docker, carry an Aliyun opinion. The client accepts a Dockerfile the caller already wrote. It does not select a registry.
- A shared "base image helper" importable by both SDKs. If both import it, both depend on a provider. The dependency arrow is one way: the CLI provider may know the server port; the server may not know the provider.

Allowed home, and the only home: the CLI provider manifest.

- Built-in provider id is `alicloud-express` (`cli/src/utils/config_keys.ts` `builtin_provider.id`; `cli/src/providers/builtin.ts`). `cli/src/providers/index.ts` states it is the default provider.
- Installed providers declare themselves in `ebx-provider.toml`, parsed by `cli/src/providers/manifest.ts`. That file is the manifest. Add the image profile there.
- The built-in provider has no external toml. Its profile is a constant beside `AlicloudExpressProvider`, still under `cli/src/providers/`. It is not a Python module.

## 4. Smallest abstraction that still generates a correct Dockerfile

One table, read by `ebx template init` and by `buildTemplateGuide` / `buildCodegenPrompt`. No class hierarchy, no strategy registry inside either SDK.

```toml
# ebx-provider.toml — installed providers only
[template.image]
from = "fc-e2b-registry.{region}.cr.aliyuncs.com/runtime/base:{tag}"
entrypoint = "keep"          # keep | replace
cmd = ""                     # empty: do not emit CMD
start_command = "python3 commands.py"
ready_command = ""
user = "user"
workdir = "/home/user/app"
```

A non-Aliyun provider ships different strings, for example `from = "python:3.12-slim"`, `entrypoint = "replace"`, `cmd = "[\"python3\", \"commands.py\"]"`, empty `start_command`. Placeholders `{region}` and `{tag}` expand from **that provider's** config keys. The server has no region.

Resolution:

1. Provider id = flag, else the configured provider, else `alicloud-express`. No flag still emits the FC `FROM`, because that is already the default provider. Do not add a second default inside the generator.
2. The generator splices three fixed server fragments around the profile: install `easy-sandbox-server` (the existing `COPY *.whl` / pip fallback), `EXPOSE 9000`, and `COPY commands.py`. It emits `ENTRYPOINT`/`CMD` only as the profile says. It writes `start_command` onto the deploy call, not into the Dockerfile, when `cmd` is empty.
3. The NL prompt is the same splice. Delete the hardcoded "pick python:3.12-slim / ubuntu" sentence and the hardcoded "never override ENTRYPOINT" sentence. Both are profile text.
4. `validateTemplateWorkspace` stays provider-blind: `FROM` exists, `commands.py` starts the server, the Dockerfile mentions `commands.py`, the YAML schema passes. It must not grep the registry host.

That is the whole abstraction. `scaffold.ts` stops embedding `FROM python:3.11-slim` and calls the same function.

## 5. The page a caller needs (do not write it here)

Path: `python-sdk/docs/en/reference/server-http-api.md`.

That file exists and is a one-line pointer at `docs/en/design/server-api.md`. The design doc is not the API. Its appendix still counts CORE as 2 (omits `POST /capabilities/check`), PROCESS as 6 (omits `/process/{pid}/stdin` and `/process/{pid}/output`), and FILE_OPS as 11 (omits `GET /files/watch`). `template_guide.ts` still documents `/capabilities` as unauthenticated.

The reference page has to stand alone for a caller who will not open `routes*.py`. For health, capabilities, commands, files, and shell it needs method, path, the group that enables it, whether `EBX_SERVER_TOKEN` + `X-Access-Token` applies, and the request and response fields. Same page covers the other rows in §1 so the guide can quote it instead of inventing auth. Until that page is the contract, the generator prompt will keep drifting from the dispatcher.
