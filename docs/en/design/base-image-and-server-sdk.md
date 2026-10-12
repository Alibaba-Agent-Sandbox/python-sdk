# Official Base Image and the Server SDK

> Status: **v2 (reviewed; see fine-grained-capabilities-review.md)** — reviewed together with the fine-grained capability design in
> [fine-grained-capabilities-review.md](fine-grained-capabilities-review.md).
> Product requirement: *all template builds should be based on the Alibaba Cloud Agent Sandbox
> (FC Agent Sandbox) base image.*

## 1. What the base image is (evidence)

Sources: repository research (`.agents/evidence/research/2026-09-04-fc-claude-code-image-inspection.md`,
`...-fc-sandbox-official-docs.md`), and the official doc page
[Build a custom image template](https://help.aliyun.com/zh/functioncompute/build-a-custom-image-template)
(fetched while writing this design; it currently cites tag `v0.0.49`, older notes cite `v0.0.44`).

| Fact | Value | Source |
|------|-------|--------|
| Registry/name pattern | `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/<name>:<tag>`; names: `base`, `code-interpreter-v1`, `browser`, `claude-code`, ... | official doc |
| Region rule | image region **must equal** the sandbox region; public pull, no credentials | official doc |
| Official image as template source | used **as-is, no build step** (`build_config` omitted); any *other* image is auto-processed: `copy` (re-push) + `envdInject` | official doc |
| Process model | `ENTRYPOINT ["/.fce2b/entrypoint"]` = PID 1 gateway + process manager; supervises `envd` (49983) and, if enabled, `sandbox-code-interpreter` (49999); gateway on 5000 | image inspection |
| Default user / cwd | `user`, `/home/user` (documented for the claude-code image; docs say "do not assume the same default user for every image") | official doc + inspection |
| Hard requirements for custom images | `linux/amd64`; `/bin/bash` at that exact path; writable standard `/etc/passwd` and `/etc/group`; no ACR image acceleration | official doc |
| Conditional | `python3` on PATH (Python `run_code`), `node` (JS `run_code`), git/ssh/CA certs as needed | official doc |
| Services started by the template | no template-level `startCmd` in the *docs*; services are started with background commands. The platform API accepts `start_command` / `ready_command` (used by our `create_official_template`) | docs + repo |
| Python | 3.13 on Ubuntu 25.04 for `claude-code` (PEP 668 "externally managed"), pip config pointing at an Alibaba mirror | image inspection |

## 2. Decision

**Server-SDK design work *is* warranted. Template builds default to the official base image through
scaffolding, a documented contract, helpers and linting — not by silently changing the behaviour of existing
APIs.**

Reasoning:

1. **Correctness, not taste.** `create_official_template(envd_inject=False)` is our default path:
   it only yields a working sandbox if the image already contains envd. A template built `FROM
   ubuntu:22.04` (today's `Image()` default and the `python-hello` fixture) has no envd unless the
   platform builder injects it. Basing on the official image makes the default path valid and
   lets the platform skip the `copy` + `envdInject` builder function (faster, cheaper, fewer moving
   parts, envd/gateway versions are the platform's tested ones).
2. **The server SDK has to live somewhere.** Layering `easy-sandbox-server` onto the official image gives a
   well-defined target: known PID 1, known user/HOME (default `EBX_SERVER_BASE_DIR=/home/user`
   matches), known ports (49983/5000 taken -> 9000/9001 free).
3. **Do not break unconfigured callers.** `Image()` still starts `FROM ubuntu:22.04`;
   `DockerBuilder.build*` still accept any Dockerfile. New behaviour is opt-in or advisory
   (warning). The default flip is announced as a deprecation in the changelog.

## 3. The contract (what a Dockerfile layered on the base image can rely on)

Documented in `docs/en/reference/base-image-contract.md`-equivalent sections of
`server-api.md` and enforced by `easy_sandbox.api.base_image.BaseImageContract`:

| Item | Contract |
|------|----------|
| FROM | `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>` (`official_base_image(region=, variant=, tag=)`) |
| Do not override | `ENTRYPOINT` (gateway PID 1); do **not** depend on `CMD` for starting services |
| Server start | platform `start_cmd = "easy-sandbox-server serve --port 9000"`, `ready_cmd = "easy-sandbox-server healthcheck --port 9000"`; fallback `Sandbox.start_server()` (envd background command + readiness poll) |
| Ports | 49983 envd, 5000 gateway, 49999 code interpreter (reserved); **9000** server HTTP, **9001** PTY WebSocket |
| User | runs as `user` (via envd/start cmd); files under `/home/user`; app code in `/home/user/app` (legacy `/app` still works if `EBX_SERVER_BASE_DIR` includes it) |
| Python | the scaffold guards `command -v python3`; installs with `PIP_BREAK_SYSTEM_PACKAGES=1` (PEP 668) |
| SDK injection | `COPY *.whl /tmp/` + `pip install` with a PyPI fallback **pinned to the client's version** (lockstep releases) |
| Policy | `COPY server-policy.json /etc/easy-sandbox/server-policy.json` (auto-loaded, see fine-grained doc 4) |
| Platform | `linux/amd64`, `/bin/bash`, writable `/etc/passwd`, `/etc/group` (already satisfied by the base) |

## 4. What gets implemented

**server-sdk**

* `easy-sandbox-server` console script and `python -m easy_sandbox.server` (`__main__.py`):
  `serve` (default; `--host --port --commands <file-or-module> --policy <json> --preset <name>
  --base-dir`), `healthcheck` (HTTP GET `/health`, exit code 0/1, for `HEALTHCHECK` and `ready_cmd`),
  `check-config` (validate + lint a policy, print effective endpoint table), `version`.
  `--commands` imports a user module so its `registry.command(...)`/`table.route(...)` side effects
  register (what `commands.py` did with `start()`), then serves — a template needs no bespoke
  `commands.py` boilerplate.
* `easy_sandbox.server.contract` constants (ports, paths, env-var names) shared by CLI/server.
* Policy auto-load (`/etc/easy-sandbox/server-policy.json`).
* `pyproject.toml`: `[project.scripts] easy-sandbox-server = "easy_sandbox.server.__main__:main"`.

**client-sdk**

* `easy_sandbox/api/base_image.py`: `OFFICIAL_REGISTRY_FMT`, `DEFAULT_BASE_VARIANT="base"`,
  `DEFAULT_BASE_TAG`, `official_base_image(...)`, `is_official_base_image(ref)`,
  `BaseImageContract`, `lint_dockerfile(text) -> list[BaseImageIssue]`,
  `scaffold_dockerfile(...)` (Dockerfile text per section 3), `SERVER_START_CMD`,
  `SERVER_READY_CMD`.
* `Image.official_base(variant, region, tag)` classmethod (chain API unchanged otherwise);
  `Image.build()` and `DockerBuilder.build*()` call `lint_dockerfile` and log a warning (not an error) for
  non-official bases, naming the consequence (`envd_inject=True` required).
* `Sandbox.start_server(...)` (remote start + readiness) and the `Sandbox.server` client.
* `SandboxTemplate.server` (structurally validated policy block). A declarative
  `SandboxTemplate.base_image` field was considered and **not added**: the Dockerfile is the single
  source of truth for the base, and the lint (`B001`) reads it from there.

**Not implemented (justified)**

* No change to `DockerBuilder`'s default of `envd_inject=False` and no automatic flip for non-official images:
  that would change what an unconfigured build sends to the platform. Warning + docs + CLI follow-up instead.
* No bundling of the server wheel in a custom base image: the wheel injection already covers the
  "installed from PyPI" and "dev checkout" cases and keeps lockstep versions.
* No second HTTP gateway/proxy: the platform gateway on 5000 already routes `{port}-{sandbox}` hosts.

## 5. CLI-side changes (recorded in `cli-followups.md`)

Node scaffold `ebx template init` (FROM official base, scaffold per section 3); deploy path
(`DockerBuilder` equivalent: wheel injection, `envd_inject` auto-choice, `start_cmd`/`ready_cmd`);
`template.yaml` `server:` compile; AI template-guide prompt (must start FROM the official base,
never override ENTRYPOINT, use `easy-sandbox-server serve`).

## 6. Open questions (cannot be settled from repo/docs)

1. Does the gateway honour a Dockerfile `CMD` or only the platform `start_command`? (we avoid CMD.)
2. Is `/home/user` + user `user` guaranteed for the plain `base` image (documented for `claude-code`)?
3. Exact default tag: docs say `v0.0.49`; we expose `EBX_BASE_IMAGE_TAG` and a constant so it is one line to bump.
4. Does the platform tolerate an already-envd-containing non-official image with `envdInject` on?

## 7. Changes after review (Draft v1 -> v2)

* The claim that the gateway forwards `Authorization` is unverified (OQ-3 in the review log): the server
  accepts both `X-Access-Token` and `Authorization: Bearer`, so either gateway behaviour works.
* `healthcheck` uses only `urllib.request` against `127.0.0.1` (2 s timeout, exit code 0/1) so it can
  serve as a Docker `HEALTHCHECK`/`ready_cmd` without heavy imports.
* `Image()` default base stays `ubuntu:22.04`; `Image.official_base()` is opt-in; a non-official base
  produces a logged warning only.
* Console script name `easy-sandbox-server` verified not to clash with `ebx`.

## 8. Implementation status

Implemented as designed: `easy-sandbox-server` console script (`serve`, `healthcheck`,
`check-config`, `version`), `easy_sandbox.server.contract`, `easy_sandbox.api.base_image`
(`official_base_image`, `is_official_base_image`, `lint_dockerfile` B001-B005,
`warn_on_dockerfile`, `scaffold_dockerfile`, `BaseImageContract`), `Image.official_base()`,
advisory linting in `Image.build()` and `DockerBuilder.build()`, `Sandbox.server` /
`server_at()` / `start_server()`. Tests: `client-sdk/tests/test_api/test_base_image.py`,
`tests/test_api/server_e2e/test_sandbox_server_helpers.py`, `server-sdk/tests/test_server/test_cli_main.py`.
Exact CLI-side changes: [cli-followups.md](cli-followups.md).
