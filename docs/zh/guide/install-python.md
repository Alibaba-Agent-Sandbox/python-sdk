# 安装 Python 配套包

当前开发版本0.3.0尚未发布到 PyPI：2026-10-19 两个发行包的元数据端点均返回404。包名存在于项目中不等于已发布。请使用下面验证过的配套源码安装方式，或从开发检出安装。CLI 从其独立仓库安装。

## 固定提交的配套源码

使用 Python 3.10或更高版本及虚拟环境。此已验证的固定实现包含标准同步/异步客户端、原生 Provider/server 扩展及服务启动确认修复；并不声称它是最新主线提交。

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
python -m pip check
python -c "import agent_sandbox, agent_sandbox.server; from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

两个版本均为0.3.0，必须一致。为兼容已有装饰器和共享命名空间，客户端仍硬依赖同版本服务端；同时指定两个源码发行包，避免 pip 去索引寻找尚未发布的服务端。不要安装无关的 `agent-sandbox` 发行包。

## 可选 extras

保留同一个服务端 URL，在客户端直接引用上选择 extra；全量依赖使用：

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
```

可把 `[all]` 换成 `[mcp]`、`[declarative]`、`[session]` 或 `[fast]`。MCP 需要相应 extra；浏览器自动化还需在镜像内单独安装 Playwright。

## 镜像内只安装服务端

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk"
```

沙箱内服务端和本地客户端职责不同，安装服务端不会创建沙箱。

## 当前开发检出

在隔离环境中，从本仓库根目录运行：

```bash
python -m pip install -e ./server-sdk -e "./client-sdk[dev]"
python -m pip check
```

此时使用实际检出的源码，而非上面的固定示例，应记录提交以便复现。配置所需厂商后再运行示例；安装通过不等于云端、厂商或模型验收通过。依赖冲突优先在新环境中定位，再同时重装配套发行包。
