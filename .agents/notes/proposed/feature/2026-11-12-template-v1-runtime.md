# Decision: Consume canonical v1 resources in prepared launch and Managed Sessions

Status: proposed

## Problem

The template owner now defines public `specVersion: 1` resources, but Python launch,
discovery and registry loading still require flat specification5 fields. Managed Sessions
ignore instance CPU/memory/disk/GPU, existing Volumes and metadata. Their native Sandbox
TTL comes from a separate private budget. Persisting the resolved instance wholesale would
also copy custom environment values into durable Session state.

## Decision

Bundle immutable template-owner normalizer/schema bytes and their Git/hash lock. Validate
with actual JSON Schema; consume literals or a Devs-resolved v1 snapshot without installing
the CLI or interpreting a second expression language. Python does not prepare source or
partially execute Serving intent. Separate template preparation props from runtime instance
settings. Apply explicit API overrides before resolved validation and retain existing
startup/readiness, ownership journaling, uncertainty and cleanup behavior.

Managed configuration snapshots only safe instance settings and custom environment names.
The Worker receives environment values from a distinct private FILE/JSON source, validates
exact names and injects them into the native Sandbox and bridge process. Protect system
credentials, model controls, ownership tags, the exclusive workspace and private runtime
state. Existing Volumes remain borrowed resources and are never deleted by Session cleanup.

## API Design

`launch_template` accepts public v1 documents. `timeout=None` preserves `instance.timeout`
(default300 for ordinary launch); explicit CPU/memory/disk/GPU/mount values replace their
instance fields, while explicit env/metadata maps merge by name. Instance overrides receive
resolved schema validation before journaling or creation. Unresolved `${...}` input fails;
an explicit literal API override may replace that value without evaluating it.

Compiled `ManagedConfig` accepts `instance` without `envs`, and `instanceEnvNames`.
Managed TTL defaults3600; private `sessions.maxLifetimeSeconds` is derived and must agree
when both are explicitly supplied. Session `_settings` retains the safe instance snapshot
and names. Only Worker mode loads `ABX_MANAGED_SANDBOX_ENV_JSON` or `_FILE`; it never
forwards the host environment wholesale. `ExpressBackend(..., instance_env=...)` validates
the current Session's declared names before infrastructure I/O.

Managed lifecycle is secure, kill-on-timeout, without auto resume. Conflicting/unsupported
fields fail. User tags cannot replace `abx-managed`, `abx-session`, `abx-revision`. Mounts
cannot overlap the workspace or `/home/user/.agent-sandbox`, including ancestors and
children. The current mount shape has no read-only flag; shared data mounts may be writable
and are not independent tenant storage boundaries.

The optional synchronous `Provider.validate_template_input(stage, value)` seam binds actual
version-specific schemas to the selected Provider. The inherited unavailable default is not
counted as a validator. Missing unknown-plugin validators, false/raised rejection and async
returns fail before creation. This adds no operation claim or automatic vendor-field mapping.

Discovery validates canonical intent and derives service information without resolving
native expressions, credentials or cloud capabilities. The standalone server policy helper
remains available; root `server` is not silently added to the public resource schema.

## Alternatives considered

- Reimplement the v1 schema/defaults in Python: rejected; source ownership and shared
  vectors require immutable producer bytes and an actual validator.
- Install or shell out to the full CLI for prepared literals: rejected; no source build or
  expression execution is needed. Native expressions require the real Devs parser.
- Persist all resolved env values or put them in deployment plans: rejected; arbitrary
  custom environment values are sensitive even without a secret-looking name.
- Ignore lifecycle, mounts, instance values or unsupported Serving declarations: rejected;
  successful parsing must not claim configuration was actually applied when it was dropped.
- Change Agent turn/cancel state machines to address a timing observation: outside this
  migration; preserve existing assertions, record the observed failure and retest.

## Dependencies

Client base dependency `jsonschema>=4.23,<5`; no new cloud resource, model adapter or release.
Producer: [template contract PR310](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/310),
fixed [e925051](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/e9250512967d4c4abb59672567d68ba3e7d18473).
Previous narrow API patch: [SDK PR163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/163).
Cross-repository delivery: [templates309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).
SDK-owned generic launch JSON/vectors must be synchronized by CLI/Registry consumers after
this scoped source is committed; old private planner projections are not the new public YAML.

## Test Strategy

Run shared owner admission vectors with the installed SDK's real JSON Schema validator.
Exercise launch through the actual Express HTTP serializer with an HTTP mock, checking
runtime specs, TTL/defaults/overrides, env, metadata and named Volume mounts rather than
field existence. Check no env values in plans/journals/settings/ownership receipts, no Volume
DELETE, malformed or unresolved input rejected before resource creation, and unchanged
cleanup on failure. Use actual temporary SQLite and PostgreSQL for Session snapshots.
Run both package suites and full local CI, packaging/fresh installs, type/lint/format,
health/hygiene, source hash verification and secret/diff checks. Cloud/model end-to-end
acceptance remains a separate required gate of the encompassing delivery.

## Acceptance criteria

- Canonical source bytes and lock match the reviewed producer commit.
- Prepared literals work without CLI installation or source building; no silent expression evaluation.
- Actual creation bodies contain declared instance fields and correctly prioritized overrides.
- Managed native TTL equals the Session lifetime snapshot, including default behavior.
- Custom env values exist only in Worker private memory and actual guest requests.
- Reserved controls and protected directories cannot be overridden; borrowed Volumes survive cleanup.
- Discovery and bilingual SDK guidance use v1; independent server/Provider APIs remain intact.
- Local and remote required checks, skips and the outstanding real-cloud gate are reported separately.

## Evidence

[Verification](../../../evidence/verify/2026-11-12-template-v1-runtime.md).
