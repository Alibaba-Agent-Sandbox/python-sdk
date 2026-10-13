# Review Log: Fine-Grained Capabilities, Client/Server Alignment, Base Image

> Reviewed documents: [fine-grained-capabilities.md](fine-grained-capabilities.md),
> [client-server-alignment.md](client-server-alignment.md),
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md).
> Reviewed artefact: **Draft v1** (frozen copy of the three documents taken before Round 1).
> Outcome: **v2 (reviewed)** - every finding below is either resolved in the design docs
> (section "Changes after review" at the end of each doc), or explicitly deferred with a reason.

## 0. Method and honesty note

The brief asked for two independent adversarial rounds by *fresh subagents* with different
lenses. The authoring environment exposed **no subagent-spawn facility**, so the rounds were
executed by the author as **separate, sequential passes with a deliberately hostile role per
lens**, each starting from the frozen Draft v1 and an explicit checklist, not from the
author's intent. This is weaker than a truly independent reviewer (shared blind spots are
possible), so two mitigations were applied:

* **Round 2's security lens was evidence-based, not opinion-based.** Before reviewing, an
  empirical probe (`/tmp/probe/probe1.py`) was run against the *unmodified* server: it starts a
  real `SandboxServer`, plants symlinks pointing outside the base dir and fires traversal,
  encoding, method-override and malformed-header requests. The findings (R2-S1..S6) are
  observed behaviours, not hypotheses. The same probes are turned into regression tests (see
  section 4).
* **Every resolution is test-backed.** Each "Resolved" item names the test module that locks
  it (or the doc section if it is purely documentary), so a human reviewer can audit the
  claim.

A human or independent-agent third round is recommended before a GA release (listed in the
open questions of the final report).

Severity: **H** = would ship a vulnerability or a hard incompatibility, **M** = design gap that
would cause bugs or user pain, **L** = polish.

## 1. Round 1 - Functional completeness and UX/API ergonomics

### 1a. Lens: functional completeness ("what scenario cannot be expressed or is ambiguous?")

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R1-F1 | M | The headline scenario ("expose only upload + download, download only from `/home/user/out`") needed 12 lines of JSON; nothing in the draft made it a one-liner. | `transfer-only` preset **and** `ServerPolicy.only(*endpoint_ids, **rule)` are now normative (3.4a): `only` = `"*": {enabled: false}` + enabling listed IDs, core endpoints always stay. Test: `test_policy_presets.py`. |
| R1-F2 | M | Multi-path endpoints (`files_move`, archive, search roots) were not specified: is `read_only` checked against source or destination? Which op class does each path get? | Normative table of *path roles* (3.5): `files_move` -> `src` is `delete`, `dst` is `write`; both must pass allow/deny/read-only. `files_archive` -> root is `read`, every member re-checked. Test: `test_policy_paths.py::test_move_*`. |
| R1-F3 | H | Limits were only enforced via `Content-Length`. A lying/absent length (chunked) streams unbounded data into `files_upload_stream`. | Byte limits are enforced **while streaming** (counting reader), not just up front; chunked `Transfer-Encoding` is rejected (411-class 400) on body-bearing endpoints. Partial files are removed on abort. Test: `test_policy_limits.py::test_upload_limit_enforced_without_content_length`. |
| R1-F4 | M | Custom routes (`RouteTable.route(...)`) and custom commands could not take part: no way to declare scopes, no `PathGuard` for handlers. | `RouteInfo.scopes`; `register(..., scopes=[...], endpoint_id=...)`; handlers get `request.context["policy"]` (an `EndpointContext` with `guard(path, op)`). Catalogue-less routes default to scope `custom:<name>`-free (callable by `*` identities) unless scopes are declared. Test: `test_policy_pipeline.py::test_custom_route_scopes`. |
| R1-F5 | M | `capabilities_check` appeared in the scope table but had no contract about being an oracle (must not touch the filesystem). | Contract: policy-only evaluation, no `stat`; response never says whether a path exists. Test: `test_policy_discovery.py::test_check_is_not_an_existence_oracle`. |
| R1-F6 | M | Policy reload / mutability unspecified. | Policy is immutable after start; `revision` is a content hash; operators restart (documented in 4 "Configuration"). Runtime `with_endpoint` creates a *new* policy object. |
| R1-F7 | M | Per-identity *path* scopes (token A may read `/out`, token B may read `/in`) cannot be expressed; rules are global. | **Deferred (documented non-goal for v1).** Rationale: identity x path matrix doubles the schema; the supported way is separate sandboxes or custom scopes plus separate endpoints. Recorded as open question OQ-2. |
| R1-F8 | L | Defaults for unset limits were "today's constants" but not enumerated. | Table of legacy constants added (3.6): 10 MiB JSON body, 100 MiB legacy `/download`, 10 MiB `/upload` (`EBX_MAX_UPLOAD_SIZE`), search 200 results, etc. |
| R1-F9 | L | `files_watch` requires `process`-like long-lived connections; no max duration/concurrency. | `limits.max_duration_seconds` (default 300) + `max_concurrency`. |

### 1b. Lens: UX / API ergonomics ("what would trip a new user?")

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R1-U1 | M | Typos in policy (`"alow"`, `"limit"`) silently become no-ops and look like security holes. | Closed vocabulary; unknown keys are `PolicyConfigError` with a *did-you-mean* hint and the JSON path (`endpoints.files_list.paths.alow`). Test: `test_policy_config.py::test_unknown_key_suggests`. |
| R1-U2 | M | Unknown endpoint IDs in `endpoints` (e.g. `file_download`) were silently ignored. | An exact selector matching no registered route is an error (globs matching nothing are warnings in `check-config`). |
| R1-U3 | M | Which error should a caller catch? Draft had a flat list. | Client exception tree finalised (section 7): everything derives from `ServerAPIError`; `PolicyDeniedError` carries `.code`, `.endpoint`, `.scope`, `.path`; legacy `except PermissionDeniedError` still catches file-policy denials. |
| R1-U4 | M | Pre-check "fail fast" could be surprising when the cache is stale (policy changed, client says 403 locally). | Pre-checks happen only after an *explicit* `discover()`; server stays authoritative; `ServerClient(prechecks=False)` and `caps.refresh()` exist; a stale-cache denial includes `revision` so users can diagnose. |
| R1-U5 | L | Need a debugging aid: "why was my call denied?" | `ServerPolicy.explain(...)` (server side) and `client.server.explain(...)` -> `POST /capabilities/check`; `easy-sandbox-server check-config --explain files_download_stream --path /etc/passwd`. |
| R1-U6 | L | Size strings (`5MB`) ambiguous between MB and MiB. | Decimal vs binary spelled out: `MB`=10^6, `MiB`=2^20; bare ints are bytes; documented and tested. |
| R1-U7 | L | `Sandbox.server` vs the decorator proxy name. | Verified no clash (`Sandbox` has no `server` attribute today); kept `Sandbox.server` (port 9000, lazy, cached) + `Sandbox.server_at(...)`. |
| R1-U8 | L | Sync users: need `_sync` twins for every method. | Mandatory in alignment doc; completeness test iterates all async methods. |
| R1-U9 | L | `ServerPolicy.only("download")` -- legacy route IDs `upload`/`download` vs stream IDs are easy to confuse. | `only()` accepts the alias group token `"transfer"` meaning `{upload, download, files_upload_stream, files_download_stream}`. |

**Round 1 outcome:** design updated (sections 3.4a, 3.5 roles table, 3.6, 7, 8); no finding
rejected except R1-F7 (deferred).

## 2. Round 2 - Security bypass and backward compatibility

### 2a. Lens: security bypass ("assume the policy author is competent and I am hostile")

Evidence from the probe against the unmodified server is marked **[probe]**.

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-S1 | **H** | **[probe]** `files_archive` (zip) follows *file* symlinks: a symlink in the sandbox dir pointing to `/etc/passwd` is archived with its content. Any path allow-list built on the existing code would be bypassable via the archive endpoint. Pre-existing vulnerability. | Archive refuses (skips) symlinks whose target is outside the endpoint boundary or denied; never follows directory symlinks. This is a **bug fix applied in all modes** (documented in CHANGELOG as security fix). Test: `test_path_guard.py::test_archive_does_not_leak_symlink_target`. |
| R2-S2 | M | **[probe]** `files_search`/`files_list` show names of symlinked entries pointing outside. Names leak topology. | In policy mode entries failing the guard are omitted (never descended). Legacy mode unchanged. Test: `test_policy_paths.py::test_list_omits_denied_entries`. |
| R2-S3 | **H** | **[probe]** A non-numeric `Content-Length` crashes `_read_json_body` with an unhandled `ValueError` (connection dropped, no response); a negative value is parsed as JSON error. A hostile client can use it for desync experiments and the 500 path leaks nothing but is untested. | Strict parsing: `^\d+$`, else 400; negative -> 400; duplicate differing `Content-Length` -> 400; `Transfer-Encoding` present -> 400 on body endpoints. Applies in all modes (pure bug fix; previous behaviour was an abort). Test: `test_http_hardening.py`. |
| R2-S4 | M | **[probe]** Duplicate query parameter (`?path=/ok&path=/etc/passwd`): server takes the first, while an intermediary (gateway/WAF) may take the last -> allow-list decisions made upstream differ. | In policy mode duplicated path-bearing params are rejected (`400 duplicate_parameter`). Legacy mode keeps "first wins". Test: `test_http_hardening.py::test_duplicate_path_param`. |
| R2-S5 | M | **[probe]** Existence-oracle ordering: in-boundary missing path -> 404 "File not found", out-of-boundary -> 400/403, so a caller can map the filesystem outside its allow-list. | In policy mode the boundary/deny check always runs **before** any `stat`, and outside-boundary returns the same 403 `path_not_allowed` regardless of existence. Test: `test_policy_paths.py::test_no_existence_oracle`. |
| R2-S6 | L | **[probe]** Relative paths resolve against the *server process CWD*, not `base_dir`; with `paths.allow` that is a foot-gun. | Kept for legacy mode (compat) but relative paths are resolved against the first allow root in policy mode (documented). Test: `test_policy_paths.py::test_relative_path_in_policy_mode`. |
| R2-S7 | **H** | Policy attached to the *URL string* rather than the matched route would allow encoded-route and trailing-slash discrepancies. Draft already keys by `RouteInfo`; reviewer verified the router: `%73tat` -> 404, `//files` -> 404, trailing slash normalised before matching. | Confirmed: policy key = `route.name` only; regression tests for encoded/doubled/trailing-slash routes; method override headers/params explicitly ignored. Test: `test_policy_bypass.py::test_route_confusion_*`. |
| R2-S8 | **H** | TOCTOU / symlink swap: `realpath` check then `open`. An attacker with `process:run` can race a swap. | `O_NOFOLLOW` on the final component; after open compare `fstat` identity with `/proc/self/fd/N` resolution and re-run the boundary check on it; `symlinks: never` additionally rejects any symlink component (lstat walk). **Residual risk documented**: intermediate-component swap between check and open can't be fully closed in pure-stdlib Python; mitigation is not exposing `process`/`terminal` alongside path scoping (lint L1). |
| R2-S9 | M | Hardlinks inside the allowed tree to outside inodes are invisible to path checks. | Residual risk documented (only creatable via process endpoints; covered by lint L1). `files_*` endpoints can't create hardlinks. |
| R2-S10 | M | Deny globs: case variants, `./`, trailing-slash, and matching against the lexical vs resolved path. | Deny is evaluated on the **resolved** path *and* the normalised lexical path; matching is case-sensitive on POSIX (documented; macOS dev machines note); basename patterns (`*.pem`) match any component; directory denies are prefix-with-separator matches (`/a/b` does not deny `/a/bc`). Tests with each variant. |
| R2-S11 | **H** | Token confusion: draft allowed `Authorization: Bearer` and `X-Access-Token` simultaneously; behaviour with two differing `X-Access-Token` headers undefined. | Identities mode: more than one distinct credential header value -> 400 `ambiguous_credentials`; Bearer wins only when `X-Access-Token` absent or equal (draft said "Authorization is used" - changed: gateways inject their own `X-Access-Token`; ordering is `Authorization` first, documented). Legacy mode untouched (first `X-Access-Token`). |
| R2-S12 | M | Timing side-channel on token lookup with several tokens. | Digest-then-`compare_digest` over all tokens with no early exit (kept); tested structurally. |
| R2-S13 | **H** | Secrets exposure: `GET /env` (system group) returns the whole environment including `EBX_SERVER_TOKEN` and other identities' `token_env`; child processes inherit them. | In policy-identities mode `env_get` redacts `EBX_SERVER_*`, `EBX_*TOKEN*` and every configured `token_env`; child env is scrubbed (3.10). `env_set` refuses to set those names. Legacy mode unchanged (compat) but lint recommends policy. Test: `test_policy_env.py`. |
| R2-S14 | M | PTY WebSocket (port 9001) has its own auth (`?token=` in URL: token lands in access logs and gateway logs) and would bypass endpoint policy. | PTY server consults the same policy: identity from `Authorization: Bearer` / `X-Access-Token` header (new) or the legacy query token; requires scope `terminal:use`; endpoint `pty_connect` rule `enabled:false` closes the socket with 4003. Query token still accepted (compat) but flagged by the discovery `warnings`. Test: `test_policy_pty.py` (uses websockets client). |
| R2-S15 | M | Policy file integrity: a writable policy file lets the in-sandbox user relax the policy. | `check-config` and startup lint warn if the policy file or its directory is writable by the server's uid; documented to place it root-owned 0644 in `/etc/easy-sandbox/`. |
| R2-S16 | M | `/proc`, `/sys`, `/dev` exposure when allow roots are broad (`/`); `/proc/self/environ` leaks tokens. | Lint L2 on allow root `/`; `hardened` preset denies `/proc`, `/sys`, `/dev`, `**/.ssh`, `**/.env*`, `**/*.pem`, `**/id_*`. |
| R2-S17 | L | Very long paths / glob selector CPU (ReDoS). | Path length cap 4096; selectors use `fnmatch` over short IDs; deny patterns are `fnmatchcase` with no regex from user input. |
| R2-S18 | L | Audit log injection through path strings. | JSON-encoded lines (escaping by construction); paths truncated to 512 chars. |
| R2-S19 | L | Brute-forcing tokens: no failed-auth throttle. | **Deferred**: gateway-fronted deployment; per-IP throttling in a stdlib server is unreliable behind a gateway. Documented; constant-time comparison + high-entropy token guidance in docs. |
| R2-S20 | L | Unicode look-alikes / normalisation. | POSIX paths are bytes without normalisation, so look-alikes name *different* files; no confusable bypass. Documented (macOS HFS+ normalisation caveat). |

### 2b. Lens: backward compatibility ("what existing user breaks?")

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| R2-C1 | **H** | Existing tests (`test_env_subprocess_boundary.py`) wire `ThreadingHTTPServer(..., SandboxRequestHandler)` and set only `auth_token` and `registry`. New attributes (`policy`, `audit`) must not be required. | Handler reads every new attribute through `getattr(self.server, ..., None)`; `None` policy = legacy pipeline. Test: existing suite + `test_policy_compat.py::test_bare_handler_wiring`. |
| R2-C2 | M | `RouteInfo` is a public dataclass constructed positionally by third parties; inserting a field breaks them. | New fields appended **after** existing ones with defaults; `RouteTable.register` keyword-only additions. |
| R2-C3 | M | `GET /capabilities` consumers may assert exact keys. | Existing keys unchanged (`groups` remains), additions are new keys; pinned by an exact-superset test. |
| R2-C4 | M | Error bodies gain `code`; clients doing equality on the body dict break. | Existing keys/values unchanged, `code` only added where a stable code exists; documented as additive. |
| R2-C5 | M | `EBX_SERVER_DISABLED_GROUPS` precedence vs policy `groups`. | Env kill switch always wins (draft kept) - tested both directions. |
| R2-C6 | M | `Image()` default base: draft tied default to ubuntu; changing to official base would silently change every build. | Default **unchanged**; new `Image.official_base()`; `DockerBuilder` emits a *warning* (not error) when the base isn't official (3 in base-image doc). |
| R2-C7 | M | Server must remain stdlib-only and Python 3.10+: no `tomllib` (3.11), no PyYAML hard dependency. | JSON-only parser in the server; YAML accepted only if PyYAML importable; no new dependencies. Verified by `test_stdlib_only.py` (import scan). |
| R2-C8 | M | Lockstep versions: new client against old server (and vice-versa). | Client treats a missing `endpoints` key as `legacy` and never sends new parameters (`cwd`, `env`, ...) unless the caller sets them; new endpoints on an old server surface as `EndpointNotAvailableError` (404 mapped), never a raw HTTP error. Test: client test with a stub legacy server. |
| R2-C9 | L | `SandboxTemplate` strictness: adding `server:` must not reject current templates; `server:` content must be validated lazily to keep the client free of server imports. | Optional field with `dict` schema validated by a small structural validator in the client (shared vocabulary constant), not by importing the server package. |
| R2-C10 | L | Existing `enable_builtin`/`_enabled_builtins` legacy toggles. | Still map to groups; policy `groups` applies after them. |

**Round 2 outcome:** two **H** security items were pre-existing bugs (R2-S1, R2-S3) and are
fixed in all modes (not only policy mode) because they are strictly bug fixes - this is the
only place "unconfigured behaviour" changes, and in both cases the old behaviour was a leak /
crash. All other changes are gated on a policy being configured.

## 3. Review of the alignment and base-image documents

Both were reviewed in the same two rounds. Material findings:

| # | Doc | Finding | Resolution |
|---|-----|---------|------------|
| R-A1 | alignment | `process_output` and `process_stdin` were proposed as server additions without saying how they interact with `capture_output` limits. | Spec added: bounded ring buffer (`limits.max_output_bytes`, default 1 MiB per process), cursor-based reads. |
| R-A2 | alignment | Client `ServerClient.files.download` vs the envd-backed `Sandbox.files.read` look interchangeable to users. | Documented in the matrix (section 5) with a decision table: envd is the default for code that must work on any sandbox; `ServerClient` for template-authored policy-scoped access. |
| R-A3 | alignment | Streaming methods need cancellation semantics. | Async generators close the response on `aclose()`; sync twins return iterators with `close()`. |
| R-B1 | base-image | Decision "warranted" was backed mostly by inference about the gateway; the claim "gateway forwards `Authorization`" is unverified. | Marked as open question OQ-3; the server accepts both headers so either gateway behaviour works. |
| R-B2 | base-image | `Image()` default change (security of existing builds). | See R2-C6. |
| R-B3 | base-image | Console script `easy-sandbox-server` must not shadow `ebx`. | Name checked: no clash. |
| R-B4 | base-image | Reviewer attack: `check-config`/`healthcheck` subcommands must not need network or heavy imports (used as Docker `HEALTHCHECK`). | `healthcheck` uses only `urllib.request` against `127.0.0.1`, 2s timeout, exit code 0/1. |

## 4. Test traceability

Server (`server-sdk/tests/test_server/`): `test_policy_config.py`, `test_policy_presets.py`,
`test_policy_pipeline.py`, `test_policy_paths.py`, `test_path_guard.py`, `test_policy_limits.py`,
`test_policy_discovery.py`, `test_policy_env.py`, `test_policy_pty.py`, `test_policy_bypass.py`,
`test_policy_compat.py`, `test_http_hardening.py`, `test_new_endpoints.py`, `test_cli_main.py`.
Client (`client-sdk/tests/`): `test_server_client_e2e.py` (real in-process `SandboxServer`),
`test_server_client_models.py`, `test_server_capabilities.py`, `test_base_image.py`. The
tests that were actually written are indexed in the final report; any item above whose test
could not be written is listed there as deferred.

## 5. Open questions carried forward

* **OQ-1** Default tag for `OFFICIAL_BASE_IMAGE` (`:latest` vs pinned) - needs platform confirmation.
* **OQ-2** Per-identity path scopes (R1-F7).
* **OQ-3** Does the gateway forward `Authorization`? (R-B1)
* **OQ-4** Behaviour of gateway CMD/ENTRYPOINT when a template sets its own `start_command`.
* **OQ-5** A truly independent third review (human or fresh agent) before GA.
