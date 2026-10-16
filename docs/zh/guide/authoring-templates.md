# 编写模板

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（`npm install -g @agent-sandbox/cli`）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

这是 **Server SDK**：`commands.py` 随镜像启动，在沙箱里面提供 HTTP 服务。在你的机器上创建并调用沙箱见 [Client SDK](client-sdk.md)。

本文档介绍如何创建自定义 Agent Sandbox 模板，包括目录结构、字段参考、能力声明、注册命令和发布流程。

模板是一个由纯文件组成的目录，可手写也可生成。`abx template scaffold` 命令有三种生成方式（内置脚手架、一句话描述、适配已有源码的项目）；该工作流记录在 CLI 仓库：[模板编写（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md)。

---

## 模板目录结构

一个完整的模板目录结构如下：

```text
my-template/
├── template.yaml      # 必须 — 模板定义
├── Dockerfile         # 可选 — 自定义 Docker 构建（优先于 template.yaml 中的构建步骤）
├── commands.py        # 可选 — 用 @command 注册命名命令
└── README.md          # 可选 — 模板说明
```

`template.yaml` 是唯一必需的文件。

---

## template.yaml 基础示例

```yaml
name: my-python-template
version: "1.0.0"
description: "Python 数据分析环境，预装 pandas 和 matplotlib"
author: "Your Name"
tags:
  - python
  - data-analysis

env:
  PYTHONUNBUFFERED: "1"
  APP_DIR: "/app"

capabilities:
  - shell
  - files
  - code
  - terminal

ports:
  - 8080
```

---

## 字段参考

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | ✅ | — | 模板名称 |
| `version` | `str` | ❌ | `"1.0.0"` | 语义版本号 |
| `description` | `str` | ❌ | `""` | 模板描述 |
| `env` | `dict[str, str]` | ❌ | `{}` | 环境变量 |
| `cpu_count` | `int` | ❌ | `None` | 默认 CPU 核数 |
| `memory_mb` | `int` | ❌ | `None` | 默认内存 MB |
| `ports` | `list[int]` | ❌ | `[]` | 暴露的端口列表 |
| `author` | `str` | ❌ | `""` | 作者 |
| `license` | `str` | ❌ | `""` | 许可证 |
| `tags` | `list[str]` | ❌ | `[]` | 标签 |
| `capabilities` | `list[str]` | ❌ | `None` | 能力声明（见下文） |

详细的字段定义参见 [template.yaml 规范](../reference/template-yaml-spec.md)。

---

## 能力声明

通过 `capabilities` 字段声明模板支持的运行时能力：

```yaml
capabilities:
  - shell      # Shell 命令执行
  - files      # 文件系统操作
  - code       # Code Interpreter
  - terminal   # PTY 终端
  - ports      # 端口网络访问
```

**标准能力集**：`shell`、`files`、`code`、`terminal`、`ports`

**默认能力集**（不声明 `capabilities` 时）：`shell`、`files`、`code`

`terminal` 和 `ports` 必须在模板中显式声明才能使用。能力令牌在模板解析层（`resolve_capabilities()`）使用，解析策略为 fail-closed：如果模板 YAML 格式错误或缺失，解析器会抛出 `TemplateParseError`（E2004）而非默认授予能力。所有 API 方法均可调用，不受声明能力限制；能力声明作为元数据用于模板校验和模型推断。

`commands.py` 启动的进程在 9000 端口提供一套固定的 HTTP API。Dockerfile 的基础镜像随模板而变，路由不变。服务器注册九个能力组。`core` 保持开启。`dev_tools`、`browser` 和 `agents` 默认关闭。`agents` 的路由已经注册，在 `ABX_SERVER_ENABLED_GROUPS` 包含 `agents` 之前保持关闭。每个组打开哪些路由、如何调用，见[模板服务器 HTTP API](template-server-api.md)。

---

## 注册命令

命名命令只有一种机制：注册在模板 server 里的函数。`template.yaml` 没有 `custom_commands` 键（客户端会拒绝它）。在 `commands.py` 中用装饰器注册 Python 函数：

```python
from agent_sandbox.server import command, start

@command("demo", description="回显参数。")
def demo(x: int, y: str) -> str:
    return f"{y}={x}"

if __name__ == "__main__":
    start(9000)
```

文件上传和下载是 server 的端点（`/files/*`、`/upload`、`/download`），属于默认开启的 `file_ops` 组，不在 `commands.py` 里注册。部署不会应用 `server:` 块。可选组用 `default_table().enable_group(CapabilityGroup.DEV_TOOLS)`（参数是 `CapabilityGroup`，不是字符串）或 `ABX_SERVER_ENABLED_GROUPS` 打开。`dev_tools`、`browser`、`agents` 默认关闭。

注册的命令由沙箱内 HTTP server 提供（`POST /commands/{name}`）。客户端用 `await sandbox.run("demo", x=1, y="hello")` 或 `abx run <id> demo --arg x=1 --arg y=hello` 调用，用 `sandbox.list_commands()` 或 `abx sandbox command list <id>` 列出。裸 shell 命令是另一个调用：`sandbox.commands.run(cmd)`。

---

## Dockerfile 自定义

目录里有 `Dockerfile` 时，镜像就是这个文件。`template.yaml` 不安装软件包。`base`、`system_packages`、`python_packages`、`node_packages`、`commands` 不是构建输入。

默认提供者是 `alicloud-express`。它的 Dockerfile 从 FC 基础镜像开始，不写 `CMD` 或 `ENTRYPOINT`。`<region>` 默认 `cn-hangzhou`，`<tag>` 默认 `v0.0.49`。额外的包写成这个基础镜像上的 `RUN`。`FROM python:3.11-slim` 不是这张镜像。

```dockerfile
FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
WORKDIR /home/user/app
COPY commands.py /home/user/app/commands.py
EXPOSE 9000
```

OpenSandbox 以及没有 `[template]` 配置的提供者使用 `FROM python:3.12-slim`、`WORKDIR /app` 和 `CMD ["python3", "commands.py"]`。可直接复制的文件（含 server wheel 安装）在 `agent-sandbox-sdk/SKILL.md`。

## 提供者模板配置

服务端 SDK 不选择沙箱提供者，`agent_sandbox.server` 也不导入提供者。端口 9000 仍是服务端的监听默认值。FC 保留端口（49983、5000、49999）属于 `alicloud-express` 模板配置，不是 HTTP API 的属性。

镜像契约归 CLI。CLI 用 `--provider` / `ABX_PROVIDER` / 默认的 `alicloud-express` 解析提供者，再把这一份配置写进 Dockerfile 和模板提示：

- `alicloud-express`：`FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`，不写 `CMD` 或 `ENTRYPOINT`，由平台 `start_cmd` / `ready_cmd` 启动，用户 `user`，工作目录 `/home/user/app`。
- 其他提供者：若插件的 `abx-provider.toml` 没有 `[template]` 表，则使用通用配置（`FROM python:3.12-slim`、`CMD ["python3", "commands.py"]`、`WORKDIR /app`、用户用镜像默认值）。缺少配置会被写明，并且不会退回 FC 镜像。

`template.yaml` 用 `user` 和 `workdir` 记下同一对默认值。Dockerfile 的 `WORKDIR` 与 `workdir` 一致。只有 `user` 非空时才写 `USER`，因为 `python:3.12-slim` 里没有名为 `user` 的账户。之后的单次命令可以自带工作目录；这两个字段是沙箱的默认值，和 E2B 模板里的 user / workdir 是同一件事。

`commands.py` 只导入 `agent_sandbox.server`，并在 `if __name__ == "__main__"` 下调用 `start(port)`。镜像安装 `agent-sandbox-server`。

---

## 发布与部署模板

Python SDK 是运行时客户端，不构建也不部署模板。构建、推送并注册模板用 CLI：`abx template build` 和 `abx template deploy`（或 `abx deploy`）。见[构建与部署](build-and-deploy.md)。

将模板发布到 GitHub、从本地或 registry 安装模板、适配已有项目（`abx template scaffold --adopt`），或通过命令行构建并注册模板（`abx deploy`、`abx template deploy|create`），请使用 `abx` CLI；见[相关：abx CLI](#相关abx-cli)。

## 下一步

- [使用模板](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md) — 安装和使用模板
- [template.yaml 规范](../reference/template-yaml-spec.md) — 所有字段精确定义
- [声明式用法](declarative-usage.md) — @sandbox 装饰器

---

## 相关：abx CLI

模板的命令行工作流记录在 CLI 仓库：[模板编写（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md)（`abx template scaffold`、`--adopt`、发布、`template install`）、[部署与构建](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)（`abx deploy`、`abx template deploy|create`）和[模板使用](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md)。
