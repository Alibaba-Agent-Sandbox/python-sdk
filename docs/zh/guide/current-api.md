# Python SDK 开发接口

通过 `ProviderSandbox` 使用 Provider 扩展，参数统一为 `sandbox_api_key`、`sandbox_base_url` 和 `sandbox_domain`。SessionManager 与 sandbox 装饰器使用相同参数。协议实现位于所属 Provider 包中，转发导入模块已删除。

命令使用 `send_input`、`send_signal`，文件使用 `stat`、`move`；删除的方法不保留转发。端口地址由所选 Provider 显式提供。

服务端文件传输使用 `/files/upload-stream` 和 `/files/download-stream`。认证统一由策略令牌引擎处理，显式策略令牌优先于便捷配置 `ABX_SERVER_TOKEN`。远程独立客户端需要显式提供 PTY URL。

固定版本的标准 `Sandbox`、`AsyncSandbox` 保留上游接口约定。模板命令与配置变更见 [CLI 开发接口](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/current-api.md)。历史验证记录仅说明其原始修订。

配置导出统一使用 `storage` 字段，删除不生效的 `max_retries`、`retry_base_delay` 和重复的 GlobalConfig 模型；显式调用的重试工具仍可使用。按环境文件约定存储的凭据不再从明文 TOML 读取。
