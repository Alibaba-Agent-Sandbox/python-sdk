# template.yaml 规范

当前模板使用 `spec_version: 5`。发布清单的完整权威 schema 是 [awesome-templates/template-v5.schema.json](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v5.schema.json)；共享启动契约见 [contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts)。应用部署拓扑、hooks 和持久状态字段仍由完整 schema 定义。

## 文件位置

每个源码模板的根目录包含唯一的 `template.yaml`。目录索引只定位该文件，不重复声明工作流；托管模板条目内嵌完整声明。Dockerfile、命令模块和依赖文件与清单一起组成源码输入。

## 完整字段定义

### 基础信息

发布 schema 要求 `name`、`version`、`description`、`author`、`license` 等元数据；`tags`、`priority`、`wave`、`smoke` 的规则见完整 schema。SDK 的运行时模型不是整个发布 schema 的替代品。

### 运行时配置

`env` 是字符串映射，`ports` 是端口列表。`start_cmd`、`ready_cmd` 与显式启动方式配合使用；镜像和服务必须实际提供声明的监听端口。SDK 解析这些字段不会自动改写 Dockerfile。

### 资源规格

源码发布清单使用 `resources.cpu`、`resources.memory`；SDK 运行时配置还可携带 `cpu_count`、`memory_mb`。应用部署的资源和拓扑字段以完整 schema 为准，不能用工作流规划代替部署执行。

### 沙箱代数

`generation` 属于具体模板和提供方启动配置，目录源码模板 schema 当前要求 `2`。是否可以创建，还要检查提供方实际支持的输入和启动方式。

<a id="能力声明"></a>
### 模板启动

`spec_version` 为整数 `5`。`provides` 通过 `protocol`、`version`、`port`、`operations`
描述全部服务，也可以为空。`start_cmd` 整体启动模板一次；没有它时使用镜像或平台模板
自身入口。`ready_cmd` 如有声明，在返回服务客户端前执行。固定 `image` 或
`provider` 与 `template_id` 可以定位已准备模板；其他情况由 CLI 准备源码。
Python 要求已准备好的引用。

从规范 4 迁移时删除 `workflow_contract_version`、`default_workflow`、`workflows`。
启动时不再选择 application/exec/interpreter 类型或某个操作。旧 `capabilities`、
`tested_on` 和手填 Provider 兼容表仍拒绝。具体调用能力由 Provider 和服务端实际检查。
见[模板启动指南](../guide/template-workflows.md)。

### 已移除的键：`custom_commands`

`custom_commands` 被拒绝。命名命令由服务端 `commands.py` 中的 `@command` 注册，客户端通过应用 HTTP 调用，不由 YAML 生成函数。

### 服务端策略（`server`）

可选。声明模板对外暴露哪些 SandboxServer 端点以及各端点的限制（设计见
[细粒度能力管理](../design/fine-grained-capabilities.md)）。省略即保持服务端默认行为。`SandboxTemplate` 会对该块做结构校验（未知键报错）；
取值由 `agent-sandbox-server check-config` 校验。服务端读取 `/etc/agent-sandbox/server-policy.json`、`ABX_SERVER_POLICY_FILE` 或 `ABX_SERVER_POLICY`。必须由选定构建/启动流程实际安装策略，仅填写 YAML 不会自动应用。

| 键 | 类型 | 说明 |
|----|------|------|
| `preset` | `str` | `default`、`transfer-only`、`read-only`、`hardened`、`locked` |
| `base_dir` | `str` | 相对路径的根目录，也是默认的路径边界 |
| `groups` | `list[str]` 或 `map[str, bool]` | 打开能力组（`[agents, dev_tools]`），或开/关（`{process: false}`）。组是它的端点 id 的别名 |
| `defaults` | 规则 | 先于各端点自身规则应用于所有端点 |
| `endpoints` | `map[str, 规则]` | 以端点 id 为键的逐端点规则（`files_download_stream`、`shell` 等） |
| `auth` | map | `tokens`（`id`、`scopes`、`token_env` 或 `token_sha256`）、`allow_anonymous`、`anonymous_scopes` |

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


## 完整示例

此源码发布示例包含 schema 要求的元数据；基础镜像占位符必须通过显式配置落实后才能构建。

```yaml
name: my-python-template
version: 1.0.1
description: Scaffold for a new Agent Sandbox template. Not a catalog entry.
author: alibaba-agent-sandbox
license: Apache-2.0
spec_version: 5
base: fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
generation: 2
start_cmd: agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
ready_cmd: agent-sandbox-server healthcheck --port 9000
resources:
  cpu: 2
  memory: 2048
ports:
- 9000
tags:
- example
- skeleton
priority: P2
wave: other
env:
  ABX_SERVER_TOKEN: ''
smoke:
- command: hello
  args:
    name: Express
  expect: Hello, Express!
provides:
  app:
    protocol: agent-sandbox-server
    version: 2
    port: 9000
    operations:
    - commands.list
    - commands.run
```

## 构建说明

`base` 是合法的来源/模板元数据；构建以选定的有效 Dockerfile 和显式构建配置为准，不自动替换 `FROM`、用户、复制路径或入口。依赖通过镜像中的原生依赖文件安装。Python 启动器不准备源码，使用已准备的 `image`/`managed` 引用或显式 `service` 路径。
