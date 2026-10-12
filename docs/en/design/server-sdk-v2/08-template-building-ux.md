# 08 - Template building UX

> Part of [Server SDK v2](README.md). How a template author (human or AI coding agent) gets a correct, minimal,
> policy-controlled server into an image. Related: [06](06-lazy-install.md), `base-image-and-server-sdk.md`.
> **v2.1**: the `server:` block is compiled with **strict unknown-key rejection** (IF-31) and a schema version; the docker build injects the server package
> for Alibaba base-image templates, PEP 668 safe (IF-22, IF-13); presets use one keyword `root=` (B-8); `legacy` is never implicit on a new template; the journeys were executed
> as `spikes/templates/t1..t8` (B-11..B-13). Owner WPs: 10b (compile + build + decorator), 10c (client surface).

## 1. Goals

* **A template should need no HTTP code.** Today `codex-agent-api/commands.py` is ~1,400 lines of routing, session handling and
  process management; v2 makes it a 15-line `server:` block.
* One declarative surface (`server:` in `template.yaml`) and one imperative surface (`server.py` with `@op` and `Policy`), both
  compiling to the same runtime configuration (`/etc/easy-sandbox/server.json`).
* The default is safe and small; every escalation is explicit and linted; first-use install keeps images small.

## 2. The `server:` section of `template.yaml`

```yaml
server:                              # all keys optional; absent section = legacy default server (today's behaviour)
  version: 1                         # (v2.1) schema version of the block; written into server.json; unknown versions are refused by the runtime
  preset: ci-runner                  # name or list of names (03 section 4; hyphen and underscore spellings both accepted); params as siblings (root, commands, ...)
  root: /workspace                   # (v2.1, B-8) the ONE keyword for the preset's root(s); `paths:` and `workspace:` are accepted aliases
  enable: ["agents.codex.**"]       # extra selectors to allow (unscoped; prefer rules for scoped grants)
  disable: ["terminal.*", files.delete]       # sugar for deny rules
  rules:                             # full-fidelity rules (03 section 10 schema)
    - allow: [files.download, files.stat, files.list]
      paths: {roots: [/tmp], deny: ["**/.env"], max_bytes: 10MB}
  custom:                            # declarative named commands -> custom.<name> ops (safest way to run things)
    grade:
      argv: ["python3", "/workspace/grade.py", "--submission", "{submission}"]
      params: {submission: {type: path, root: /workspace/submissions}}
      cwd: /workspace
      timeout: 60s
      effects: [exec]
      principals: [role:grader]
  auth:
    tokens: [{id: app, roles: [dev], token_env: APP_API_KEY}]
  agents: [codex]                    # adapter names or declarative definitions
  agent:
    codex: {llm: {base_url_env: LLM_BASE_URL, api_key_env: LLM_API_KEY, model: gpt-5-codex}, permissions: workspace-write}
  install: {mode: build, mirrors: {npm: "https://registry.npmmirror.com"}}   # (v2.1) build = prepare at image build; the recommended FC setting
  audit: {sink: stderr}
  load: [my_template.ops]            # python modules with @op (shipped in the image)
```

* **Validation is strict, fail-closed (v2.1, IF-31, IS-A1).** The client-side validator (`models/template.py::validate_server_block`) and the runtime loader (`from_config`)
  share **one key table generated from the server** (`catalog/server_schema.json`, vendored into the client by `make gen`; the client never imports the server).
  Any unknown key at any depth is an error with a did-you-mean (`config.unknown_key`): `server.pesets` -> "did you mean 'preset'?". The working tree currently has two weaknesses that must be fixed:
  (a) `SandboxTemplate` declares `model_config = {"extra": "ignore"}`, so a typo of the **top-level key** (`servr:`) silently builds a legacy-default server; the compile step reads the raw YAML and
  rejects unknown top-level keys of the template that look like `server` (edit distance <= 2) and the model changes to `extra="forbid"` for the `server` subtree (nested models);
  (b) `validate_server_block` validates the in-flight vocabulary (`endpoints`, `defaults`, `groups`, `SERVER_POLICY_PRESETS`); it is replaced by the v2 vocabulary (`preset`, `root`,
  `enable`, `disable`, `rules`, `custom`, `auth`, `agents`, `agent`, `install`, `audit`, `load`, `commands`, `llm`, `version`), and the old keys are **rejected with a targeted message** (`server.endpoints was replaced by server.rules (allow/deny over dotted op ids); see 03 section 10`). The in-flight vocabulary is part of the **unreleased** 0.3.0 (CHANGELOG `[Unreleased]`),
  so the repository's ADR `2026-09-03-no-backward-compat-capability` applies: no translator, no deprecation window (this removes the "two-minor alias window" of the first v2 draft, cut list item in [10](10-implementation-plan.md) section 3.2).
  What **is** kept for compatibility is the *released* 0.2.x behaviour (routes, bodies, groups, env toggles) through `presets.legacy_compat()` (04 section 10). The server **also** validates at load, so a hand-written `server.json` cannot bypass the client check; `server.json` carries `"schema": 1` and the runtime refuses an unknown schema.
  Values are the server's job: `check-config` runs at build time (below).
* `template.yaml` keeps its existing `custom_commands:` (template mechanism A: envd-side commands, untouched) and `capabilities:`; `server:` governs
  mechanism B (the in-sandbox server). `capabilities:` entries `shell`, `files`, `code`, `ports` do **not** implicitly mount server ops.
* Compilation: `ebx template build` (and `SandboxTemplate.build`) writes the resolved block to `/etc/easy-sandbox/server.json` in the image
  (secrets are only `*_env` names; an unset `token_env` at **runtime** refuses to start, 03 section 15.5), runs `check-config --strict` (errors fail the build, warnings print), and, when `install.mode: build`, `prepare`.
  The compile step is WP-10b and has an executable contract: `spikes/ai_consumer/s8_template_yaml.py` (unknown key -> error with suggestion) and `spikes/templates/t2_commands_git_pytest.py` (YAML -> policy -> HTTP).
* **Docker build injection for base-image templates (v2.1, IF-13, IF-22).** `api/docker_builder.py` emits, for templates whose base is the Alibaba Cloud Agent Sandbox image (or any image with an
  externally managed Python): `USER root`; `COPY` of the server wheel **from the build context** (the builder stages the wheel matching the client's pinned lockstep version; offline-capable; never
  `pip install` from an index); `RUN pip install --no-cache-dir --break-system-packages <wheel>` (or the venv variant when `server.python: venv`); `COPY server.json /etc/easy-sandbox/server.json`;
  `RUN easy-sandbox-server prepare` when `install.mode: build`; `USER user`; and the deploy descriptors `start_cmd = "easy-sandbox-server serve --port 9000"`,
  `ready_cmd = "easy-sandbox-server healthcheck --port 9000"` (`api/deploy.py`). Templates that already install the server themselves set `server.inject: false`. Exact Dockerfile: [06](06-lazy-install.md) section 8.
  Test: a builder unit test renders the Dockerfile for three bases and asserts the lines above; an opt-in E2E builds one image (WP-10b gate).
* Start/ready commands are those of the base-image design: `easy-sandbox-server serve` / `easy-sandbox-server healthcheck`; no `commands.py` is needed
  unless the author wants Python ops (then `server.py` + `load:`).
* **Declarative decorator integration (v2.1, IF-13).** The existing declarative layer (`declarative/decorator.py`: `@sandbox.register.*`, `enable_builtin`) is kept and **compiled into the same
  block**: `@sandbox.register.command("grade")` -> `custom:` entry; `enable_builtin(group)` -> `enable: ["group:<g>"]`; both go through the legacy name-mangling table (02 section 2). The decorator
  API gains one new form, `@sandbox.server.op("grader.run", effects="exec", paths=("submission",))`, which registers a Python `@op` in the module that `load:` imports. Test: the three forms produce an identical
  `server.json` (WP-10b).

## 3. Python flavour (when YAML is not enough)

```python
# server.py  (COPY into the image; `easy-sandbox-server serve --load /app/server.py`)
from easy_sandbox.server import Policy, op, ops, presets

@op("grader.run", effects="exec", paths=("submission",), summary="Grade a submission directory")
def run(ctx, submission: str, timeout: int = 60) -> dict:
    r = ctx.run(["python3", "/workspace/grade.py", ctx.paths["submission"]], timeout=timeout)   # ctx.run = admitted subprocess helper
    return {"exit_code": r.exit_code, "stdout": r.stdout[-4000:]}

policy = presets.minimal() + Policy().allow(ops.grader.run, paths="/workspace/submissions", principals=["role:grader"])
# convention: `serve --load server.py` imports the module; a module-level `policy` (Policy) becomes the author-layer policy
# (or call start(policy=policy) under `if __name__ == "__main__":`)
```

`ctx.run(argv, ...)` is the sanctioned subprocess helper for custom ops: no shell, scrubbed env, rlimits and process-group handling from the same launcher
as `commands.run`.

## 4. Journeys

### 4.1 Download-only file service

```yaml
server: {preset: download-only, root: /data}
```

Dockerfile: generated by the builder (06 section 8; PEP 668 safe) - nothing else installed. Executable: `spikes/templates/t1_download_only.py` (only download works; `files.upload` -> 404).

### 4.2 Grader / CI runner

```yaml
server:
  preset: ci-runner
  root: /workspace                  # read-only workspace by default (v2.1, B-9); writable: true is an opt-in and then commands must not run files the caller can write
  rules:
    - allow: commands.run
      commands: {allow: ["pytest -q {path}", "python3 /workspace/grade.py"], cwd: /workspace, timeout: 120s}
  auth: {tokens: [{id: ci, roles: [runner], token_env: CI_TOKEN}]}      # CI_TOKEN must be set and >= 16 chars, else the server refuses to start
```
Executable: `spikes/templates/t2_commands_git_pytest.py`.

### 4.3 Codex (or any CLI agent) behind the OpenAI Agents API

See [05](05-agents-api.md) section 12: `preset: agent-host`, `agents: [codex]`, `llm:` in `agent.codex`. Image has **no** codex baked in; first use installs it.
For a self-contained image add `install: {mode: build}` and the build runs `prepare` (**recommended on FC**). Executable: `spikes/templates/t3_codex_hosted.py`, `t4_claude_qoder.py` (the `qoder`, `qwen_code`
and `cursor` adapters are flagged experimental in `agents.runtimes.list`).

### 4.4 Several agents + browser

```yaml
server:
  preset: agent-host
  agents: [codex, claude_code]
  enable: ["browser.navigate", "browser.screenshot", "browser.content"]
  rules:
    - allow: browser.navigate
      urls: {allow: ["https://*.example.com/*"], block_private: true}
  install: {mode: lazy}
```

## 5. Local development loop

1. `easy-sandbox-server init --preset ci-runner --root /workspace > server.yaml` (annotated starter).
2. `easy-sandbox-server describe --effective --config server.yaml` - exactly which ops are mounted, with scopes (the thing the AI/human should
   *read* before shipping).
3. `easy-sandbox-server check-config --config server.yaml --strict`; `explain --op files.download --arg path=/etc/passwd [--principal ID]` to try attacks offline (**one spelling**, N-4; `serve --explain-denials` turns on verbose 404 hints in development, N-6).
4. `easy-sandbox-server serve --config server.yaml --port 9000` locally; drive with `ServerClient("http://127.0.0.1:9000")` or `ebx server call`.
5. `easy-sandbox-server doctor` inside a built image (`ebx connect` then run it) to see base-image contract, tools, writable dirs.
6. `ebx template build`.

## 6. Migrating existing templates

| Today | v2 |
|-------|----|
| `commands.py` calling `start()` with `registry.command(...)` | works unchanged **with the compatibility policy `presets.legacy_compat()`**, which is applied only when no policy is given; as soon as you add a policy, legacy `custom.*`/`ext.*` are no longer mounted unless you allow them, and **`easy-sandbox-server check-config --legacy-diff` lists exactly the v1 ops the new policy drops** (B-6; spike `legacy_diff`, `templates/t8_v1_migration.py`) |
| `commands.py` implementing a whole API (`codex-agent-api`) | delete; `preset: agent-host`, `agents: [codex]`; keep `template.yaml` env mapping as `llm:` |
| Dockerfile `RUN npm i -g @openai/codex` | remove (lazy install) or replace by `RUN easy-sandbox-server prepare` (needs network at build time) |
| Dockerfile `RUN pip install easy-sandbox-server` on the Alibaba base image | fails (PEP 668); use the builder injection (generated) or `--break-system-packages` / venv |
| `EBX_SERVER_DISABLED_GROUPS=...` env in Dockerfile | still works; prefer `disable:` |
| `capabilities: [shell, files]` | unchanged (client-side gating) |

`codex-agent-api` before/after: 15 routes hand-registered with `table.route(...)` in group `COMMANDS` (so `EBX_SERVER_DISABLED_GROUPS=commands`
would also kill them, and the default `/v1/agents/{agent_id}` literal-vs-variable order was a latent bug) -> generated from the registry, individually
policy-addressable (`agents.codex.sessions.*`), usable with the stock `openai` SDK.

## 7. Author-facing errors and lints (messages are part of the UX)

* `unknown selector 'file.list' (no such operation); did you mean 'files.list'?`
* `rule 3 allows commands.run with pattern 'python3 ...': python3 can run arbitrary code; pin the arguments or use server.custom`.
* `paths root '/' is refused: PathScope("/") raises ValueError; use PathScope.anywhere(unsafe=True) (a lint error) if you really mean it`.
* `allow(commands.run) without a CommandScope: policy.scope_required` (bare grants are refused, IS-P1).
* `agents.codex.* is allowed while files.* is jailed to /workspace: the agent process is not confined by path scopes; set agent.codex.permissions`.
* `server.auth: no tokens configured and the server will listen on 0.0.0.0: open mode`.
* `custom.grade param 'submission' type path has no root`.

## 8. Interaction with the other design tracks

* **Providers/credentials**: the sandbox *provider* is where the sandbox runs; the server's `llm:` is the model endpoint of an agent. In-sandbox variables remain
  `EBX_SERVER_*`; `EBX_LLM_*` are optional fallbacks. Nothing in `server:` mentions a provider.
* **Repository layout**: `server.json`, manifests and `operations.json` live in `server-sdk`; template validation code is generated into `client-sdk`
  (no runtime import). If the layout work introduces a shared package, the catalog moves there unchanged.
