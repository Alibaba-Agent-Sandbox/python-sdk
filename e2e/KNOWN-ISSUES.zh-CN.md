# E2E 套件记录的已知问题

套件把发现的每个产品缺陷固定为**严格 `xfail`**(`@pytest.mark.known_issue`)。缺陷修复后该测试会变为 XPASS 并使运行失败
(strict),迫使修复者删除标记,从而保证本清单始终真实。标注 *platform*(平台)或 *environment*(环境)的问题不是 SDK 缺陷,
对应测试为非严格或带原因跳过。

> English version: [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

观测环境:真实云端(cn-hangzhou、envd 0.5.2、模板 `python-hello`),日期 2026-10-12,SDK 源码为本仓库当前版本。

| ID | 类型 | 摘要 | 测试 | 修复后的预期 |
|---|---|---|---|---|
| KI-001 | SDK 缺陷(**已修复**) | `sandbox.commands.run(cmd, env={...})` 以 `envVars` 发送变量,而 envd 期望 `envs`,单次调用的环境变量被静默丢弃 | `test_03_commands.py::test_run_with_per_call_env` | 命令内 `printenv` 能看到该值 |
| KI-002 | SDK 缺陷(**已修复**) | `files.list` / `files.get_info` 不识别 envd 的数值型条目类型:目录被报告为 `file`;`get_info` 忽略嵌套的 `entry` 对象(名称/路径为空) | `test_04_files_envd.py::test_list_and_stat_report_directory_type` | 目录为 `directory`,`get_info` 返回真实名称/路径/大小 |
| KI-003 | SDK 缺陷(**已修复**) | 命令超时时抛出原始 `httpx.ReadTimeout`,`CommandTimeoutError` 从不触发 | `test_03_commands.py::test_command_timeout_raises_command_timeout_error` | 抛出 `CommandTimeoutError` |
| KI-004 | SDK 缺陷(**已修复**) | `commands.kill`、`send_signal`、`send_input` 发送扁平的 `{"pid": N, ...}`,而 envd 需要 `{"process": {"pid": N}, "signal": ..., "input": {...}}`;请求从未到达进程(envd:`process not found`),真实进程继续运行 | `test_03_commands.py::test_kill_and_signal_terminate_a_process[...]`、`::test_send_input_reaches_stdin` | 进程被终止/收到 stdin |
| KI-005 | SDK 缺陷(**已修复**) | not-found 情况泄漏原始 `httpx.HTTPStatusError`(404):对不存在沙箱的 `Sandbox.connect()`、读取不存在文件的 `files.read` | `test_01_platform.py::test_connect_to_missing_sandbox_raises_sdk_error`、`test_04_files_envd.py::test_read_missing_file_raises_sdk_file_error` | `SandboxError` 子类(文件操作为 `FileNotFoundError_`) |
| KI-006 | SDK 缺陷(**已修复**) | 平台 401 以原始 `httpx.HTTPStatusError` 暴露,而非 `AuthenticationError`(CLI 做了映射,SDK 没有) | `test_01_platform.py::test_wrong_api_key_raises_authentication_error` | `AuthenticationError` |
| KI-007 | SDK 缺陷(**已修复**) | `files.list` 列出不存在的目录返回 `[]`(envd 返回 200 且无条目),而不是抛错 | `test_04_files_envd.py::test_list_missing_directory_raises` | `FileNotFoundError_` |
| KI-008 | 平台/网关 | 从测试机向 envd 上传 1 MB 及以上的文件会超过默认 30 秒 HTTP 超时(受吞吐限制);400 KB 正常。因依赖网络吞吐,为非严格 xfail | `test_04_files_envd.py::test_one_megabyte_upload_within_default_timeout`(`e2e_slow`) | 在默认超时内通过,或超时随大小自适应 |
| KI-009 | 平台 | 该云端的 Jupyter 代码解释器服务返回 HTTP 404,`run_code` 回退为 shell,末尾表达式(`21*2`)的值不会返回;stdout 正常 | `test_05_network_and_code.py::test_run_code_returns_last_expression_value` | `results[0].text == "42"` |
| KI-010 | SDK 缺陷(**已修复**) | 对 `async def` 函数使用 `@sandbox`:生成的远程脚本调用协程函数但未 await,结果是字符串 `<coroutine object ...>` | `test_07_declarative.py::test_async_decorated_function` | 返回真实值 |
| KI-011 | 环境 | 从本环境向个人版 ACR 推送真实镜像层速度约 17 KB/s(较早推送已去重的小层可成功),Docker 自定义模板流程无法在合理时间内完成。套件用 2 MB 随机层 canary 推送探测(`E2E_CANARY_PUSH_TIMEOUT`,默认 120 秒),并带确切原因**跳过**整个 `e2e_docker` 模块 | `test_08_custom_template_docker.py`(`e2e_docker`、`e2e_slow`) | 在带宽正常的镜像仓库链路下 canary 通过,流程照常运行 |

说明

- KI-001 至 KI-007 与 KI-010 已在 `client-sdk/src` **修复**(CHANGELOG `Unreleased` > `Fixed`);对应测试的 `xfail` 标记已删除,
  现为普通回归测试(单元级回归测试见 `client-sdk/tests/test_known_issues/`)。验证记录:
  `.agents/evidence/verify/2026-10-12-ki-sdk-fixes.md`。KI-008 现在会以清晰的 `FileOperationError`(提示 `EBX_HTTP_TIMEOUT`)
  暴露,而不是裸的 httpx 超时(超时本身未改变)。新的 SDK 行为:envd 只能投递 SIGTERM/SIGKILL(其他信号编号抛 `ValueError`),
  envd 的进程 id 是它自己的计数,不是操作系统 pid。
- Python oracle CLI 继承了 KI-002(`ebx sandbox files stat` 输出空名称/路径;目录被列为 `file`),见 `cli/e2e/BASELINE.md`。
