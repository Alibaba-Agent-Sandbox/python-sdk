# Server SDK

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

Server SDK 跑在**沙箱里面**。它是镜像启动后一直听着的 HTTP 服务，默认端口 9000。包名是 `agent-sandbox-server`，导入 `agent_sandbox.server`。模板的 `commands.py` 用它注册命令、打开能力，然后 `start(9000)`。

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=server-sdk"
```

```python
from agent_sandbox.server import command, start


@command(description="Say hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    start(9000)
```

这段代码不创建云上沙箱，也不读取沙箱 API Key。谁来创建沙箱、谁来调用这些路由，是 [Client SDK](client-sdk.md) 或 `abx` CLI 的事。

## 通过 CLI 加载命令

使用 `serve` 子命令，让服务启动与命令注册分别负责各自的工作：

```bash
agent-sandbox-server serve --commands ./commands.py --port 9000
```

文件在 HTTP 服务启动前作为模块导入，因此其中的 `if __name__ == "__main__"`
代码块不会执行。含有 `from __future__ import annotations` 和 `@dataclass` 的文件
遵循普通导入的行为：装饰器执行时，其模块已经存在于 `sys.modules` 中。
可以重复传入 `--commands`，加载多个文件或可导入的模块名。

同一进程内，同一规范路径的文件只加载一次，相对路径、绝对路径和符号链接别名均会
合并；不同目录下同名的 `commands.py` 则是不同模块。修改文件后需重启服务。
文件所在目录会保留在导入路径中，以支持同目录模块的导入。若加载抛出异常，未完成的
模块记录和此次加载对导入路径的修改会被清除，异常会阻止服务启动。
其他副作用（如异常前已注册的命令）不会回滚；请修正文件后重启服务。

## 从这里开始

| 文档 | 做什么 |
|------|--------|
| [编写模板](authoring-templates.md) | `template.yaml`、Dockerfile、`commands.py` |
| [模板服务器 HTTP API](template-server-api.md) | 服务实际提供的路由 |
| [最佳实践](best-practices.md) | 服务器不带提供者、按需打开能力组 |
| [细粒度能力](fine-grained-capabilities.md) | 按端点开关路由 |
| [文件与命令控制](file-and-command-controls.md) | 限制路径和命令 |
| [Agents API](agents-api.md) | 在沙箱里打开 Codex 和 Qwen Code 的 HTTP 会话 |
| [托管代理](hosted-agents.md) | 这些路由怎么拒绝、怎么返回 |

参考：[Server HTTP API](../reference/server-http-api.md)、[template.yaml](../reference/template-yaml-spec.md)、[Agents API 参考](../reference/agents-api.md)、[Server API 设计](../design/server-api.md)。

## 示例

这些 `commands.py` 随镜像启动，见 [示例目录](../../../examples/README.zh-CN.md#server-sdk-示例)：

- `examples/templates/python-hello/commands.py` — 最小命令服务器
- `examples/templates/agents-cli/commands.py` — 只打开发话相关的 Agents 路由

`examples/templates/python-hello/call_api.py` 不是 Server SDK。它在沙箱外面，对已经在听的服务发请求，归在 Client SDK。
