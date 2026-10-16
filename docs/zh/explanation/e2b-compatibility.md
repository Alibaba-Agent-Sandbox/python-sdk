# E2B 行为与阿里云后端能力

标准公开接口遵循阿里云支持的固定 E2B 版本。`Sandbox` 为同步客户端，`AsyncSandbox` 为异步客户端，`agent_sandbox.code_interpreter` 提供代码解释器客户端。项目 Provider、Server、声明式等扩展使用 `ProviderSandbox`。

项目持有并维护保留 MIT 署名的源码及协议传输，不在运行时安装或调用 E2B 包。兼容范围包含分页、返回模型、异常、流式处理和 PTY 行为，而不仅是方法名。

完整导入、连接配置、条件能力和后端不支持项见[迁移契约](../guide/migrate-from-e2b.md)。客户端导出了某个类型，不代表阿里云已经开放其服务接口。
