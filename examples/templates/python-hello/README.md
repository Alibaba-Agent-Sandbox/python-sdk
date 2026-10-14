# Python Hello 模板

**Server SDK。** `commands.py` 在沙箱里面启动。`call_api.py` 是 Client SDK：在外面调用已经起来的服务。

> **Fixture**：本目录是主仓库的**离线测试夹具**（`client-sdk/tests/test_templates/` 使用），
> 不是发布真源。模板内容、索引与发布以
> [`alibaba-agent-sandbox/awesome-templates`](https://github.com/alibaba-agent-sandbox/awesome-templates/tree/main/python-hello)
> 为准。

基础 Python 开发环境模板。

## 安装

> 以下 `abx` 命令由独立 `cli` 仓库中的 `abx` CLI 提供（`npm install -g @agent-sandbox/cli`）。

```bash
abx install ./examples/templates/python-hello --registry-type local
```

## 使用

```bash
abx create --template python-hello
```

### 命名命令（端到端）

容器启动后会自动运行 `commands.py`，监听端口 9000，提供以下命名命令：

```bash
# 打招呼
abx run <sandbox-id> hello --name Alice
# → Hello, Alice!

# 执行 Python 代码
abx run <sandbox-id> run_script --code "print(1+1)"
# → 2
```

SDK 侧等价写法：

```python
from agent_sandbox import Sandbox

sandbox = Sandbox.create_sync(template="python-hello")
print(sandbox.run_sync("hello", name="Alice"))  # Hello, Alice!
```

### 上传 / 下载

```bash
abx upload <sandbox-id> ./local_file.txt /app/remote.txt
abx download <sandbox-id> /app/remote.txt ./local_file.txt
```

## 环境

- 基础镜像: Ubuntu 22.04
- Python 3 + pip
- 容器内运行时: `pip install agent-sandbox-server`（提供 `agent_sandbox.server`）
- 工作目录: /app
