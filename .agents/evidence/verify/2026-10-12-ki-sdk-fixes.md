# Verification: SDK defects KI-001 to KI-007 and KI-010 fixed (python-sdk client-sdk)

- Date: 2026-10-12
- Change: fixes of the defects pinned by the real-cloud E2E suite ([`e2e/KNOWN-ISSUES.md`](../../../e2e/KNOWN-ISSUES.md)); CHANGELOG `Unreleased` > `Fixed`
- Result: PASS for the eight fixed defects; one throughput-bound test is environment-flaky (KI-008, see below)
- Package under test: `easy-sandbox` (`client-sdk`) installed editable from the working tree
- Environment: real Alibaba Cloud FC agent sandbox platform (cn-hangzhou, envd 0.5.2), Python 3.11, Linux. Credentials from the gitignored `.env` (values not recorded)

## Protocol evidence (captured from a real sandbox)

- `ListDir` entry: `{"name","path","type":2,"size":4096,"mode","permissions","owner","group","modifiedTime"}` (`type` 1 = file, 2 = directory, number); `Stat` -> `{"entry": {...}}`; `Stat` of a missing path -> HTTP 404 with an empty body; `ListDir` of a missing path -> HTTP 200 `{"entries": []}`.
- `Process/List` -> `{"processes":[{"config":{"cmd","args","cwd","envs"},"pid":1,"tag":""}]}`: envd pids are its own counters (1, 2, 3, ...), not OS pids; the `config` key is `envs` (confirms KI-001).
- `SendInput` with a nested selector and an unknown pid -> HTTP 404 `process not found`; `SendSignal {"process":{"pid":N},"signal":"SIGNAL_SIGKILL"}` on a running `sleep` ends the stream with an `exit` event and empties `List`.

## Commands run

```bash
cd client-sdk && python -m pytest tests -m "not integration"      # 2222 passed, 1 skipped, 1 failed (see below)
cd client-sdk && python -m pytest tests/test_known_issues          # 81 new regression tests, all pass
cd client-sdk && ruff check src tests && mypy src/easy_sandbox/    # clean
cd e2e && python -m pytest -m "e2e and not e2e_docker and not e2e_slow" -ra     # fast path (make e2e)
python scripts/e2e-cleanup.py --all-tagged                         # dry run: 0 leftovers
```

## Results

| Run | Selection | Result |
|---|---|---|
| unit | `client-sdk` `-m "not integration"` | 2222 passed, 1 skipped, 1 failed: `test_agent/test_mcp_stdio.py::...ping_is_answered_while_a_tool_call_is_in_flight` fails identically before any of these changes (baseline: 2141 passed, same single failure) |
| unit | `client-sdk/tests/test_known_issues/` (new) | 81 passed (KI-001 ... KI-008, KI-010) |
| real cloud | `test_03_commands.py` (17 tests) | 17 passed, including the formerly xfailed `per_call_env`, `command_timeout_raises_command_timeout_error`, `kill_and_signal_terminate_a_process[kill/signal_term/signal_kill]`, `send_input_reaches_stdin`, plus the new `timed_out_command_is_not_left_running` |
| real cloud | `test_01_platform.py` | all passed, including `wrong_api_key_raises_authentication_error` and `connect_to_missing_sandbox_raises_sdk_error` (now `SandboxNotFoundError`) |
| real cloud | `test_04_files_envd.py` | `list_and_stat_report_directory_type`, `read_missing_file_raises_sdk_file_error` (`FileNotFoundError_`), `list_missing_directory_raises` (`FileNotFoundError_`) pass; see the throughput note |
| real cloud | `test_07_declarative.py` | `async_decorated_function` passes (`42`) |
| real cloud | fast path `make e2e` selection | 79 passed, 1 xfailed (KI-009, platform), 1 failed (`test_medium_file_roundtrip_matches_remote_checksum`, see below) |

## Throughput-bound test (not a regression)

`test_medium_file_roundtrip_matches_remote_checksum` uploads 400 KB. From this host the upload rate measured 20-30 s for 400 KB in the later runs (it passed in the first run after the fixes), i.e. right at the 30 s default HTTP timeout (KI-008). It now fails with `FileOperationError: Upload to <path> (400000 bytes) timed out; the transfer took longer than the HTTP timeout` plus the `EBX_HTTP_TIMEOUT` hint instead of a bare `httpx.ReadTimeout`. The upload code path is otherwise unchanged.

## Test-suite fixes made on the way

- `e2e/test_03_commands.py`: the helpers started processes and picked `procs[-1]` of a list shared with earlier tests of the module, and force-killed with `kill -9 <pid>` although envd pids are not OS pids; they now pick the process whose pid was not listed before and force-kill through `commands.send_signal(pid, 9)`. This is what made the first post-fix run flaky for the process-control tests.

## Cleanup

Every sandbox was tracked and deleted by the session finalizer (`leaked_after_cleanup=0` in every run); `python scripts/e2e-cleanup.py --all-tagged` reports no tagged sandbox. Probe sandboxes created while investigating were killed in `finally` blocks.

## Not fixed / out of scope

- KI-008 (gateway throughput), KI-009 (Jupyter service 404), KI-011 (ACR push bandwidth): platform/environment, unchanged by design; KI-008 is only reported more clearly.
- `commands.run(timeout=...)` is an inactivity limit (no output for `timeout + 5` s), not a wall-clock deadline: a chatty command is never timed out. Pre-existing, outside KI-003.
- `ProcessInfo.command` stays empty (envd nests it under `config.cmd`); not part of the recorded issues.
