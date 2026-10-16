# Verification: provider management final review and Volume mount parity

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34
- Result: PARTIAL; real storage acceptance and current-revision remote checks/review remain outstanding.
- Revision: scoped uncommitted mount follow-up on `25fd4b6`; six source files in
  `client-sdk/src/agent_sandbox/{api/sandbox.py,models/sandbox.py,engine/client.py,engine/server.py,engine/engine.proto,engine/engine_pb2.py}`,
  `client-sdk/tests/test_api/test_volume_mounts.py`, and `client-sdk/tests/test_engine/test_engine.py`.
  The opt-in cloud scenario is `e2e/test_09_volume_mounts.py`; documentation and this record accompany the change.
- Environment: Linux, Python 3.13.13, existing development environment; packages remain 0.3.0.
  Tests used both source directories on `PYTHONPATH`. No runtime dependency changed.

## What was verified

Final review identified a missing distinction: Volume management does not mount a Volume
when a sandbox is created. The public Python creation API now accepts a mount-path to
existing Volume-name dictionary. Validation runs before provider lookup/construction;
unsupported providers fail E8004 before loading their implementation. The existing built-in
gRPC lifecycle carries additive map field 16, and the Python model emits the documented
`volumeMounts: [{name, path}]` REST shape. Omitted/empty hints preserve prior requests.

Another review found that an already-running older gRPC engine would silently discard an
unknown protobuf field. `HealthStatus.supported_create_options` field 4 now advertises mount
support. Nonempty hints require that capability before Create, with a five-second Health RPC
deadline; absent support fails E8004 with an upgrade/restart suggestion. No existing process
or socket is replaced. Calls without mounts retain prior behavior.

Schemas remain structurally validated by Python; the shared Node host performs authoritative
Ajv compilation. The built-in Python lifecycle remains gRPC and does not change to the Node
HTTP engine used by provider management commands. Earlier verification and remote results for
`25fd4b6` apply to that older revision, not these new mount changes. The original
[verification evidence](2026-10-16-provider-management-commands.md) is preserved unchanged.

## Commands run

Commands below used the development tools on `PATH` and client/server source directories on
`PYTHONPATH` as appropriate. Make targets were run from the repository root; the full client
suite was run from `client-sdk`.

| Command | Result | Evidence and limitations |
| --- | --- | --- |
| `python -m pytest client-sdk/tests/test_api/test_volume_mounts.py client-sdk/tests/test_engine/test_engine.py client-sdk/tests/test_models/test_sandbox.py client-sdk/tests/test_protocol/test_sandbox.py -q --tb=short` | PASS | Final rerun: 82 passed in 5.28s; includes the final bounded Health negotiation. |
| `make lint format-check typecheck` | PASS | Both packages; mypy checks 56 server and 84 client files. The older environment's server unused-ignore failure does not reproduce here. |
| `make test` | FAIL | Server phase: 847 passed, 8 failed in 373.27s. Make stops before the client phase; failure details below. |
| `cd client-sdk && python -m pytest tests -q --tb=short` | PASS; concurrent observation | 1981 passed, 23 skipped, 47 warnings in 261.21s, while the server suite also ran. Collected before the final Health-timeout-only refinement; the final 82-test rerun covers that refinement. A separate client-only run follows below. |
| Full client suite alone, without a socket override | FAIL | 9 failed, 1972 passed, 23 skipped in 258.64s; no warning summary. All failures are existing mocked lifecycle tests receiving E1001 through a live default gRPC engine instead of their local HTTP patches. |
| Same ten `tests/integration/test_e2e.py` tests with `ABX_ENGINE_SOCKET` pointing to a unique temporary directory | PASS | 10 passed in 2.07s. No source change or unknown process termination was needed. |
| `make hygiene` | PASS | No local paths or credential-like strings reported. |
| `make build` | PASS | Both sdists and wheels built; no runtime dependency or package version change. |
| `env -u PYTHONPATH make dist-check` | PASS | Final build and distribution rerun includes the five-second Health refinement. Four archives pass twine; both typed wheels install together and import from temporary site-packages. |
| `bash scripts/check-repo-health.sh` | FAIL | Final result: 105 PASS, 1 WARN, 1 FAIL; only the existing archived OpenSandbox English/Chinese mismatch remains. All new relative links and record references resolve. |
| Pinned Ruff 0.4.9 check/format and Bandit 1.7.7 on changed Python source/tests and the E2E scenario | PASS | Reproduces hook tool versions without changing hook configuration. Existing audited boundaries received precise line annotations described below. |
| `ruff check e2e/test_09_volume_mounts.py` and `ruff format --check e2e/test_09_volume_mounts.py` | PASS | The new opt-in cloud scenario satisfies style checks independently of package-only Make targets. |
| Compile the embedded E2E probe and execute it against an ordinary temporary directory | PASS | Rejects the missing exact kernel mount and creates no sentinel. This is a negative local harness check, not storage E2E. |
| `ABX_E2E_VOLUME_MOUNT=0 python -m pytest e2e/test_09_volume_mounts.py -q -ra --tb=short` | SKIPPED | One skipped: missing `ABX_SANDBOX_API_KEY`. Storage prerequisites also remain unavailable; no cloud calls or resource creation occurred. |
| `git diff --check` | PASS | No whitespace errors in the scoped follow-up. |

The protobuf descriptor was regenerated using isolated tooling `grpcio-tools==1.83.0`, whose
`libprotoc 35.1` matches the checked-in Python gencode version 7.35.1. Only `--python_out` was
needed because service definitions did not change. Generation used
`python -m grpc_tools.protoc -I client-sdk/src --python_out=client-sdk/src client-sdk/src/agent_sandbox/engine/engine.proto`.
This tooling is not added to runtime dependencies.

## Problems found and required gates

The eight server failures concern raw HTTP/WebSocket framing, policy compatibility and
secret-environment subprocess behavior, in untouched server source. Several receive
environment-generated HTTP 501 instead of the local server response; others return no
response, or the compatibility test finds no configured app. Their exact test names are:

- `test_app_agents_transport.py::TestResponsesWebSocket::test_upgrade_without_a_key_is_a_400_not_a_hang`
- `test_app_agents_transport.py::TestResponsesWebSocket::test_token_is_required_for_the_upgrade`
- `test_http_hardening.py::TestContentLength::test_valid_still_works`
- `test_http_hardening.py::TestPolicyModeFraming::test_transfer_encoding_rejected_in_policy_mode`
- `test_http_hardening.py::TestBodyLimit::test_lying_content_length_cannot_exceed_cap`
- `test_policy_compat.py::test_unconfigured_server_still_has_the_one_engine`
- `test_policy_exec.py::TestSecretEnvironment::test_server_secrets_never_reach_children`
- `test_policy_pipeline.py::TestAuthentication::test_ambiguous_x_access_token_rejected`

The concurrent full-client run's warnings include background test threads failing to bind
loopback port 9001 already in use. The client-only run has no warning summary, consistent
with fixture contention in the concurrent run; the concurrent warnings are not attributed
to a baseline product defect. That client-only run instead found nine mocked lifecycle
tests receiving an E1001 `/sandboxes` response through the default gRPC engine rather than
their current process's patched HTTP layer. Running the same ten cases on an explicitly
unique socket passes. We infer shared default-socket reuse across tool processes, whose
PID namespaces do not guarantee filesystem-unique socket names. No source workaround or
unknown process termination was used. A final full run uses a fresh unique socket and
runs sequentially. The 23 skips include two opt-in Node command tests without an explicitly
configured compatible binary; earlier Node-engine evidence remains historical.

An initial health check ran before this new evidence file existed and therefore reported
two task-owned missing-record/link failures in addition to the pre-existing archived
OpenSandbox English/Chinese mismatch. The final health check must supersede that transient
result; missing-record failures are not described as baseline failures.

Pinned Ruff requires a precise E721 exception for intentional exact-dictionary validation,
and its older TCH003 spelling for the existing Pydantic runtime datetime import. Bandit
flagged four pre-existing boundaries newly covered by the changed-file scan: the local
Python module subprocess import/launcher, the pytest-only Unix socket path hardened to
owner-only mode, and a terminal executable parameter named `shell` that is not subprocess
`shell=True`. Each received a narrow explanatory annotation after review. No scanner
configuration, selected check or runtime behavior was relaxed.

## Cleanup

The mount regressions use local mocked or loopback services. The real gRPC loopback tests
release their test-owned sessions and close their HTTP listeners. They do not create cloud
resources. The E2E scenario is opt-in and was skipped. When enabled with existing storage,
it first requires an exact kernel mount, uses an exclusive no-follow sentinel and bounded
read, checks inode ownership before unlinking, then independently checks cleanup. Existing
Volume metadata and pre-existing customer files are not targeted. The existing tracker
independently kills its tagged sandbox even if marker cleanup fails.
The full server suite generated an untracked five-byte `server-sdk/out.txt`; its bytes were
checked against the existing test fixture's literal payload before deletion. No other
untracked or pre-existing file was removed.
The failed mocked-lifecycle run observed authentication rejection rather than a successful
sandbox creation; it is not a real-cloud acceptance run. No cloud success or cleanup of
unrelated resources is inferred from it.

## Not verified

Real Volume mount/read/write/cleanup, storage permissions and role/runtime prerequisites,
current mount revision's remote CI/interpreter matrix and required review. No cloud mount
success, fully green repository gate set, current revision CI pass or merge is claimed.
