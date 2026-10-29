# 声明式用法（@sandbox 装饰器）

`@sandbox` 装饰器让你以声明式方式在远程沙箱中执行 Python 函数，无需手动管理沙箱生命周期。

---

## 基本用法

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter-v1")
def analyze(data):
    import pandas as pd
    df = pd.DataFrame(data)
    return df.describe().to_dict()

# 调用时自动：创建沙箱 → 上传函数 → 执行 → 返回结果 → 销毁沙箱
result = analyze({"col1": [1, 2, 3], "col2": [4, 5, 6]})
print(result)
```

---

## 参数配置

```python
@sandbox(
    template="code-interpreter-v1",  # 模板名称（默认 "code-interpreter-v1"）
    timeout=300,                      # 沙箱超时秒数（默认 300）
    envs={"MY_KEY": "value"},         # 环境变量
    packages=["pandas", "numpy"],     # 远程预安装的 pip 包
    serializer="json",                # 序列化方式（默认 "json"）
    sandbox_id=None,                  # 复用已有沙箱 ID（不为 None 时跳过创建）
    keep_alive=False,                 # True 时执行后不销毁沙箱
    sandbox_api_key=None,             # API Key 覆盖
    sandbox_base_url=None,            # 平台 API URL 覆盖
    sandbox_domain=None,              # 域名覆盖
    cpu=None,                         # CPU 核数
    memory=None,                      # 内存 MB
)
def my_func():
    pass
```

### 参数详解

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `template` | `str` | `"code-interpreter-v1"` | 沙箱模板名称 |
| `timeout` | `int` | `300` | 沙箱超时秒数 |
| `envs` | `dict` | `None` | 注入的环境变量（envd 作用域；详见[环境变量指南](environment-variables.md)） |
| `packages` | `list[str]` | `None` | 远程预安装的 pip 包 |
| `serializer` | `str` | `"json"` | 序列化模式（仅支持 `json`） |
| `sandbox_id` | `str` | `None` | 复用已有沙箱 ID |
| `keep_alive` | `bool` | `False` | 执行后不销毁沙箱 |
| `sandbox_api_key` | `str` | `None` | API Key 覆盖 |
| `sandbox_base_url` | `str` | `None` | 平台 URL 覆盖 |
| `sandbox_domain` | `str` | `None` | 平台域名 |
| `cpu` | `int` | `None` | CPU 核数 |
| `memory` | `int` | `None` | 内存 MB |

---

## 序列化规则

`serializer` 参数控制函数参数和返回值的序列化方式。当前仅支持 JSON 模式。

| 模式 | 额外依赖 | 支持类型 | 说明 |
|------|----------|----------|------|
| `json`（默认） | 无 | JSON 可序列化类型 | 最安全，跨语言兼容 |

**JSON 模式**：参数通过 `json.dumps` 序列化，结果通过 `json.loads` 反序列化。不支持的类型会使用 `default=str` 回退。

---

## 与 async 结合

装饰器会自动检测被装饰函数是否为异步函数：

```python
@sandbox(template="code-interpreter-v1")
async def async_analyze(data):
    import pandas as pd
    df = pd.DataFrame(data)
    return df.describe().to_dict()

# 异步调用
result = await async_analyze({"col": [1, 2, 3]})
```

同步装饰函数会阻塞到远程结果返回。在异步应用中，装饰 `async def` 函数并使用 `await` 调用。

---

## 复用沙箱

显式创建实例，保留 ID 并决定何时删除。装饰器连接该实例，执行后关闭借用的客户端。

```python
import asyncio
from agent_sandbox import ProviderSandbox
from agent_sandbox.declarative import sandbox

async def main():
    instance = await ProviderSandbox.create(template="base")
    try:
        @sandbox(sandbox_id=instance.id)
        async def calculate():
            import math
            return math.factorial(6)

        print(await calculate())
    finally:
        await instance.kill()

asyncio.run(main())
```

自动创建时传入 `keep_alive=True` 会保留远程沙箱，但装饰器只返回函数结果。需要重连或主动清理时，优先使用上面的显式管理方式。

## 注册应用命令

在模板镜像内注册应用命令并启动服务：

```python
# commands.py inside the template image
from agent_sandbox.server import command, start

@command()
def demo(x: int, y: str) -> str:
    return f"{y}={x}"

if __name__ == "__main__":
    start(9000)
```

按[模板启动指南](template-workflows.md)启动模板，再连接返回的沙箱 ID。`application_token` 使用启动服务时的同一个应用令牌：

```python
from agent_sandbox import ProviderSandbox

instance = await ProviderSandbox.connect(sandbox_id)
try:
    async with await instance.application_client(9000, token=application_token) as client:
        print(await client.commands.run("demo", x=1, y="hello"))
finally:
    await instance.close()
```

本机 `sandbox.register` 不会把函数上传到远程沙箱。命名 HTTP 命令需要部署模板并运行应用服务；直接执行函数使用前述函数装饰器。

## 限制

1. **参数序列化**：函数参数和返回值必须是 JSON 可序列化的（不支持的类型会回退为 `str`）
2. **函数源码**：装饰器通过 `inspect.getsource()` 获取函数源码，Lambda 和动态生成的函数不支持
3. **导入**：远程沙箱中需要的库必须通过 `packages` 参数预安装，或已包含在模板中
4. **注册命令参数类型**：`@sandbox.register` 支持 `str`、`int`、`float`、`bool` 和 `list[str]`，不支持任意对象类型
5. **闭包变量**：函数中引用的外部变量不会被自动序列化，请使用显式参数传递
6. **执行环境隔离**：被装饰的函数在独立的远程 Python 进程中执行，不共享本地进程的状态

---

## 下一步

- [SDK 使用指南](sdk-usage.md) — 直接使用 Sandbox API
- [编写模板](authoring-templates.md) — 创建自定义模板
- [API 参考](../reference/api-reference.md) — 完整 API 签名
