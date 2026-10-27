# 迁移已有阿里云 E2B 应用

标准 Python API 以阿里云推荐的 `e2b==2.31.0`、`e2b-code-interpreter==2.8.1` 为行为基线，范围遵循[阿里云 E2B 兼容说明](https://help.aliyun.com/zh/agent-sandbox/e2b-compatibility-explanation)。项目自行持有协议实现，不安装这两个 E2B 包。本契约针对极速版；其他 Provider 通过独立的 `ProviderSandbox` 扩展 API 使用。本次不涉及 Node SDK。

## 最小迁移步骤

已通过 E2B SDK 使用极速版的应用：安装本项目客户端，按下表修改导入，保留已有 API Key、`E2B_API_KEY`、`E2B_API_URL`、`E2B_DOMAIN`（或原有 `api_key=` 参数）以及同步/异步调用方式。标准入口继续读取这些 E2B 配置；无需重建 Key/模板，也不要求新增 AK/SK 或 CLI。Provider 扩展入口使用项目的 `ABX_*` 配置。

只有在你选择 AK/SK 管理 Key 时，才需安装包含 `api-key.prepare` / `api-key.resolve` 的配套 CLI、配置 AK/SK 和地域、授予 Team 级权限，并在 SDK 首次运行前调用一次 `prepare_api_key_sync(confirm=True)`（异步用 `await prepare_api_key(confirm=True)`）。之后沿用现有标准业务调用，续期仍需明确确认。新增模板构建、ACR、Volume 等功能按需增加权限，见[完整权限指南](permissions.md)。这些准备接口需包含本功能的 CLI/SDK 源码或后续配套发行版，不能假定任意旧安装已经支持。

## 安装与导入

使用已发布客户端：`python -m pip install --index-url https://pypi.org/simple agent-sandbox-client==0.4.0a6`。通过 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和 `ABX_SANDBOX_DOMAIN` 配置极速版账号；本项目标准 `Sandbox` / `AsyncSandbox`、`code_interpreter` 和 `ProviderSandbox` 均支持这些项目配置。也可使用 `abx config` 与项目/用户配置文件。标准客户端公开 `api_key=` 参数仍属于其固定契约。仍使用第三方 E2B SDK 的独立应用按该 SDK 的原生配置操作，不要混用不同提供商账号的凭据。


| 原导入 | 新导入 |
|---|---|
| `from e2b import Sandbox, AsyncSandbox` | `from agent_sandbox import Sandbox, AsyncSandbox` |
| `from e2b_code_interpreter import Sandbox, AsyncSandbox` | `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` |
| `from e2b.exceptions import SandboxException` | `from agent_sandbox.exceptions import SandboxException` |

```python
from agent_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create(template="code-interpreter-v1", timeout=300)
try:
    sandbox.files.write("/tmp/input.txt", "hello")
    print(sandbox.commands.run("cat /tmp/input.txt").stdout)
    sandbox.run_code("value = 41")
    print(sandbox.run_code("value + 1").text)
finally:
    sandbox.kill()
```

`Sandbox` 是同步 API，`AsyncSandbox` 是异步 API；原有同步代码无需增加 `await`。`Sandbox.list()` 返回延迟分页器，通过 `has_next`、`next_items()`、`next_token` 使用；异步版本等待 `next_items()`。类方法与实例方法保持 E2B 命名，例如 `Sandbox.kill(id)` 与 `sandbox.kill()`，连接、信息、超时同理。超时单位为秒，`request_timeout=0` 关闭请求超时。非零命令退出抛出携带 `exit_code`、`stdout`、`stderr` 的 `CommandExitException`。后台命令返回支持 PID、等待、stdin、终止的句柄。写文件返回 `WriteInfo`，读取支持文本、字节和流。解释器保留执行结果、错误、回调和持久上下文模型。

## 能力边界

| 能力 | 契约与限制 |
|---|---|
| 生命周期、查询、metadata 过滤、分页、超时、端口地址、签名文件 URL 生成 | 标准 API；URL 是否可直接使用取决于后端 envd 鉴权能力，与参考 SDK 保持相同行为 |
| 命令、后台进程、stdin、PTY、文件与目录监听 | 标准 envd 协议与句柄语义 |
| 解释器、上下文、执行次数、stdout/stderr/result 回调、多语言 | 使用 `agent_sandbox.code_interpreter` 和支持解释器的模板；阿里云图表需生成文件取回 |
| 模板、从镜像构建 | 标准 Python Template API，以及项目 CLI build/deploy 扩展；仍受后端构建能力和权限限制 |
| 运行时网络更新 | 已实现 `update_network` 与允许/拒绝规则；阿里云 `egress_proxy` 不生效；公网入站鉴权与 Host 改写仅创建时可设 |
| 暂停/恢复 | 一代需白名单；二代具备运行时能力，仍受实际函数/账号设置限制。当前 python-hello 因未启用 pauseSession 拒绝暂停 |
| 快照 | 已实现创建、延迟分页、删除、恢复；需 MicroVM 与白名单。保留期、全名、占用和恢复覆盖限制遵循[阿里云快照规则](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test)。建议 `request_timeout=300` 并保存返回的 ID/名称 |
| 文件 metadata | 取决于二代运行时/envd 版本；旧 envd 返回与参考 SDK 相同的版本错误 |
| Metrics/Logs | 阿里云文档存在矛盾示例，不承诺所有账号可用；保留服务端错误，可使用控制台可观测能力 |
| Volume、Team、API Key/Access Token 管理、MCP 网关 | 不属于阿里云支持的 E2B 迁移主路径；导出上游类型不代表后端新增能力，应使用云端支持的管理方式 |
| OSS、VPC、阿里云扩展 | Provider/项目扩展，不混入标准 E2B 参数 |

`ProviderSandbox` 是项目异步 Provider、ServerClient、声明式等扩展的独立入口。使用命名服务端命令、会话、自定义 Provider、`sandbox.network` 的示例显式导入该类，不作为 `Sandbox` 的兼容模式。

## 第三方集成最佳实践

用户负责修改自有代码、封装层和集成适配器中的导入。依赖写死 `e2b` 或检查类身份时，优先使用客户端工厂/依赖注入；否则维护小型 fork 修改导入并固定版本验证。不要替换 `sys.modules`、安装冒名 `e2b` 包，也不要认为文本替换能解决运行时类型检查。E2B 私有模块及其他版本不在固定契约内。

## 实现来源与验证

协议客户端来自固定版本 MIT 许可源码，移入项目命名空间并由项目维护。源码哈希记录在 `client-sdk/src/agent_sandbox/_standard/SOURCES.json`，许可证随源码保留；运行时不依赖 E2B。接口回归位于 `client-sdk/tests/test_api/test_standard_contract.py`，真实云端迁移测试位于 `e2e/test_standard_contract.py`。接口测试通过不代表所有账号已开通条件功能；实际执行结果和限制见工程验证记录。

快照列表的可选 `name` 过滤是阿里云文档定义的扩展，本项目在固定 Python 参考版本基础上补齐，保留原有调用方式；删除全名时进行路径编码。

已对真实 python-hello 函数补充探测：pause 返回“pauseSession is not enabled for this function”，快照创建返回“sandbox runtime does not support snapshot”。客户端入口已实现，但该函数未启用暂停，且运行时不支持快照；不能把文档中的运行时能力等同于任意模板都已启用，需要已启用暂停的函数与支持快照的 MicroVM 模板验证成功路径。

标准入口接收 `E2B_*` 设置；原生 `ProviderSandbox` 保留规范的 `ABX_SANDBOX_*` 配置。标准入口仍可回退到现有项目配置，不能把兼容名称整体改写到原生配置注册表。
