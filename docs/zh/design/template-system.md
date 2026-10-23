# 模板系统设计

模板采用规范 4 和显式工作流契约 1。模板描述所提供的软件及其具名使用方式。提供方适配器、所选 SDK/CLI 调用方、本地配置和可信验证是彼此独立的输入；安装 Python 或 HTTP 服务不会实现提供方解释器操作。

当前规范见 [template.yaml 规范](../reference/template-yaml-spec.md)，发布权威是 [template-v4.schema.json](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v4.schema.json)，执行说明见 [显式模板工作流](../guide/template-workflows.md)。Node.js CLI 由 [agent-sandbox](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) 维护；Python 仓库拥有客户端、沙箱内服务和共享的[工作流契约](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts)。

## 1. 官方核心模板

当前模板清单以 [awesome-templates](https://github.com/Alibaba-Agent-Sandbox/awesome-templates) 为准。进入目录、作者提供的 smoke 命令和历史验收，都不保证每个提供方/调用方可以运行每条工作流。应读取真实 manifest 和所选工作流，不能使用固定的首发环境承诺推导支持。

<a id="tier-1--首发模板5-个"></a>
<a id="tier-2--扩展模板5-个"></a>
以前的首发/扩展列表由源仓库目录取代。本文不承诺模板发布日期、已安装依赖版本或自动安全认证。

<a id="base"></a>
<a id="python-base"></a>
<a id="python-data-science"></a>
<a id="node-web"></a>
<a id="code-interpreter"></a>
<a id="browser-automation"></a>
<a id="full-stack"></a>
<a id="go-dev"></a>
<a id="java-dev"></a>
<a id="ml-gpu"></a>

## 2. 模板来源与分发机制

### 2.1 模板名解析规则

源码索引只定位唯一权威 `template.yaml`，不能覆盖其工作流或启动命令。提供方托管条目内嵌完整严格 manifest，且归属于该提供方。本地源码路径、Git 修订、镜像引用和托管 ID 表示不同输入类型，不能当作可互换别名。

| 工作流输入 | 含义 |
| --- | --- |
| `source` | 项目快照，需要已实现的准备路径及显式构建配置 |
| `image` | 已准备镜像；Python 启动器要求不可变 SHA256 引用 |
| `managed` | 提供方拥有的引用；启动需要提供方解析出的不可变身份 |
| `service` | 已存在的应用 HTTP 服务，使用显式绑定及 `startup: none` |

未知引用不授予默认操作。Python 独立启动器不准备源码项目；未解析的托管 ID 在创建前拒绝。源码 Dockerfile 不会根据 `base` 元数据被重写，也不会替换成猜测的备用镜像。

### 2.2 各入口使用方式

对于已有沙箱，使用 `ProviderSandbox.connect(...)`，再通过 `await sandbox.application_client(port, token=...)` 访问应用。这会解析独立的提供方端口端点；提供方内部控制或执行端点不是应用 URL。

对于新建的已准备镜像工作流，`agent_sandbox.api.launch_workflow(...)` 接收真实 manifest、工作流 ID、提供方和不可变引用。在发送应用负载前检查条件。见[完整 Python 示例与限制](../guide/template-workflows.md#python-应用调用)。

CLI 目录指引使用 `abx template launch SOURCE --workflow ID`；如果存在 portable profile，可移植源码构建还需显式选择 `--build-profile portable`。所选 CLI/提供方必须实际支持对应输入及启动路径。Express 当前只声明 managed 输入和 entrypoint/none 启动；这说明本项目实现范围，不能据此断言平台其他原生 API 无法构建镜像。

### 2.3 GitHub tarball 解析流程

源码获取和执行分开：解析请求的源码修订，安全获取项目，读取唯一 manifest，冻结符合条件的源码快照，再规划所选工作流。下载归档或命中缓存都不证明提供方支持或运行验证通过。远端认证失败不能静默改为匿名重试，也不能改变源码身份。

### 2.4 模板包结构（仓库/subdir 内容）

```text
my-template/
├── template.yaml       # spec_version: 4，workflow_contract_version: 1
├── Dockerfile          # 显式原生镜像构建
├── Dockerfile.portable # 可选，显式选择的构建 profile
├── commands.py         # 使用命令服务时的应用命令
└── requirements.txt    # 需要时声明应用依赖
```

可选 `AGENTS.md` 由外部智能体工具读取，不会增加运行时操作。快照身份排除不安全的秘密/忽略路径，拒绝不支持的符号链接输入；证据必须写到冻结快照之外，避免自引用。

### 2.5 官方模板仓库

[awesome-templates](https://github.com/Alibaba-Agent-Sandbox/awesome-templates) 拥有源码 manifest、Dockerfile、发布 schema 和目录。[awesome-providers](https://github.com/Alibaba-Agent-Sandbox/awesome-providers) 拥有可安装的适配器。内置 Express 描述由 CLI 拥有。Registry 和官网消费这些来源，不会补足缺失的处理器。

### 2.6 GitHub Token 配置（私有仓库与限流）

源码下载凭据属于获取过程，提供方凭据属于控制面，网关请求头属于解析出的端点，应用 token 属于应用。不能跨受众复制。CLI 实际 token 配置以其维护的文档为准；不得把凭据或签名端点 URL 放入 manifest、receipt 或公开诊断。

### 2.7 本地缓存管理

缓存只是获取优化。复用需要匹配预期身份，不能跳过当前 manifest 校验、操作规划或验证资格检查。可变分支名不能代替当前 receipt 要求的不可变源码/构建/产物身份。

## 3. 自定义模板方式

<a id="方式一cli--dockerfile"></a>
### Dockerfile 与显式构建 profile

将真实依赖、用户、文件和入口设置写入所选 Dockerfile。Portable profile 是显式替代方案，不是对原生构建的静默重写。源码根 context 使用带引号字符串 `'.'`，使 YAML 调用方对其类型达成一致。

<a id="方式二sandboxyaml-声明式"></a>
### 严格 manifest

`template.yaml` 承载模板元数据和具名工作流。单独的 `sandbox.yaml` 客户端配置不是元数据别名。具名应用函数通过沙箱内服务的 `@command` 注册；YAML 字段不会生成函数。见[编写模板](../guide/authoring-templates.md)。

<a id="方式三发布到-github按-tagbranchsha-拉取"></a>
### 发布源码

发布真实源码修订并保留 manifest/构建输入。可变 ref 可以定位源码，但验证必须绑定解析出的内容。发布源码不等于发布提供方托管引用，也不会使工作流变成已验证。

## 4. 模板规范（template.yaml）

### 完整字段定义

使用完整[规范参考](../reference/template-yaml-spec.md#完整字段定义)和源仓库 schema，避免维护另一份独立字段清单。发布必须包含 name、version、description、author、license 元数据。`spec_version` 是整数 `4`；`workflow_contract_version` 是整数 `1`。

### 字段分类说明

| 声明 | 职责 |
| --- | --- |
| `provides` | 模板实际提供的服务协议/版本/端口和应用操作 |
| `workflows` | 具名的 kind、input、startup、binding、operation、service 及附加条件 |
| `default_workflow` | 未指定其他 ID 时选择的唯一已声明工作流 |
| `start_cmd` / `ready_cmd` | 显式启动/就绪命令；非空就绪命令即使配合 entrypoint/none 也需要执行能力 |
| `build_profiles` | 显式 Dockerfile/context 选择，不做隐式可移植改写 |
| `server` | 沙箱内端点策略，必须由所选构建/启动路径实际安装并应用 |

旧 `capabilities`、`tested_on`、手写 `providers` 兼容结论和未知工作流字段均被拒绝。省略字段不授予 `{shell, files, code}`。`base` 仍是合法元数据，不会静默改写 Dockerfile `FROM`，也不会构造模板继承链。

### 关键设计要点

1. 模板提供软件和应用协议，无法通过声明实现平台适配器或调用方处理器。
2. 提供方操作契约按调用方分别声明精确操作，以及支持的输入/启动方式。例如 `exec.run`、`ports.resolve`、`code.context.execute` 是不同操作。
3. 规划采用三值：T 允许继续本地检查；F 表示明确不匹配或缺失实现；U 表示信息尚未解析。F 优先于 U。本项目缺少适配不能证明原生平台缺少该能力。
4. 应用服务可以通过 shell 启动及已解析 HTTP 端口使用，不需要统一解释器。缺少解释器只阻断对应解释器工作流。
5. SDK/CLI 传输和网络绑定必须符合所选操作。即使处理器存在，服务端策略仍可拒绝应用端点。未知发现结果按拒绝处理；应用负载在协议及策略检查之后发送。
6. 成熟度、本地环境检查和当前可信验证相互独立。Stable 标签或历史测试不能认证当前 manifest、调用方及绑定。

### 示例：基于 GitHub 模板的扩展

扩展源码项目应编辑真实 Dockerfile 和严格 manifest，不能依赖远端 `base.from` 继承规则。源仓库的 [python-hello manifest](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/python-hello/template.yaml) 为同一 `app` 服务分别声明源码及已准备镜像应用工作流，portable 构建 profile 需显式选择。借鉴这一结构仍需实际提供方/调用方支持及本地凭据，不是就绪保证。

## 5. 模板版本管理

### 语义版本号

模板 `version` 是元数据。规范版本、工作流契约版本、已解析源码修订、manifest 摘要、产物摘要和调用方修订具有不同含义。SemVer 标签不能代替这些身份。

### 版本选择

显式选择源码修订及已声明工作流。已准备镜像启动需要摘要固定的镜像；managed 启动需要不可变提供方解析。Python 启动器不会展开虚构的模板 SemVer 范围，也不会自动把仓库引用翻译成云模板。

### 版本列表

从拥有目录/源码的仓库读取可用版本和 manifest。只有源码、manifest、构建、产物、提供方代码、调用方、工作流、绑定及契约身份匹配，当前验证才具备资格。即使人类可读名称不变，内容变化也会使旧证据无法复用。

## 6. 模板市场架构

Registry 聚合源仓库元数据、计算分范围规划并展示合格证据。官网展示已接收的严格目录快照。两者构建目录页面时均不执行访客工作负载，也不获取访客云凭据。

### CLI 命令总览

当前命令面由 [CLI 使用模板指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md) 维护。目录工作流启动显式指定源码及工作流 ID。提供方原生部署、应用部署拓扑和工作流启动各自遵循显式操作要求。

### 模板安全

信任需要独立核实的已批准 CI 来源及匹配产物。模板可增加必需检查，不能移除验证 profile 下限。必需检查缺失、失败或跳过均不合格。作者填写的 PASS JSON、runner 名称或历史 smoke 输出不能自证。签名和安全审计必须有实际证据，不能假定每个目录条目都具备。

## 7. 备注：Session 管理与模板的关系

工作流规划静态源码/产物的某种用法，只拥有其创建的运行资源。创建意图和返回资源 ID 必须持久记录；不确定创建不能自动重试。即使 journal 写入或连接关闭失败，清理仍尝试删除自有资源，未解决资源仍保留以便对账。关闭已有沙箱连接不会取得其所有权，也不删除它。

应用 HTTP 绑定保留沙箱代理前缀及签名 query 值，分离网关请求头与应用 token，检查端点有效期，并拒绝重定向、authority 覆盖及编码命名空间穿越。沙箱内 HTTP 服务仍是独立协议，拥有端点策略和 token scopes；见[服务端 API 设计](server-api.md)。

## 相关：abx CLI

参见 CLI [使用模板](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md)、当前 [Python 工作流指南](../guide/template-workflows.md)、[模板规范](../reference/template-yaml-spec.md)及[应用服务 API](../guide/template-server-api.md)。固定版本标准客户端维持独立公共契约；项目提供方适配器当前不给 Express/E2B/REST 声明统一解释器操作，CubeSandbox/container 仅实现持久默认上下文操作。
