# 在已有极速版账号上使用 Agent Sandbox

这里更换的是客户端和工具，不是云后端。原账号、地域、Team、API Key、模板 ID/别名、
Volume、RAM 角色都可以继续使用，不必仅为接入客户端而重建资源。目前没有已实现的
零改动或一键迁移；应核对应用实际使用的 API。

## 需要修改的内容

| 原极速版应用 | Agent Sandbox 客户端 |
| --- | --- |
| `from e2b import Sandbox` | `from agent_sandbox import Sandbox` |
| 隐式读取 `E2B_API_KEY`、`E2B_API_URL`、`E2B_DOMAIN` | 显式配置 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL`、`ABX_SANDBOX_DOMAIN`，不静默读取旧名称。 |
| `Sandbox.kill(id)` | `Sandbox.kill_by_id(id)` |
| `sandbox.get_host(port)` | `sandbox.network.get_host(port)` |
| 假定上传/下载 URL 可凭签名访问 | 使用带认证的文件方法，见 [E2B 迁移差异](migrate-from-e2b.md)。 |
| 原 API、结果和错误处理 | 核对方法、流式输出、异常及同步/异步行为，同名方法不等于完整兼容。 |

若当前 shell 中确实配置的是**同一个极速版账号**，可以显式映射选定设置，而不打印值：

```sh
export ABX_SANDBOX_API_KEY="$E2B_API_KEY"  # example: use the existing Express value
export ABX_SANDBOX_BASE_URL="$E2B_API_URL"
export ABX_SANDBOX_DOMAIN="$E2B_DOMAIN"
```

不要启用 shell 跟踪，也不要从原生 E2B 账号复制这组配置。继续使用原模板 ID/别名和
原地域端点。普通沙箱密钥生命周期、执行和文件调用无需 AK/SK；云管理、模板发布另需
AK/SK 及镜像仓库前提。API 的 `api_key`、`api_url`、`domain` 仍是对应规范配置的兼容
别名，与规范名称同时提供不同值时会拒绝。

## 用新建测试沙箱验收

按[安装指南](getting-started.md) 安装兼容的 client/server 发布版本后，选择已有模板：

```python
import asyncio
import os
from agent_sandbox import Sandbox

async def main():
    sandbox = await Sandbox.create(
        provider="alicloud-express",
        template=os.environ["EXISTING_TEMPLATE_ID"],
        timeout=300,
    )
    try:
        result = await sandbox.commands.run("printf migration-ok")
        assert result.exit_code == 0 and result.stdout == "migration-ok"
    finally:
        await sandbox.kill()  # 只清理本例自己创建的沙箱

asyncio.run(main())
```

检查已有存活沙箱时，用其 ID 和同 Team 密钥连接。连接不等于允许加入自动删除清单；
未经所有者授权，不改变其租期和工作负载。

普通原生生命周期、执行和文件访问，不要求先给已有镜像安装本项目的 9000 端口服务。
项目命名命令、Agents 路由和对应模板能力属于额外运行时要求，任意旧模板未必提供。
Provider 插件和管理 API 还需要兼容的 Node 引擎，与原生极速版生命周期路径不同。

## 边界、证据与升级

创建时 `volume_mounts={"/mnt/workspace": "existing-volume-name"}` 复用同 Team 的
Volume 和存储角色，不创建底层存储，也不自动证明权限正确。
[已有真实 OSS 验收](../../../.agents/evidence/verify/2026-10-16-provider-volume-live.md)
覆盖记录中的 base 模板/地域下挂载、读写、沙箱重建持久化和本次资源清理，不代表极速版
全部能力已验收。域名管理、动态追加挂载、STS 管理凭据、较新 JuiceFS 字段及
`volume.update` 的真实状态转换仍不支持或未验证，以
[共享宿主矩阵](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/design/alicloud-provider-commands.md) 为准。

外置插件按记录的来源更新。内置 provider 随 SDK 发布：
`python -m agent_sandbox.providers --json update alicloud-express --check` 返回
`bundled` 和指引，不检查最新版本、不执行软件升级。按原安装方式同步升级匹配的
client/server，Node 管理操作还需单独升级 abx。只重启自己管理的引擎。
[宿主职责/更新设计](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/design/provider-portability-and-updates.md)
定义确认、固定版本、回滚及待完成的模板适配器工作。
