# 安装 Python 配套包

下面的固定源码方案安装已验证的0.3.0快照；当前0.3.1a2 alpha 候选的说明见后文，只有发布及公开回读成功后才能从 PyPI 安装。包名存在于项目中不等于已发布。CLI 从其独立仓库安装。

## 固定提交的配套源码

使用 Python 3.10或更高版本及虚拟环境。此已验证的固定实现包含标准同步/异步客户端、原生 Provider/server 扩展及服务启动确认修复；并不声称它是最新主线提交。

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"
python -m pip check
python -c "import agent_sandbox, agent_sandbox.server; from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

两个版本均为0.3.0，必须一致。客户端的本地服务端和声明式辅助功能需要同版本服务端，因此将它列为必需依赖；同时指定两个源码发行包，避免 pip 去索引寻找尚未发布的服务端。不要安装无关的 `agent-sandbox` 发行包。

## 可选 extras

工作流 YAML 加载和声明式装饰器属于基础客户端，不再提供 declarative extra。

保留同一个服务端 URL，在客户端直接引用上选择 extra；全量依赖使用：

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"
```

可把 `[all]` 换成 `[mcp]`、`[session]` 或 `[fast]`。MCP 需要相应 extra；浏览器自动化还需在镜像内单独安装 Playwright。

## 镜像内只安装服务端

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk"
```

沙箱内服务端和本地客户端职责不同，安装服务端不会创建沙箱。

## 当前开发检出

在隔离环境中，从本仓库根目录运行：

```bash
python -m pip install -e ./server-sdk -e "./client-sdk[dev]"
python -m pip check
```

此时使用实际检出的源码，而非上面的固定示例，应记录提交以便复现。配置所需厂商后再运行示例；安装通过不等于云端、厂商或模型验收通过。依赖冲突优先在新环境中定位，再同时重装配套发行包。

## 维护者发布检查

两个发行包必须从匹配的 `v<version>` 标签发布。先对同一标签检出执行复用 CI，
只有 CI 成功才进入发布任务。工作流为每个包构建一次 wheel/sdist，
在新环境安装这对实际 wheel，并保存候选产物。手动运行默认 dry-run，同样要求选择
版本标签。上传前 PyPI 已存在的文件必须与候选 SHA-256 一致，不能只靠 `skip-existing`
宣称验证成功。先上传 server，再上传 client；之后回读公开文件摘要，并从公开索引
在新环境只安装固定版本 client，验证 server 自动依赖并运行 `pip check`。回读失败表示发布尚未验证，应保留候选产物用于恢复，
不要静默重新构建。该工作流不能替代必需 CI、评审及真实后端验收。

## 可选 alpha 预发布

0.3.1a2 是需显式选择的 alpha 候选。公开发布验证完成后，可使用下面的精确版本安装；同版本 server 由依赖自动安装。发布完成前，仍可使用上面的固定源码方案。Node provider doctor 需要配套 CLI initialize 接口（计划为 CLI 0.4.11），0.4.10 不支持。测试版不代表所有能力生产就绪。

```bash
python -m pip install 'agent-sandbox-client==0.3.1a2'
python -m pip check
```
