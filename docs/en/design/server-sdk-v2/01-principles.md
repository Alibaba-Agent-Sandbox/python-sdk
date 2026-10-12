# 01 - Principles, scope and non-goals

> Part of [Server SDK v2](README.md). Authoritative over the in-flight documents it supersedes
> (see the reconciliation section in [10-implementation-plan.md](10-implementation-plan.md)).

## 1. What the server SDK is

`easy-sandbox-server` (import `easy_sandbox.server`) is the **in-sandbox runtime** of Easy Sandbox: a
stdlib-only HTTP server that runs inside a sandbox image (port 9000, PTY WebSocket on 9001) and gives
callers - the Python client SDK, the Node `ebx` CLI, the official `openai` SDK, plain `curl` - a typed,
policy-controlled surface over the sandbox: files, commands, processes, terminals, system information,
browser, developer tools, coding agents, and user-defined operations.

It is **not** an envd clone. envd (port 49983) stays the platform's data plane that
`Sandbox.files/commands` use. The server is the template author's plane. The two overlap on purpose
only where that helps (see [07-client-mirror.md](07-client-mirror.md) section 6).

## 2. The seven design rules

These rules are the tie-breakers for every decision in this set. Each is testable.

**R1. One identity per operation: a dotted ID, defined once.**
`files.list`, `commands.run`, `agents.codex.sessions.create`. The ID is the only name used in the
server registry, policy rules, the audit log, error bodies, `/capabilities`, OpenAPI `operationId`,
the generated client attribute path, and the CLI. HTTP method and path are *bindings* of an
operation, never identifiers. There is no second registry (no `KEEP = {("GET", "/health"), ...}`-style
sets of method/path tuples anywhere; a CI test greps for them).

**R2. Everything is an operation, and every operation is policy-checked by the same code path.**
Built-ins, custom commands, legacy `table.route(...)` extensions and agent calls all go through one
pipeline: transport checks (step 0: timeouts, target/Host/Origin/content-type) -> authenticate -> look up ->
validate arguments -> policy -> (limits) -> handler -> audit.
There is no route that skips the pipeline, including `/health` (it is op `core.health`, allowed by
every preset).

**R3. Absent unless enabled; enabled does not mean unconstrained.**
An operation is *mounted* only if at least one `allow` rule covers it. Unmounted operations answer
`404 op.not_enabled` and are not listed in `/capabilities` for that caller. Mounted operations can
be narrowed by scopes (paths, commands, limits, principals, hooks). Policy is **deny-overrides**,
**fail-closed** (any hook or scope error denies; an unset `token_env` refuses to start; allows over
path/command/agent-exec ops without a scope are rejected with `policy.scope_required`) and **restrict-only below the author layer**
(operators can tighten, never loosen).

**R4. Coarse is sugar for fine.**
Groups (`file_ops`, `process`, ...), presets (`readonly`, `download-only`, ...) and the legacy
`CapabilityGroup`/`enable_builtin` API are *expansions into rules over operation IDs*. Fine-grained
rules never need a group to exist, and a group never grants more than its golden list of IDs
("no privilege creep", pinned by a snapshot test).

**R5. Server and client are one schema.**
The registry emits a catalog (`operations.json`) from which the OpenAPI document, the Python client
(`ServerClient`), the TypeScript client for the Node CLI and the docs tables are generated. A contract
test replays every operation from the catalog against the real server. Hand-written client method
names that differ from the op ID are a defect.

**R6. Batteries included, never installed until used.**
The server core is stdlib-only and small. Coding-agent CLIs, a browser, Node and similar tools are
described by **manifests** and installed **lazily on first use** (or at build time by
`easy-sandbox-server prepare`, derived from the enabled operations). Nothing is downloaded at import,
at server start, or by an operation that was not enabled and called.

**R7. Boring for humans, predictable for AI coding agents.**
One obvious way to do the common thing (`presets.*`, `Policy().allow(...)`, `@op`), strings with typo
suggestions instead of silent no-ops, errors that say what to change, and a one-page reference
([09-ai-codegen-usability.md](09-ai-codegen-usability.md)) that is sufficient to write correct
configurations without reading source.

## 3. Scope

In scope:

* operation model, registry, ID grammar, aliases, generated catalog/OpenAPI ([02](02-operation-model.md));
* policy: allow/deny rules, presets, path and command scoping, per-principal rules, authorize hooks,
  limits, audit, config layering, reload, error model ([03](03-policy-and-permissions.md));
* built-in operation catalog with legacy bindings ([04](04-builtin-modules.md));
* first-class agent API: `/v1/agents/...` compatible with the official `openai` SDK, adapters for
  codex, claude_code, qoder, qwen_code, cursor and any declarative CLI ([05](05-agents-api.md));
* lazy installation, manifests, `easy-sandbox-server prepare|doctor|...`, read-only filesystems and the
  Alibaba Cloud Agent Sandbox base image ([06](06-lazy-install.md));
* the matching client surface and the Node CLI mirror ([07](07-client-mirror.md));
* template building UX ([08](08-template-building-ux.md));
* code layout, work packages, compatibility and migration ([10](10-implementation-plan.md)).

Non-goals:

* A sandbox/isolation mechanism. The server **cannot** confine a process the policy lets run; kernel-level
  isolation is the platform's job. Server scopes constrain *server operations*; see the threat model in
  [03](03-policy-and-permissions.md) section 12 for exactly what is and is not promised.
* Re-implementing the whole OpenAI Agents API (47 operations; tiered 25 implemented / 2 reserved / 5 refused / 15 not planned); the supported subset is tiered in
  [05](05-agents-api.md).
* A multi-tenant control plane. One server instance serves one sandbox with a small set of principals.
* Hot-patching operations at runtime. The registry is frozen after startup; policy reload is opt-in.
* Replacing `Sandbox.files`/`Sandbox.commands` (envd) in the client.

## 4. Vocabulary

| Term | Meaning |
|------|---------|
| **operation (op)** | A named, typed, policy-checked capability, e.g. `files.download`. |
| **op ID** | The dotted lowercase name; grammar in [02](02-operation-model.md) section 2. |
| **namespace** | An ID prefix: `files`, `agents.codex`, `agents.codex.sessions`. |
| **binding** | An HTTP method + path (or WS/SSE endpoint) that dispatches to an op. `POST /ops/{id}` always exists. |
| **effect** | A coarse tag on an op: `read`, `write`, `delete`, `exec`, `net`, `admin`. |
| **group** | A legacy coarse switch (`file_ops`, `process`, ...) = a named list of op IDs. |
| **rule** | `allow(...)` or `deny(...)` over selectors with optional scopes. |
| **selector** | An op ID, `ns.*` (one level), `ns.**` (any depth), `group:<name>`, `effect:<tag>`, or `*`. |
| **scope** | Constraints attached to an allow rule: `paths`, `commands`, `limits`. |
| **principal** | The authenticated caller: `id`, `roles`, `claims`. |
| **preset** | A `Policy` factory (`presets.readonly()`); policies compose with `+`. |
| **hook** | `authorize(ctx) -> Decision`: a *veto-only* extra check. |
| **adapter** | The per-agent-CLI plugin that builds an invocation and parses its output. |
| **manifest** | Declarative description of how to obtain a tool (npm lock, tarball + sha256, ...). |
| **LLM endpoint** | `llm:` - the model API an agent CLI talks to. (Not "provider": that word means the *sandbox backend* in the providers design.) |

## 5. Compatibility stance

* **v1 routes keep their paths and bodies** (strangler migration: baseline-and-port, compat gate on every
  work package). Because v1 defaults were over-permissive, behaviour parity is opt-in via
  `presets.legacy_compat()` (with `legacy_diff` showing what it widens); the secure default differs.
  There is no shipped rollback dispatcher and no version jump: the release is 0.3.0.
  Details: [10](10-implementation-plan.md) sections 1 and 6.
* New behaviour is opt-in via a policy, a preset, `EBX_SERVER_*`, or new operations. The only intentional
  default changes are additive (extra response keys, extra routes, universal `Authorization: Bearer`).
* Wire versions: operation IDs are append-only; renames keep the old ID as an alias; the catalog carries
  `catalog_version`. See [02](02-operation-model.md) section 9.
