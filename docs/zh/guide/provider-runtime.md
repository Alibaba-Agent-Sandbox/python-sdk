# 在 Python 中准备 Provider 运行时

使用 Python SDK 源码中的 `agent_sandbox.providers.ProviderClient`，在应用启动阶段绑定 Provider 和服务目标。应用传入兼容的 Python 实现时优先使用它，否则可以获取已确认的独立 EPP 实现及其运行时。导入 SDK 和直接调用业务 HTTP API 均无需准备 Provider 运行时。

## 在 Linux x86-64 glibc 上使用 OpenSandbox

[示例锁文件](../../../examples/providers/locked-opensandbox/provider.lock.json)固定了 Provider 和 Node.js 制品的地址、SHA-256 与字节长度。通过你信任的渠道取得锁文件。OpenSandbox 服务需要可以访问，并能够启动选定的镜像。

- 将 `OPENSANDBOX_BASE_URL` 设置为 OpenSandbox 服务地址。
- 服务启用鉴权时，设置该服务的 `OPENSANDBOX_API_KEY`。本机制品校验通过后，SDK 才把 Key 交给 Provider。
- 可通过 `OPENSANDBOX_TEST_IMAGE` 指定该服务可运行的镜像。

[示例程序](../../../examples/providers/locked-opensandbox/run.py)下载固定制品、创建 Sandbox、运行命令、验证文件读写、删除 Sandbox，再从缓存准备一次并确认实例已删除。

```bash
python examples/providers/locked-opensandbox/run.py
```

在应用能够联网的准备阶段调用 `await ProviderClient.prepare(lock, config, cache_dir=path, download=True)`。使用由应用操作者管理路径及父目录的私有缓存。离线准备复用该缓存并使用默认的 `download=False`。每次准备都重新验证缓存制品。缓存校验失败时，可以用已确认的副本替换对应条目，或换一个私有缓存重新准备。

## 使用已安装的 Python Provider

通过 `native=` 传入受信的 `Provider` 实例。实现的 ID、版本须与 `ProviderLock` 一致。用 `required_features` 声明所需能力。SDK 优先使用兼容的 Python 实现，否则选择匹配宿主和能力的已确认独立实现。在独立实现中优先选择 Python，然后选择数值最小的优先级。只用本地 Python 时，锁文件可以省略运行时条目。Python 实现沿用应用的依赖安装方式。

`ProviderClient` 提供 `create(SandboxConfig(...))`、`connect`、`list`、`get`、`set_timeout` 和 `delete`。在准备客户端的事件循环中使用它。使用结束后关闭各 Sandbox 句柄，再关闭客户端。需要释放自己创建的远端 Sandbox 时调用 `delete`。`ProviderClient.close()` 负责关闭本地资源。

独立制品准备支持 Linux glibc。制品需要独立 EPP/1 入口。示例还要求宿主 glibc 版本满足所锁定的 Node 发行版。目录安装与现有 `ProviderSandbox.create(provider=...)` 继续使用各自的设置方式。[Node.js 平台要求](https://github.com/nodejs/node/blob/v22.22.2/BUILDING.md)

操作提交后若丢失响应，应先查看返回错误。创建错误的 `outcome == "unknown_outcome"` 时须先核对远端状态。可选的 `on_created` 回调会在 Provider 返回实例 ID 后立即收到该 ID。关闭客户端前应等待正在执行的操作结束。
