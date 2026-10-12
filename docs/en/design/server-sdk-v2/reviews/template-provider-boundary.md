# Review: template generation vs provider image contracts

Adversarial. No application source was changed. Evidence is the generator spec, the three live defaults, the FC base-image design, and the OpenSandbox plugin. There is no `examples/providers/opensandbox/manifest.json`; the plugin manifest is `ebx-provider.toml`.

The maintainer is right: the SDK must not depend on a sandbox provider. The image contract is the provider's. The HTTP server is not. Today's code has that backwards in two modules, and the generator follows a third contract that matches neither.

## What the tree actually does

| Source | Base image | How the server becomes the process | Workdir |
|---|---|---|---|
| `cli/src/agent/template_guide.ts` and `cli/src/agent/codegen.ts` | Unconstrained `FROM`. Prompt examples: `python:3.12-slim`, `node:20-slim`, `ubuntu:24.04`. "官方基础镜像" means a Docker Hub official image. | `CMD ["python3", "commands.py"]`. `commands.py` ends in a blocking `SandboxServer.serve(port=9000)`. `validateServerEntrypoint` rejects a file that does not call `serve()` / `start()`. | `/app` |
| `cli/src/cli/scaffold.ts` | `python:3.11-slim` (node case: `node:20-slim`) | Same `CMD`. Installs `easy-sandbox`, not `easy-sandbox-server`. | `/app` |
| `cli/src/api/image.ts` | `ubuntu:22.04` | No default command. `entrypoint()` writes a `CMD` line. `build()` can pass `start_cmd`. | unset |
| `python-sdk/docs/en/design/base-image-and-server-sdk.md`, `client-sdk/.../api/base_image.py`, `server-sdk/.../server/contract.py` | `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>` (`v0.0.49`, region default `cn-hangzhou`) | Do not set `ENTRYPOINT`. Do not depend on `CMD`. Platform `start_cmd` / `ready_cmd`. `lint_dockerfile` warns on any other `FROM` (`B001`) and on any `ENTRYPOINT` (`B002`). | `/home/user/app` |
| OpenSandbox plugin (`ebx-provider.toml`, `src/sandbox.mjs`) | `default_image` `python:3.12-slim` | Create **requires** an `entrypoint` argv. Default `tail -f /dev/null`. Image `CMD` is not the start path. `templates.*` is unsupported. execd is injected on **44772**. | not specified |

`commands.py` and the HTTP API do not mention a sandbox provider. `REFERENCE_COMMANDS_PY` imports only `easy_sandbox.server` (`CapabilityGroup`, `CommandRegistry`, `SandboxServer`, `default_table`) and listens on 9000. Grep of `server-sdk/src/easy_sandbox/server` finds no sandbox-provider import. The word `provider` under `easy_sandbox.server.agents` is an LLM endpoint (`base_url`, `api_key`, `wire_api`). It is not a slot for `alicloud-express` or OpenSandbox.

## 1. Owner split

| Concern | Owner |
|---|---|
| HTTP API: routes, `SandboxServer.serve`, `/health`, port **9000** listen default, PTY **9001** | Server SDK, inside the image. No provider id, no registry, no `ENTRYPOINT` rule. |
| `commands.py`: registrations and, under `if __name__ == "__main__"`, `serve(port=9000)` | Template file the CLI generator writes. It stays free of provider names. The server imports it for side effects (`--commands`) or the container runs it as main. |
| Which `FROM`, whether `ENTRYPOINT` may be replaced, `CMD` vs platform `start_cmd`/`ready_cmd`, arch, workdir, reserved ports, registry/push | **Provider template profile**, read by the CLI generator. Built-in profile sits beside `AlicloudExpressProvider`. A plugin puts it in `ebx-provider.toml`. |
| Rendering that profile into the Dockerfile, the `template.yaml` start fields, and the prompt that replaces today's single `TEMPLATE_GUIDE` | CLI generator (`template_guide.ts`, `codegen.ts`, scaffold). |
| `official_base_image(region=, tag=)` as a string formatter | Client SDK, optional helper. The caller passes region and tag. It does not choose a provider and the generator does not call it unless the selected profile's base reference is that pattern. |
| Deciding `envd_inject`, ACR region lock, OpenSandbox create `entrypoint` | Provider plugin at build/create time, using the same profile. Not the server process. |

## 2. Profile shape (fields only)

```
base_image
entrypoint_replaceable     # bool
server_start               # image_cmd | platform_start_cmd
cmd                        # argv, only when server_start = image_cmd
start_cmd                  # string, only when server_start = platform_start_cmd
ready_cmd                  # string or null
arch
workdir
reserved_ports             # ports the template must not bind
registry                   # pull/push hints; not credentials
```

**alicloud-express** (FC Agent Sandbox; this is the contract in `base-image-and-server-sdk.md`):

```
base_image: fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
entrypoint_replaceable: false
server_start: platform_start_cmd
cmd: null
start_cmd: easy-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
ready_cmd: easy-sandbox-server healthcheck --port 9000
arch: linux/amd64
workdir: /home/user/app
reserved_ports: [49983, 5000, 49999]
registry: public pull; image region must equal the sandbox region; a non-matching FROM takes platform copy + envdInject; no ACR image acceleration
```

**Generic Docker / OpenSandbox** (no FC gateway). One profile. OpenSandbox does not get the FC fields just because it is also a provider.

```
base_image: python:3.12-slim
entrypoint_replaceable: true
server_start: image_cmd
cmd: ["python3", "commands.py"]
start_cmd: null
ready_cmd: null
arch: linux/amd64
workdir: /app
reserved_ports: []
registry: pull by image URI; no region-locked FC registry; no envdInject; private-registry auth stays in provider config
```

OpenSandbox's plugin must grow two facts on top of that profile, not instead of it: create's required `entrypoint` argv has to be `cmd` (today it sends `tail -f /dev/null`, so a generated `CMD` never runs), and **44772** is reserved because execd is injected into the container netns. `templates.*` is unsupported, so this provider does not build the Dockerfile; the image has to be pullable already.

## 3. Selected provider has no profile

The generator applies the generic profile above and says which provider id had none. It still writes `commands.py` and a Dockerfile that starts with `FROM python:3.12-slim`.

It does not call `official_base_image()`. A missing profile is not Alibaba Cloud Express. It does not read runtime create knobs (`default_image`, `entrypoint`) as if they were a Dockerfile contract: OpenSandbox's current `entrypoint` is a keep-alive, and using it would emit a container that never binds 9000.

`commands.py` is always the main-guard form, so a later profile can switch `server_start` without a second HTTP API. `validateServerEntrypoint` keeps requiring `easy_sandbox.server` and a `serve()` call. For `platform_start_cmd` it must also require that `serve()` is not at import time, and it must reject a Dockerfile `CMD` / `ENTRYPOINT`.

## 4. What must not move into the SDK

- No provider import, provider id, or profile lookup inside `easy_sandbox.server`, including `commands.py` and the route table. The agents LLM `provider` block stays an LLM endpoint.
- The client SDK must not select a provider, read `EBX_PROVIDER`, or treat `alicloud-express` as the generator default.
- `official_base_image` may stay a pure function that returns a string when the caller passes region and tag. A no-argument call already returns the Hangzhou FC image; the generator must not use that as a default.
- `BaseImageContract`, `lint_dockerfile` `B001`/`B002`, and `server.contract` `ENVD_PORT` / `GATEWAY_PORT` / `CODE_INTERPRETER_PORT` / `START_COMMAND` are the alicloud-express profile living in the SDK. They move out with the profile. The server keeps **9000** as its own listen default. Reserved FC ports are not properties of the HTTP API.
- Scaffold and `Image()` do not grow a provider switch. They take a base reference from the caller or from the CLI, which got it from the profile.

## 5. Fix this contradiction first

`template_guide.ts` (and the prompt in `codegen.ts`, and `scaffold.ts`) says the container main process is `python3 commands.py`, with `CMD ["python3", "commands.py"]` and `WORKDIR /app`.

The FC base image says the opposite: `ENTRYPOINT ["/.fce2b/entrypoint"]` stays PID 1, services are not started with `CMD`, workdir is `/home/user/app`, and the platform runs `start_cmd` / `ready_cmd`. Docker appends `CMD` to an existing `ENTRYPOINT`, and the design doc leaves open whether the gateway honors those args (section 6, question 1). The guide's `CMD` is therefore not a legal start for this image. `WORKDIR /app` also misses the image default `EBX_SERVER_BASE_DIR=/home/user` unless the template sets that env.

**alicloud-express: the FC rule is the one that is right.** The generator must emit the official `FROM`, must not emit `ENTRYPOINT` or `CMD`, must use `/home/user/app`, and must pass `start_cmd` / `ready_cmd`. `commands.py` only registers; `serve()` runs under `__main__` so `--commands` import does not bind the port twice.

**A non-FC provider: the guide's `CMD` and `WORKDIR /app` are the ones that are right.** Nothing in that image is a gateway PID 1. Replacing or setting the image command is how `easy_sandbox.server` starts. The FC lint must not flag that Dockerfile.

Do not paper over this by teaching the agent both rules in one prompt. One selected profile, one Dockerfile. The package-name drift (`easy-sandbox` in the scaffold vs `easy-sandbox-server` in the guide) and the three non-FC bases (`3.11-slim`, `3.12-slim`, `ubuntu:22.04`) are real, and they are second.
