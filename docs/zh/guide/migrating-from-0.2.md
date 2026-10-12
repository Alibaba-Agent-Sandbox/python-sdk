# 从 0.2.x 迁移到 0.3.0

0.3.0 把 Python 项目拆成两个版本号同步发布的 PyPI 发行包，二者共享 `easy_sandbox` 导入命名空间：

| 发行包 | 导入路径 | 内容 |
|--------|----------|------|
| `easy-sandbox` | `easy_sandbox` | 客户端 SDK（`Sandbox`、传输层、协议层、模板 API、`@sandbox`、MCP Server、Agent） |
| `easy-sandbox-server` | `easy_sandbox.server` | 原先随 `easy-sandbox` 一起发布的容器侧运行时 |

`easy-sandbox` 依赖 `easy-sandbox-server==<相同版本>`，因此全新执行 `pip install easy-sandbox`
仍然同时提供 `from easy_sandbox import Sandbox` 与 `from easy_sandbox.server import start`，导入路径不变。
`[server]` extra（`pip install "easy-sandbox[server]"`）作为无害的别名保留。

0.3.0 同时移除了 `[cli]`、`[binary]` extra 与 `ebx` 控制台脚本；请通过
`npm install -g @easy-sandbox/cli` 安装 CLI（见 `cli` 仓库）。

## 原地升级的风险

在已有的 0.2.x 环境中原地升级可能使 `easy_sandbox.server` 不可用：

```bash
pip install -U easy-sandbox
python -c "from easy_sandbox.server import start"
# ImportError: cannot import name 'start' from 'easy_sandbox.server' (unknown location)
```

原因：pip 先安装新依赖 `easy-sandbox-server`，再卸载旧的 `easy-sandbox` 0.2.x；旧版本的文件清单仍包含
`easy_sandbox/server/*`，于是刚装好的文件被删除，`easy_sandbox.server` 退化为空命名空间。全新环境不受影响。

任选其一修复：

```bash
# 仅重装 server 发行包，不动其依赖
pip install --force-reinstall --no-deps easy-sandbox-server

# 或者干净重装
pip uninstall -y easy-sandbox easy-sandbox-server
pip install easy-sandbox
```

SDK 检测到这种状态时（`@sandbox` 装饰器的 `sandbox.server` 代理以及 `sandbox.register.upload()` / `.download()`），
会抛出 `ImportError`，提示 `pip install easy-sandbox-server` 以及 `--force-reinstall --no-deps` 的修复方法。

## 沙箱镜像与模板

模板镜像只需要容器侧运行时，不需要客户端依赖。在 `Dockerfile` 中使用：

```dockerfile
RUN pip3 install --no-cache-dir easy-sandbox-server
```

`ebx template deploy` / `DockerBuilder.inject_sdk_wheel` 已自动注入 `easy-sandbox-server` wheel
（否则回退为 `pip install easy-sandbox-server`）。仅安装 server 的镜像里有 `easy_sandbox/server/`
但没有 `easy_sandbox/__init__.py`；`import easy_sandbox.server` 可正常使用，而 `easy_sandbox.__version__`
在该环境中并不存在，请改用 `easy_sandbox.server.__version__`。

## 检查清单

1. 固定 `easy-sandbox>=0.3.0`；镜像中固定 `easy-sandbox-server`（与客户端版本一致）。
2. 把 `pip install "easy-sandbox[cli]"` 替换为 `npm install -g @easy-sandbox/cli`。
3. 升级后若 `import easy_sandbox.server` 失败，执行上面的修复命令。
4. 容器内使用 `easy_sandbox.server.__version__`，不要使用 `easy_sandbox.__version__`。
