# template.yaml 规范

本文档精确定义 `template.yaml` 文件的所有字段（使用者视角）。

---

## 文件位置

模板的 `template.yaml` 位于模板目录根下：

```text
my-template/
├── template.yaml    ← 本文档定义的文件
├── Dockerfile       # 可选
└── ...
```

安装后位于 `~/.abx/templates/<template-name>/template.yaml`。

---

## 完整字段定义

### 基础信息

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | ✅ | — | 模板名称，用于 `--template` 参数 |
| `version` | `str` | ❌ | `"1.0.0"` | 语义版本号 |
| `description` | `str` | ❌ | `""` | 模板描述 |
| `author` | `str` | ❌ | `""` | 作者 |
| `license` | `str` | ❌ | `""` | 许可证标识（如 `"MIT"`） |
| `tags` | `list[str]` | ❌ | `[]` | 分类标签 |

### 运行时配置

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `env` | `dict[str, str]` | ❌ | `{}` | 环境变量（生成 `ENV` 指令） |
| `ports` | `list[int]` | ❌ | `[]` | 暴露的端口（生成 `EXPOSE` 指令） |

### 资源规格

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `cpu_count` | `int` | ❌ | `None` | 默认 CPU 核数 |
| `memory_mb` | `int` | ❌ | `None` | 默认内存 MB |

### 沙箱代数

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `generation` | `int` | ❌ | `1` | 沙箱代数：`1` = 一代（rund），`2` = 二代（MicroVM，Beta）。设置后，CLI 命令（`template deploy`、`template build`、`template create`）会读取此值，除非通过 `--generation` 参数显式覆盖。 |

### 能力声明

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `capabilities` | `list[str] \| null` | ❌ | `null` | 运行时能力列表 |

**可选值**（标准能力集 `STANDARD_CAPABILITIES`）：

| 能力 | 说明 |
|------|------|
| `shell` | Shell 命令执行（`commands.run()` 等） |
| `files` | 文件系统操作（`files.read()` 等） |
| `code` | Code Interpreter 代码执行（`run_code()` 等） |
| `terminal` | PTY 终端会话（`get_terminal()`） |
| `ports` | 端口 URL 访问（`network.get_url()` 等） |

**行为规则**：
- `null`（未声明）→ 使用默认能力集 `{shell, files, code}`
- 显式列表 → 仅启用列出的能力（可以是标准能力集的子集或超集）
- 列表中的值必须是标准能力集中的项，否则校验失败（抛出 `TemplateParseError` E2004）

### 已移除的键：`custom_commands`

`custom_commands` 不是 `template.yaml` 的键。客户端会拒绝包含它的文件（`TemplateParseError`，E2004）。命名命令只有一种机制：注册在模板 server 里的函数（`commands.py` 中的 `@sandbox.register`），用 `sandbox.run(name, **kwargs)` 或 `abx run <id> <name>` 调用。见[编写模板](../guide/authoring-templates.md#注册命令)。

### 服务端策略（`server`）

可选。声明模板对外暴露哪些 SandboxServer 端点以及各端点的限制（设计见
[细粒度能力管理](../design/fine-grained-capabilities.md)）。省略即保持服务端默认行为。`SandboxTemplate` 会对该块做结构校验（未知键报错）；
取值由 `agent-sandbox-server check-config` 校验。工具链会把它编译为 `/etc/agent-sandbox/server-policy.json`，服务端启动时自动加载。

| 键 | 类型 | 说明 |
|----|------|------|
| `preset` | `str` | `default`、`transfer-only`、`read-only`、`hardened`、`locked` |
| `base_dir` | `str` | 相对路径的根目录，也是默认的路径边界 |
| `groups` | `list[str]` 或 `map[str, bool]` | 打开能力组（`[agents, dev_tools]`），或开/关（`{process: false}`）。组是它的端点 id 的别名 |
| `defaults` | 规则 | 先于各端点自身规则应用于所有端点 |
| `endpoints` | `map[str, 规则]` | 以端点 id 为键的逐端点规则（`files_download_stream`、`shell` 等） |
| `auth` | map | `tokens`（`id`、`scopes`、`token_env` 或 `token_sha256`）、`allow_anonymous`、`anonymous_scopes`、`legacy_scopes` |

规则包含 `enabled`、`scopes`、`paths`（`allow`、`deny`、`read_only`、`symlinks`）、`limits`（`max_bytes`、`max_request_bytes`、`timeout_seconds`、`rate_per_minute` 等）、`params`（`overwrite`、`deny_extensions`、`allow_commands` 等）和 `audit`。

```yaml
server:
  preset: transfer-only
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out] }
      limits: { max_bytes: 5MB }
    files_upload_stream:
      paths: { allow: [/home/user/in] }
      params: { overwrite: false }
```

---

## 完整示例

```yaml
name: flask-web
version: "2.0.0"
description: "Flask Web 开发环境"
author: "Agent Sandbox Team"
license: "MIT"
tags:
  - python
  - web
  - flask

env:
  PYTHONUNBUFFERED: "1"
  FLASK_ENV: "development"

ports:
  - 5000
  - 8080

cpu_count: 2
memory_mb: 2048

capabilities:
  - shell
  - files
  - code
  - terminal
  - ports

```

---

## 构建说明

`template.yaml` 只定义运行时配置（能力、server 策略、环境变量、资源）。镜像构建完全由模板目录中的 `Dockerfile` 负责，使用语言原生依赖文件（`requirements.txt` / `package.json`）管理依赖。
