# 编写模板

模板包含应用源码、Dockerfile 和一个 `template.yaml`。使用 `specVersion: 1`；[字段参考](../reference/template-yaml-spec.md)说明资源、实例与原生 Serving 配置。可选的 `registry.yaml` 负责目录描述和初始化问题。依赖写入 Dockerfile 与语言原生依赖文件。

Python 应用端点在镜像内安装 `agent-sandbox-server`，注册真实业务函数：

```python
from agent_sandbox.server import command, start

@command("hello", description="Greet a user")
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    start(9000)
```

在 `sandbox.start` / `sandbox.ready` 声明启动和就绪命令，在 `sandbox.services` 声明端点。YAML 不注册函数，也不会启用服务端默认关闭的组。服务端策略是独立运行时配置，通过镜像内策略文件或服务端文档说明的配置入口加载。参阅[服务端 API](template-server-api.md)。

通过 [CLI 模板编写流程](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md)准备和发布源码。Python [启动已准备模板](template-workflows.md)，或连接已有 Sandbox。镜像原生入口和 Python 启动命令应只有一个责任方，避免同一服务重复启动。

通过 `session.servers["app"].commands.run("hello", name="Python")` 或显式解析的 `sandbox.application_client` 调用注册函数。应用令牌、网关请求头和 Sandbox API 凭据属于不同认证层。Shell 使用 `sandbox.commands.run(...)`，其存在不等于业务 API 或解释器能力。
