# Python Hello 模板

> **Fixture**：本目录是主仓库的**离线测试夹具**（`client-sdk/tests/test_templates/` 使用），
> 不是发布真源。模板内容、索引与发布以
> [`Easy-Sandbox/awesome-templates`](https://github.com/Easy-Sandbox/awesome-templates/tree/main/python-hello)
> 为准。

基础 Python 开发环境模板。

## 安装

> 以下 `ebx` 命令由独立 `cli` 仓库中的 `ebx` CLI 提供（`npm install -g @easy-sandbox/cli`）。

```bash
ebx install ./examples/templates/python-hello --registry-type local
```

## 使用

```bash
ebx create --template python-hello
```

### 命名命令（端到端）

容器启动后会自动运行 `commands.py`，监听端口 9000，提供以下命名命令：

```bash
# 打招呼
ebx run <sandbox-id> hello --name Alice
# → Hello, Alice!

# 执行 Python 代码
ebx run <sandbox-id> run_script --code "print(1+1)"
# → 2
```

SDK 侧等价写法：

```python
from easy_sandbox import Sandbox

sandbox = Sandbox.create(template="python-hello")
result = sandbox.custom("hello", name="Alice")
print(result.value)  # Hello, Alice!
```

### 上传 / 下载

```bash
ebx upload <sandbox-id> ./local_file.txt /app/remote.txt
ebx download <sandbox-id> /app/remote.txt ./local_file.txt
```

## 环境

- 基础镜像: Ubuntu 22.04
- Python 3 + pip
- 容器内运行时: `pip install easy-sandbox-server`（提供 `easy_sandbox.server`）
- 工作目录: /app
