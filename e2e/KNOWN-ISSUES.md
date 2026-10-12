# Known issues recorded by the E2E suite

The suite pinned every product defect it found as a **strict `xfail`** (`@pytest.mark.known_issue`).
When the defect is fixed the test flips to XPASS and fails the run (strict), forcing whoever fixed it
to delete the marker, which keeps this list honest. Issues marked *platform* or *environment* are not
SDK bugs; their tests are non-strict or skip with the reason.

> 中文版本:[KNOWN-ISSUES.zh-CN.md](KNOWN-ISSUES.zh-CN.md).

Observed on the real cloud (cn-hangzhou, envd 0.5.2, template `python-hello`) on 2026-10-12 with the
SDK sources in this repository.

| ID | Kind | Summary | Test(s) | Expected after the fix |
|---|---|---|---|---|
| KI-001 | SDK bug (**fixed**) | `sandbox.commands.run(cmd, env={...})` sends the variables as `envVars`; envd expects `envs`, so per-call environment variables are silently dropped | `test_03_commands.py::test_run_with_per_call_env` | `printenv` inside the command shows the value |
| KI-002 | SDK bug (**fixed**) | `files.list` / `files.get_info` do not understand envd's numeric entry type: directories are reported as `file`; `get_info` ignores the nested `entry` object (name/path come back blank) | `test_04_files_envd.py::test_list_and_stat_report_directory_type` | directories are `directory`, `get_info` returns the real name/path/size |
| KI-003 | SDK bug (**fixed**) | a command that exceeds its timeout surfaces as a raw `httpx.ReadTimeout`; `CommandTimeoutError` is never raised | `test_03_commands.py::test_command_timeout_raises_command_timeout_error` | `CommandTimeoutError` |
| KI-004 | SDK bug (**fixed**) | `commands.kill`, `send_signal`, `send_input` post a flat `{"pid": N, ...}` body, but envd needs `{"process": {"pid": N}, "signal": ..., "input": {...}}`; they never reach the process (envd: `process not found`). Real processes keep running | `test_03_commands.py::test_kill_and_signal_terminate_a_process[kill|signal_term|signal_kill]`, `::test_send_input_reaches_stdin` | the process terminates / receives stdin |
| KI-005 | SDK bug (**fixed**) | not-found conditions leak raw `httpx.HTTPStatusError` (404): `Sandbox.connect()` on a missing sandbox, `files.read` of a missing file | `test_01_platform.py::test_connect_to_missing_sandbox_raises_sdk_error`, `test_04_files_envd.py::test_read_missing_file_raises_sdk_file_error` | an SDK `SandboxError` subclass (`FileNotFoundError_` for files) |
| KI-006 | SDK bug (**fixed**) | a 401 from the platform surfaces as raw `httpx.HTTPStatusError`, not `AuthenticationError` (the CLI maps it, the SDK does not) | `test_01_platform.py::test_wrong_api_key_raises_authentication_error` (a companion test asserts the raw 401 is at least visible) | `AuthenticationError` |
| KI-007 | SDK bug (**fixed**) | `files.list` of a missing directory returns `[]` (envd answers 200 with no entries) instead of raising | `test_04_files_envd.py::test_list_missing_directory_raises` | `FileNotFoundError_` |
| KI-008 | platform / gateway | an envd upload of 1 MB or more exceeds the default 30 s HTTP timeout from the test VM (throughput limited); 400 KB passes. Non-strict because it depends on network throughput | `test_04_files_envd.py::test_one_megabyte_upload_within_default_timeout` (`e2e_slow`) | passes within the default timeout, or the timeout becomes size-aware |
| KI-009 | platform | the Jupyter code-interpreter service answers HTTP 404 on this cloud, so `run_code` falls back to a shell and the value of a trailing expression (`21*2`) is not returned; stdout works | `test_05_network_and_code.py::test_run_code_returns_last_expression_value` | `results[0].text == "42"` |
| KI-010 | SDK bug (**fixed**) | `@sandbox` on an `async def` function: the generated remote script calls the coroutine function without awaiting it, so the result is the string `<coroutine object ...>` | `test_07_declarative.py::test_async_decorated_function` | real return value |
| KI-011 | environment | pushing real image layers from this environment to personal ACR crawls at about 17 KB/s (small layers deduplicated by an earlier push succeed), so the Docker custom-template flow cannot finish in a reasonable time. The suite probes this with a 2 MB random-layer canary push (`E2E_CANARY_PUSH_TIMEOUT`, default 120 s) and **skips** the whole `e2e_docker` module with the exact reason | `test_08_custom_template_docker.py` (`e2e_docker`, `e2e_slow`) | with a registry path that has normal bandwidth the canary passes and the flow runs |

Notes

- KI-001 to KI-007 and KI-010 are **fixed** in `client-sdk/src` (CHANGELOG `Unreleased` > `Fixed`); their `xfail` markers are
  removed, so those tests are ordinary tests now and guard against regressions (unit-level regression tests:
  `client-sdk/tests/test_known_issues/`). Verification: `.agents/evidence/verify/2026-10-12-ki-sdk-fixes.md`. KI-008 now also
  surfaces as a clear `FileOperationError` naming `EBX_HTTP_TIMEOUT` instead of a bare httpx timeout (the timeout itself is unchanged).
  New SDK behaviour worth knowing: envd can only deliver SIGTERM/SIGKILL (other signal numbers raise `ValueError`), and envd's
  process ids are its own counters, not OS pids.
- The Python oracle CLI inherits KI-002 (`ebx sandbox files stat` prints blank name/path; directories listed as `file`), see `cli/e2e/BASELINE.md`.
