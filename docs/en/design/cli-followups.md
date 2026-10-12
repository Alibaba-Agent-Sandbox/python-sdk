# `ebx` CLI follow-ups: fine-grained capabilities, base image, server alignment

> Audience: the CLI worker for the Node/TypeScript repository (`/workspace/cli`). That repository
> was **not** edited by this workstream; this file is the exact spec. Related specs:
> [agents-api-cli-followups.md](agents-api-cli-followups.md) (Agents API),
> [providers-and-credentials.md](providers-and-credentials.md) (credentials).
> Designs: [fine-grained-capabilities.md](fine-grained-capabilities.md),
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md),
> [client-server-alignment.md](client-server-alignment.md).

Everything below is **additive**: an `ebx` that implements none of it keeps working with the new
SDKs (unconfigured server, unchanged templates).

## 1. `ebx template init` scaffold (`src/cli/scaffold.ts`)

The current Python/Node/minimal scaffolds start `FROM python:3.11-slim` / `node:20-slim`, install
`easy-sandbox` (the client distribution, which now depends on the server) and run
`CMD ["python3", "commands.py"]`. New default for **all** scaffolds:

1. `FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`. `<region>` is the
   resolved region (`src/cli/region.ts`, default `cn-hangzhou`); `<tag>` defaults to `v0.0.49`
   and is overridable by env `EBX_BASE_IMAGE_TAG` (region: `EBX_BASE_IMAGE_REGION`). Variants:
   `base`, `code-interpreter-v1`, `browser`, `claude-code` (flag `--base-variant`). Validate the
   parts against `^[a-z0-9-]+$` (region), `^[a-z0-9][a-z0-9._-]*$` (variant),
   `^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$` (tag) - same rules as
   `easy_sandbox.api.base_image.official_base_image`.
2. Install the **server** distribution, pinned to the CLI's lock-step version:

   ```dockerfile
   ENV PIP_BREAK_SYSTEM_PACKAGES=1 PIP_NO_CACHE_DIR=1
   COPY *.whl /tmp/
   RUN command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 1; } \
    && if ls /tmp/easy_sandbox_server-*.whl >/dev/null 2>&1; then \
         pip install /tmp/easy_sandbox_server-*.whl; \
       else \
         pip install 'easy-sandbox-server==<VERSION>'; \
       fi \
    && rm -f /tmp/easy_sandbox_server-*.whl
   ```

   (`pip install easy-sandbox` is wrong for an in-container runtime; keep the glob narrow so
   the injected wheel is not confused with other wheels.)
3. `WORKDIR /home/user/app`, `COPY commands.py /home/user/app/commands.py`, `EXPOSE 9000 9001`,
   `ENV EBX_SERVER_BASE_DIR=/home/user`. Do **not** emit `ENTRYPOINT` (the gateway is PID 1)
   and do not rely on `CMD`.
4. Optional (`--policy <preset|file>`): `COPY server-policy.json /etc/easy-sandbox/server-policy.json`
   and `RUN easy-sandbox-server check-config --policy /etc/easy-sandbox/server-policy.json`
   (do **not** pass `--strict` while building as root: lint L5 would fail the build).
5. Node scaffold: Node comes from the base image; keep the Python server layer identical.
6. `commands.py` template: replace the `start()` boilerplate by commands-only module (it is
   imported by `easy-sandbox-server serve --commands /home/user/app/commands.py`); keep the old
   `start()` variant working (`python3 commands.py`) for existing templates.
7. `template.yaml` scaffold: `base:` becomes the official reference; add a commented `server:`
   block (see section 3) and `start_command` / `ready_command`:

   ```yaml
   start_command: easy-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
   ready_command: easy-sandbox-server healthcheck --port 9000
   ```

The CLI may shell out to nothing Python: the strings above are plain text (the Python helper
`scaffold_dockerfile()` is the reference implementation; the CLI test should compare its output
for the default arguments once, as a golden file).

## 2. Deploy (`src/cli/commands/template.ts`, `src/api/docker_builder.ts`, `src/api/fc_template.ts`)

* **Wheel injection**: inject the **server** wheel (`easy_sandbox_server-<v>-py3-none-any.whl`);
  `_downloadReleaseWheel` must ask PyPI for `easy-sandbox-server` (not `easy-sandbox`) and the
  dev-checkout path must build `server-sdk/`. File name glob in the Dockerfile:
  `easy_sandbox_server-*.whl`.
* **Dockerfile lint (advisory, never fatal)** before the build, port of
  `easy_sandbox.api.base_image.lint_dockerfile`: parse logical lines; look only at the **last
  stage**; report
  `B001` base is not `fc-e2b-registry.*.cr.aliyuncs.com/runtime/*` (and is not a previous stage
  name), `B002` `ENTRYPOINT` present, `B003` final `USER root`/`0`, `B004` `EXPOSE` of 5000,
  49983 or 49999, `B005` no `FROM`. Print as `warning:` lines; add `--no-lint` to silence.
* **`envd_inject` auto-choice** (`use_official` path, `envd_inject` option): when the last
  stage's base is an official image keep `envd_inject=false` (the image already contains envd);
  when it is not, keep today's default but print the B001 warning with the consequence
  ("pass `--envd-inject` so the platform injects envd"). Do not flip the default silently.
* **`start_command` / `ready_command`**: when `template.yaml` has them (or the CLI scaffold
  produced them) pass them as `start_command` / `ready_command` to the official create-template
  call (already plumbed as `start_cmd` / `ready_cmd`, generation 2 only). Defaults when the
  Dockerfile uses the server scaffold and the flags are absent: `easy-sandbox-server serve --port
  9000` and `easy-sandbox-server healthcheck --port 9000` (the latter exits 0/1 and needs no
  network beyond `127.0.0.1`).
* **Policy compile**: if `template.yaml` has a `server:` block, write it as JSON to
  `<context>/server-policy.json` and make sure the Dockerfile copies it to
  `/etc/easy-sandbox/server-policy.json`; fail fast with the validator message (section 3).
  YAML to JSON conversion happens in the CLI because the in-container server is stdlib-only.

## 3. `template.yaml` `server:` block (`src/utils/registry.ts`, `src/api/template.ts`)

The declarative block is the same document as the JSON policy (see
[fine-grained-capabilities.md](fine-grained-capabilities.md) section 4). Port
`validate_server_block` from `easy_sandbox.models.template`: unknown keys are errors
(`server.<path>: unknown key; allowed: [...]`); top-level keys
`version, preset, base_dir, groups, defaults, auth, endpoints, description`; presets
`default, transfer-only, read-only, hardened, locked`; rule keys
`enabled, scopes, paths, limits, params, audit`; path keys `allow, deny, read_only, symlinks`.
Values are validated by the server (`easy-sandbox-server check-config`), which the CLI may run
inside the build as in section 1.4; never accept `token` literals in YAML: tokens are provided as
`token_env` names or `token_sha256` digests.

## 4. New CLI commands (optional, thin HTTP clients)

All talk to the template's SandboxServer through the sandbox gateway URL (`9000-<id>.<domain>`)
with `X-Access-Token` (gateway) and, when the server has its own tokens, `Authorization: Bearer`.

| Command | HTTP |
|---------|------|
| `ebx sandbox server caps <id> [--endpoint NAME]` | `GET /capabilities` (v2: `endpoints`, `identity`, `revision`) |
| `ebx sandbox server check <id> <endpoint> [--path P --op read\|write\|delete]` | `POST /capabilities/check` |
| `ebx sandbox server start <id> [--commands F --preset P --policy FILE --token T]` | envd background command `easy-sandbox-server serve ...` + poll `GET /health` (mirror of `Sandbox.start_server`) |
| `ebx sandbox files watch <id> <path>` | `GET /files/watch` (SSE) |
| `ebx sandbox process output <id> <pid> [--since N --wait]` | `GET /process/{pid}/output` |
| `ebx sandbox process stdin <id> <pid> [-]` | `POST /process/{pid}/stdin` |

Exit codes follow the E9xxx table in [error-codes.md](../reference/error-codes.md) (401 -> 3, other
server errors -> 1); the CLI prints `code`, `endpoint` and `scope` from the JSON body, and
`retry_after` for 429.

## 5. AI template guide (`src/agent/template_guide.ts`) and codegen/adopt

The guide currently teaches `commands.py` + `CMD ["python3", "commands.py"]` on arbitrary bases.
Update the prompt text and `REQUIRED_TEMPLATE_FILES` notes:

* start `FROM` the official base image of the sandbox region (give the exact reference);
* never write `ENTRYPOINT`; never rely on `CMD`; the platform runs
  `easy-sandbox-server serve --port 9000 --commands /home/user/app/commands.py`;
* install `easy-sandbox-server` as in section 1.2; put code in `/home/user/app`; run as `user`;
* ports 5000, 49983, 49999 are reserved; 9000 is the HTTP server, 9001 the PTY WebSocket;
* to restrict what the template exposes, add a `server:` block (give two examples:
  `transfer-only` with `paths.allow: [/home/user/out]`, and a read-only preset);
* after generating, run the section-2 lint and the `check-config` command in the validation step.

`adopt.ts` (adopting an existing Dockerfile): run the same lint, and if the base is not official
only **suggest** the rewrite; do not rewrite user Dockerfiles automatically.

## 6. Tests the CLI worker should add

* Scaffold golden files for python/node/minimal against `scaffold_dockerfile()` output.
* Lint table tests for B001-B005 incl. multi-stage, `FROM --platform=...`, stage-name bases,
  line continuations, comments.
* `server:` block validator parity test against the vocabulary listed in section 3.
* Deploy: injected wheel name, `envd_inject` unchanged by default, `start_cmd` / `ready_cmd`
  plumbed for generation 2 only.

## 7. Open points that need platform confirmation

1. Default tag (`v0.0.49` per the current official page) and how often it changes.
2. Whether the gateway honours a Dockerfile `CMD`, or only the platform `start_command`
   (the design avoids `CMD`).
3. Whether the gateway forwards `Authorization` to ports (the server accepts both
   `Authorization: Bearer` and `X-Access-Token`, so either works).
4. Whether `user` / `/home/user` is guaranteed for every official variant (documented for
   `claude-code`).
5. Whether `envdInject` is harmless on an image that already contains envd.
