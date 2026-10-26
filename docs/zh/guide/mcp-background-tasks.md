# Python MCP 后台任务与重连

Python MCP server 提供 `start_task`、`get_task`、`cancel_task`，在已有 Linux
沙箱中执行后台 shell 任务。运行时需要 `python3`、`/proc` 和进程组支持。
Python STDIO 与 HTTP 共用这些处理函数；Node.js CLI 的 MCP 是另一份实现，
本次三个工具仅适用于 Python server。

## 启动、重连和结束

先创建沙箱，再显式启动后台任务：

```json
{"name":"create_sandbox","arguments":{"template":"base","timeout":600}}
{"name":"start_task","arguments":{"command":"printf BEFORE; sleep 10; printf AFTER","timeout":120}}
```

保存返回的 `sandbox_id` 和 32 位小写十六进制 `task_id`。提交成功时返回已观测
状态，短任务可能已结束。提交响应无法确认时返回 `state: "unknown"`、原句柄，并可能附带
错误；使用句柄查询或销毁该沙箱，不要直接重复提交可能已执行的命令。

**启动后台任务会显式保留整只沙箱，使其在 MCP 断开后继续存活到原平台 TTL。**
其他沙箱仍按原会话规则清理。任务处理函数不请求延长平台存活时间，沙箱到期可能
早于任务超时。之后调用普通执行、文件工具，仍会按原有策略续期。保留的是整只
沙箱，也包含其中其他工作；需要单独控制时请使用专用沙箱。

新 MCP 会话或新 Python MCP 进程，在相同授权 provider、地域配置下可查询句柄：

```json
{"name":"get_task","arguments":{"sandbox_id":"REPLACE_ME","task_id":"0123456789abcdef0123456789abcdef","stdout_offset":0,"stderr_offset":0,"limit":16384}}
```

结果包括 `state`、`exit_code`、`started_at`、`finished_at`、`stdout`、`stderr`，
两路日志各自的下一字节偏移、已保存字节数和 `stdout_truncated` /
`stderr_truncated`。状态为 `running`、`succeeded`、`failed`、`cancelled`、
`timed_out` 或 `unknown`。`failed` 表示非零退出或 supervisor 失败，supervisor
丢失时为 `unknown`，不会编造成功。进度体现为日志和状态，不提供百分比。
时间为 Unix 秒数。`get_task` / `cancel_task` 中的非零退出码属于任务数据，
成功读取或确认取消不会仅因该退出码被标成 MCP 工具错误。

后续读取传入上次返回的偏移；同一偏移可重复读取。`limit` 为每路日志字节数，
默认 16384，上限 65536。分页可能切断 UTF-8 字符，片段解码时使用替代字符。
每路最多保存 1 MiB，超过后仍持续排空管道，避免任务阻塞，并在结束时标明截断。
每个沙箱 OS 用户最多接受 128 个任务目录。

取消后读取记录状态：

```json
{"name":"cancel_task","arguments":{"sandbox_id":"REPLACE_ME","task_id":"0123456789abcdef0123456789abcdef"}}
```

supervisor 先向任务自有进程组发 TERM，再发 KILL；正常退出、非零退出和超时
也会清理同组后代。取消最多等待三秒确认终态，仍为 `running` 或 `unknown`
不能当作取消成功。对已结束任务重复取消只返回保存的结果，不接受任意 PID。
另建 session/进程组的子进程超出该归属边界，完整停止需销毁沙箱。

取回结果后显式释放保留资源：

```json
{"name":"kill_sandbox","arguments":{"sandbox_id":"REPLACE_ME"}}
```

## 参数与边界

| 工具 | 参数 |
|---|---|
| `start_task` | 必填 `command`，最多 65536 字符；可选已有 `sandbox_id`、`cwd`、任务 `timeout`（1–3600 秒，默认 300） |
| `get_task` | 必填 `sandbox_id`、`task_id`；可选两路字节偏移（0–1048576）、`limit`（1–65536） |
| `cancel_task` | 与 `get_task` 相同的句柄和分页参数 |

启动时省略 `sandbox_id` 必须已有会话默认沙箱，不会隐式创建。
JSON 与 shell 引号编码后的请求在远程连接前受 96 KiB 上限约束。
未知参数和非法任务 ID 会被拒绝。查询、取消使用 SDK 原有的授权 provider
连接路径，调用后关闭连接，不纳入会话退出时的销毁集合。其他 provider 的连接路径可能
恢复已暂停的实例，仍遵循其自身生命周期语义。

日志和原子状态文件保存在沙箱内按 OS 用户隔离的私有目录中，可跨 MCP 会话和
进程替换，但不能跨沙箱销毁、到期、文件系统丢失或重建。本次不提供本机持久
数据库、托管任务服务、自动重试或沙箱替换。首次状态写入前进程崩溃可能导致
句柄无法确认；无法查询时可销毁沙箱完成清理。

输出是用户数据。写日志前，supervisor 对沙箱环境变量名中包含 KEY、TOKEN、
SECRET、PASSWORD 的已知值做精确脱敏，覆盖跨管道读取分片的值；主机还会逐页
屏蔽自身配置值。这不等于通用秘密检测，编码值、部分值、跨页的主机专属秘密
仍可能保留。命令、文件、日志共用沙箱 OS 身份，task_id 不是多租户授权边界。
不要把秘密写入命令或打印；不同信任域使用独立授权沙箱。

真实极速版验证覆盖原生 Start/Connect 的重放限制，以及启动→断开→重连→
读取退出码和完整日志→取消→资源清理。该记录不代表其他 provider、Windows
或托管多用户部署已通过验收。

## 限定句柄的兼容性

本源码版本将 `start_task.sandbox_id` 返回为实际 `provider:id`，使新会话仍连接任务
原先使用的后端，包括非默认提供方。完整返回句柄是不透明值，须原样传给 `get_task`
和 `cancel_task`；拆分或仅提取原始 ID 的客户端需要更新。没有新增参数，但返回字符串
的表示发生变化。历史非限定 ID 在 SDK 默认提供方对应原资源时仍可使用；生命周期缓存
也接受唯一的原始 ID。多个缓存提供方使用同一原始 ID 时会拒绝推测，要求限定提供方。
