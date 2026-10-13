# OpenSandbox provider: adversarial end-to-end notes

> Status: archive. Not the current specification.

> **Status: test record, not the current specification.** Notes from one end-to-end run on 2026-10-13. The plugin under test lives in the awesome-providers catalog, not in this repository. Some error codes below were superseded by the later re-run noted at the end of this page. The normative provider design is [providers-and-credentials.md](../design/providers-and-credentials.md). Chinese status page: [zh](../../zh/archive/opensandbox-e2e-adversarial.md).

Recorded 2026-10-13 against a local OpenSandbox server (`opensandbox-server==1.1.1`, Docker runtime, `opensandbox/execd:latest`, image `python:3.12-slim`). The plugin under test is [alibaba-agent-sandbox/awesome-providers](https://github.com/alibaba-agent-sandbox/awesome-providers) `opensandbox/`. Only failures that were reproduced are listed. Design docs were not treated as evidence.

The catalog commit that contains the entrypoint fix is `7f095cbe30ac4c8a22abbb20945546185cd0151a`. Catalog `main` at the end of this run was `c14a0728765362a96ed161bbb453efd0a56d7c86` (docs on top of that fix; the plugin sources are unchanged after `7f095cb`).

## Live path

Server: `python-sdk/e2e/opensandbox/local-up.sh up` (already healthy). `GET /health` → `{"status":"healthy"}`, `GET /version` → `{"version":"1.1.1"}`.

`abx` was the CLI source via `node --import tsx src/bin/abx.ts` in `/workspace/cli`, with a throwaway `HOME`.

### Install

```text
abx --json provider install https://github.com/alibaba-agent-sandbox/awesome-providers.git \
  --subdir opensandbox --ref 7f095cbe30ac4c8a22abbb20945546185cd0151a --yes
```

Exit 0. Receipt trust `pinned`, commit `7f095cb…`, id `opensandbox` 0.1.0.

`abx --json provider default` → `alicloud-express` / source `builtin`. `provider list` shows opensandbox as exec/pinned and not the default. `provider doctor opensandbox` → installed, integrity, config, handshake all `ok`.

Local path (same command, directory argument):

```text
abx --json provider install /tmp/awesome-providers/opensandbox --yes
```

Exit 0, trust `local`. A second install without `--force` exits 1, `E8003`. With `--force --yes` exits 0.

Unpinned git install (`--yes`, no `--ref`) exits 2, `E8012` ("Refusing an unpinned git source in non-interactive mode.").

`abx provider default opensandbox` then `abx --json provider uninstall opensandbox --yes` exits 0 with `default_reset: true` and stderr `Default provider reset to 'alicloud-express'.` A following `provider default` is `alicloud-express`.

A dirty local tree (a `// dirty marker` line appended to `provider.mjs`) installs as trust `local` with no commit, and the installed `provider.mjs` contains the marker. The installer does not pretend the dirty tree is a git pin.

### Before the entrypoint fix

`sandbox.create` with the previous default entrypoint `python3 commands.py` against `python:3.12-slim`:

- Plugin: `CREATE_FAIL` `-32005`, `execd of sandbox … did not become ready within 40s: … ECONNREFUSED`.
- Direct API `POST /v1/sandboxes` with that entrypoint: HTTP 202, container then `Exited (2)`. Logs: `python3: can't open file '//commands.py': [Errno 2] No such file or directory`.
- The same API call with `["sleep","infinity"]` stayed `Up` and execd listened on `:44772`.

OpenSandbox exits the container when the entrypoint exits, and execd dies with it. The manifest default was delivered by the host as an explicit entrypoint, so every stock image got `python3 commands.py`.

### After the fix (installed commit `7f095cb`)

| Step | Command / call | Result |
|---|---|---|
| Create | `abx --json --provider opensandbox sandbox create --template base --timeout 120 --yes` | Exit 0. `ID` `7d62f677-5b38-4c7e-98e0-5d9d4e1233b8`, status `running`, template `python:3.12-slim` |
| Exec | `abx --json --provider opensandbox sandbox exec <id> "printf 'cli-exec ok\n'"` | Exit 0. stdout `cli-exec ok\n`, exit_code 0 |
| Stream | `abx --provider opensandbox sandbox shell-stream <id> --command "printf 'cli-stream ok\n'"` | Exit 0. stdout `cli-stream ok` |
| Upload | `abx … sandbox upload <id> unicode.txt "/tmp/你好 世界.txt"` | Exit 0 |
| Download | `abx … sandbox download <id> "/tmp/你好 世界.txt" back.txt` | Exit 0. bytes match (`café ☃`) |
| Unknown id | `abx --json --provider opensandbox sandbox info does-not-exist-xyz` | Exit 4, `E8005`, HTTP 404 |
| Wrong key | `Sandbox.create` with `ABX_OPENSANDBOX_API_KEY=super-secret-key-xyzzy` | `InvalidAPIKeyError` `E1001`. The key string is not in the exception text |
| SDK create TTL | `Sandbox.create(..., timeout=30)` | `expires_in` 59.7 s. Plugin stderr: `timeout 30s is below OpenSandbox's 60 s minimum; using 60 s` |
| SDK exec | `sh -c 'echo out; echo err >&2; echo $LIVE_VAR; exit 3'` | exit 3, stdout `out\nbar\n`, stderr `err\n` |
| SDK stream | `sh -c 'echo a; sleep 0.2; echo b >&2; exit 2'` | stdout `a\n`, stderr `b\n`, exit 2 |
| SDK file | path `/tmp/你好 世界/'q\".txt`, body `café\n☃\n` | read-back equal |
| Port | `network.resolve(8000)` then HTTP server | URL `http://127.0.0.1:<port>/proxy/8000`, fetch `/hostname` status 200 |
| Pause / resume | `sb.pause()` / `sb.resume()` then `echo alive` | status `paused`, then exec exit 0 `alive\n` |
| Plugin live suite | `OPENSANDBOX_LIVE=1 node tests/run.mjs live` on the fixed tree | 2 passed (lifecycle, wrong key) |
| Plugin unit+mock | `node tests/run.mjs unit mock` | 49 passed |

`abx sandbox kill <id> --yes` twice (flag after the subcommand): both exit 0 after the CLI fix below. Putting `--yes` before the subcommand is rejected as `No such option '--yes'` (exit 2); that is flag placement, not a kill failure.

Node live suite also asserts a second `sandbox.kill` on the same plugin process returns `{}`.

## Defects reproduced and fixed

1. **Stock-image entrypoint killed the sandbox.** Default `python3 commands.py` exits on `python:3.12-slim`, so execd never stays up. Fixed in the plugin: automatic entrypoint is `tail -f /dev/null`. An explicit entrypoint still wins (`python3 commands.py` for a generated image). A code-interpreter image keeps `/opt/code-interpreter/code-interpreter.sh` unless the caller sets something else. The host delivers the manifest default, so that default string is treated as automatic, not as a user override. Failing unit test added first (`tests/unit/create-entrypoint.test.mjs`), then the implementation. Catalog commit `7f095cb`.

2. **`abx sandbox kill` was not idempotent.** The command called `Sandbox.connect` (a get) before kill. A vanished sandbox returns HTTP 404 / `E8005` from get, so the second `abx kill` exited 4 even though the plugin's `sandbox.kill` swallows not-found. Reproduced on id `7d62f677-…`. Fixed by calling `Sandbox.killById`, which hits kill directly. Failing test `test_kill_of_a_missing_sandbox_is_idempotent` added first. Re-ran: both kills exit 0.

3. **`Sandbox.kill()` on the same object was not idempotent.** The first call closes the plugin client. The second call raised `ProviderProcessError` `E8021` (`exited unexpectedly (code 0)`), with the earlier TTL clamp line in the suggestion. Reproduced on id `d800b3f7-…` through the Python SDK. A successful kill is remembered and a second call returns without talking to the closed plugin (`test_second_kill_is_a_noop`). The same guard is in the Node SDK working copy `cli/src/api/sandbox.ts`; that directory is not in git, so this commit does not add it. `abx sandbox kill` does not use the instance method; it uses `killById` (defect 2).

## Reproduced, not changed

- `abx --json sandbox info <id>` after `sandbox create --timeout 30` printed `Timeout: 300s` and `Region: cn-hangzhou`. Those are `SandboxInfo` defaults. The SDK's `end_at` for the same create was ~60 s (the clamp). Info does not show that expiry. It did not block exec, files, or kill.
- `process.stdin`, PTY, code interpreter, and template build are declared unsupported (`-32003` / `E8004`). They were not separately driven against this server. Pause, ports, exec, and files, which the manifest claims, worked on this Docker runtime.
- An untracked copy of the plugin was still under `python-sdk/examples/providers/opensandbox/` (not in git). It was removed. The SDK examples that remain are `local-process` and `e2b-compatible`. No `provider.mjs` remains in the SDK or CLI trees.

## 中文

在本机 Docker 上的 OpenSandbox 1.1.1（`execd:latest`，镜像 `python:3.12-slim`）复现了三条缺陷，并已修复：

1. 默认入口 `python3 commands.py` 在通用镜像里立刻退出，容器和 execd 一起死掉，创建在约 40 秒后以 `-32005` / `ECONNREFUSED` 失败。插件改为自动使用 `tail -f /dev/null`；显式入口仍然优先；code-interpreter 镜像仍用自己的运行时脚本。目录提交 `7f095cb`。
2. `abx sandbox kill` 会先 `connect`/`get`。沙箱已经不存在时 get 返回 404（`E8005`，退出码 4），第二次 kill 失败。改为直接 `killById` 后，连续两次 `abx … sandbox kill <id> --yes` 都是退出码 0。
3. 同一个 `Sandbox` 对象上第二次 `kill()` 会在客户端已关闭后报 `E8021`。成功的第一次 kill 之后，第二次调用直接返回。

同一轮还确认：钉住提交的 `abx provider install`（git URL 与本地目录）、不带 `--ref` 的非交互安装被拒绝、重复安装需要 `--force`、卸载后默认提供方回到 `alicloud-express`、同步 exec、流式 exec、带空格和引号的 Unicode 路径、端口 URL、pause/resume、错误 API key（`E1001`，错误文本不含密钥）、未知 id（`E8005`）。`sandbox info` 仍会显示默认的 `Timeout 300s` 和 `Region cn-hangzhou`，与服务器上约 60 秒的过期时间不一致，这次没有改。

## Re-run 2026-10-13 after the provider hardening

A second run with the hardened host code (pinned install from a local clone, 18/18 contract kit on both hosts, create/exec/files/kill from the CLI, the SDK scenario with pause/resume) is recorded in [2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md). Two differences from the notes above: `connect`/`info` of an unknown sandbox is now `E2009` (exit 4) instead of `E8005` (`kill` stays idempotent), and `info` for a plugin sandbox no longer prints the built-in region `cn-hangzhou`.
