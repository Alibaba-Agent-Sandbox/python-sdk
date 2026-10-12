# 官方基础镜像与 Server SDK

> 状态：**v2（已评审，见 fine-grained-capabilities-review.md）**，与细粒度能力设计一起评审：
> [fine-grained-capabilities-review.md](fine-grained-capabilities-review.md)。
> 产品要求：*所有模板构建都应基于阿里云 Agent Sandbox（FC Agent Sandbox）基础镜像。*
> 英文版为准：[../../en/design/base-image-and-server-sdk.md](../../en/design/base-image-and-server-sdk.md)。

## 1. 基础镜像是什么（证据）

来源：仓库内研究材料（`.agents/evidence/research/2026-09-04-fc-claude-code-image-inspection.md`、`...-fc-sandbox-official-docs.md`），以及官方文档页
[构建自定义镜像模板](https://help.aliyun.com/zh/functioncompute/build-a-custom-image-template)（撰写本设计时获取；当前引用标签 `v0.0.49`，较早的笔记引用 `v0.0.44`）。

| 事实 | 取值 | 来源 |
|------|------|------|
| 仓库/命名规则 | `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/<name>:<tag>`；名称：`base`、`code-interpreter-v1`、`browser`、`claude-code` 等 | 官方文档 |
| 地域规则 | 镜像地域**必须等于**沙箱地域；公开拉取，无需凭据 | 官方文档 |
| 官方镜像作为模板来源 | **原样使用，无构建步骤**（省略 `build_config`）；任何*其他*镜像都会被自动处理：`copy`（重新推送）+ `envdInject` | 官方文档 |
| 进程模型 | `ENTRYPOINT ["/.fce2b/entrypoint"]` = PID 1 网关 + 进程管理器；监管 `envd`（49983），启用时还有 `sandbox-code-interpreter`（49999）；网关在 5000 | 镜像检查 |
| 默认用户 / 工作目录 | `user`、`/home/user`（文档针对 claude-code 镜像；文档说"不要假设每个镜像的默认用户相同"） | 官方文档 + 检查 |
| 自定义镜像的硬性要求 | `linux/amd64`；`/bin/bash` 在该确切路径；可写的标准 `/etc/passwd` 与 `/etc/group`；不使用 ACR 镜像加速 | 官方文档 |
| 条件性要求 | PATH 上有 `python3`（Python `run_code`）、`node`（JS `run_code`），按需 git/ssh/CA 证书 | 官方文档 |
| 模板启动的服务 | *文档*中没有模板级 `startCmd`；服务通过后台命令启动。平台 API 接受 `start_command` / `ready_command`（我们的 `create_official_template` 使用） | 文档 + 仓库 |
| Python | `claude-code` 上为 Ubuntu 25.04 的 Python 3.13（PEP 668"externally managed"），pip 配置指向阿里云镜像源 | 镜像检查 |

## 2. 决定

**Server SDK 层面的设计工作*是*值得做的。模板构建通过脚手架、文档化的契约、辅助函数和 lint 默认走向官方基础镜像，而不是悄悄改变现有 API 的行为。**

理由：

1. **这是正确性问题，不是品味问题。** `create_official_template(envd_inject=False)` 是我们的默认路径：只有镜像里已经包含 envd 才能得到可用的沙箱。
   基于 `FROM ubuntu:22.04` 构建的模板（今天 `Image()` 的默认值和 `python-hello` 夹具）除非平台构建器注入，否则没有 envd。基于官方镜像可使默认路径有效，
   并让平台跳过 `copy` + `envdInject` 构建函数（更快、更省、环节更少，envd/网关版本都是平台测试过的）。
2. **Server SDK 必须有个落脚点。** 把 `easy-sandbox-server` 叠加到官方镜像上，得到边界清晰的目标：已知的 PID 1、已知的用户/HOME（默认 `EBX_SERVER_BASE_DIR=/home/user` 吻合）、
   已知的端口（49983/5000 被占用 -> 9000/9001 空闲）。
3. **不破坏未配置的调用方。** `Image()` 仍然 `FROM ubuntu:22.04`；`DockerBuilder.build*` 仍接受任何 Dockerfile。新行为是可选的或建议性的（警告）。默认值的翻转将在变更日志中以弃用方式预告。

## 3. 契约（叠加在基础镜像之上的 Dockerfile 可以依赖什么）

写在 `server-api.md` 里与 `docs/en/reference/base-image-contract.md` 等价的章节中，并由 `easy_sandbox.api.base_image.BaseImageContract` 强制执行：

| 项 | 契约 |
|----|------|
| FROM | `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`（`official_base_image(region=, variant=, tag=)`） |
| 不要覆盖 | `ENTRYPOINT`（网关是 PID 1）；**不要**依赖 `CMD` 启动服务 |
| 服务启动 | 平台 `start_cmd = "easy-sandbox-server serve --port 9000"`，`ready_cmd = "easy-sandbox-server healthcheck --port 9000"`；兜底 `Sandbox.start_server()`（envd 后台命令 + 就绪轮询） |
| 端口 | 49983 envd、5000 网关、49999 代码解释器（保留）；**9000** 服务端 HTTP、**9001** PTY WebSocket |
| 用户 | 以 `user` 运行（经 envd/启动命令）；文件位于 `/home/user`；应用代码在 `/home/user/app`（若 `EBX_SERVER_BASE_DIR` 包含它，旧的 `/app` 仍可用） |
| Python | 脚手架检查 `command -v python3`；以 `PIP_BREAK_SYSTEM_PACKAGES=1`（PEP 668）安装 |
| SDK 注入 | `COPY *.whl /tmp/` + `pip install`，PyPI 兜底**固定为客户端版本**（同步发布） |
| 策略 | `COPY server-policy.json /etc/easy-sandbox/server-policy.json`（自动加载，见细粒度文档第 4 节） |
| 平台 | `linux/amd64`、`/bin/bash`、可写的 `/etc/passwd`、`/etc/group`（基础镜像已满足） |

## 4. 实现了什么

**server-sdk**

* `easy-sandbox-server` 控制台脚本与 `python -m easy_sandbox.server`（`__main__.py`）：`serve`（默认；`--host --port --commands <file-or-module> --policy <json> --preset <name> --base-dir`）、
  `healthcheck`（HTTP GET `/health`，退出码 0/1，用于 `HEALTHCHECK` 和 `ready_cmd`）、`check-config`（校验并 lint 策略，打印有效端点表）、`version`。
  `--commands` 会导入用户模块，使其 `registry.command(...)`/`table.route(...)` 的副作用完成注册（相当于原来 `commands.py` 里的 `start()`），然后开始服务，
  模板不再需要自己写 `commands.py` 的样板代码。
* `easy_sandbox.server.contract` 常量（端口、路径、环境变量名），由 CLI/服务端共享。
* 策略自动加载（`/etc/easy-sandbox/server-policy.json`）。
* `pyproject.toml`：`[project.scripts] easy-sandbox-server = "easy_sandbox.server.__main__:main"`。

**client-sdk**

* `easy_sandbox/api/base_image.py`：`OFFICIAL_REGISTRY_FMT`、`DEFAULT_BASE_VARIANT="base"`、`DEFAULT_BASE_TAG`、`official_base_image(...)`、`is_official_base_image(ref)`、
  `BaseImageContract`、`lint_dockerfile(text) -> list[BaseImageIssue]`、`scaffold_dockerfile(...)`（第 3 节的 Dockerfile 文本）、`SERVER_START_CMD`、`SERVER_READY_CMD`。
* `Image.official_base(variant, region, tag)` 类方法（链式 API 其余不变）；`Image.build()` 与 `DockerBuilder.build*()` 调用 `lint_dockerfile`，对非官方基础镜像记录警告（不是错误），并指出后果（需要 `envd_inject=True`）。
* `Sandbox.start_server(...)`（远程启动 + 就绪）与 `Sandbox.server` 客户端。
* `SandboxTemplate.server`（经结构校验的策略块）。曾考虑声明式的 `SandboxTemplate.base_image` 字段，但**没有添加**：基础镜像的唯一事实来源是 Dockerfile，lint（`B001`）直接从那里读取。

**未实现（有理由）**

* 不改变 `DockerBuilder` 的 `envd_inject=False` 默认值，也不对非官方镜像自动翻转：那会改变未配置构建发给平台的内容。改为警告 + 文档 + CLI 跟进项。
* 不在自定义基础镜像中打包服务端 wheel：wheel 注入已覆盖"从 PyPI 安装"和"开发检出"两种情况，并保持版本同步。
* 不增加第二个 HTTP 网关/代理：5000 上的平台网关已经路由 `{port}-{sandbox}` 主机名。

## 5. CLI 侧变更（记录在 `cli-followups.md`）

Node 脚手架 `ebx template init`（FROM 官方基础镜像，按第 3 节生成脚手架）；部署路径（`DockerBuilder` 的等价实现：wheel 注入、`envd_inject` 自动选择、`start_cmd`/`ready_cmd`）；
`template.yaml` 的 `server:` 编译；AI 模板指南提示词（必须 FROM 官方基础镜像，不得覆盖 ENTRYPOINT，使用 `easy-sandbox-server serve`）。

## 6. 未决问题（无法从仓库/文档确定）

1. 网关是否遵守 Dockerfile 的 `CMD`，还是只认平台的 `start_command`？（我们避免使用 CMD。）
2. 普通 `base` 镜像是否保证 `/home/user` 与用户 `user`（文档针对 `claude-code`）？
3. 精确的默认标签：文档为 `v0.0.49`；我们提供 `EBX_BASE_IMAGE_TAG` 和一个常量，更新只需改一行。
4. 对于已经含有 envd 的非官方镜像，平台开启 `envdInject` 是否能容忍？

## 7. 评审后的变更（草案 v1 -> v2）

* "网关转发 `Authorization`"的说法未经证实（评审记录中的 OQ-3）：服务端同时接受 `X-Access-Token` 和 `Authorization: Bearer`，网关怎么处理都可行。
* `healthcheck` 只使用 `urllib.request` 访问 `127.0.0.1`（2 秒超时，退出码 0/1），因此可作为 Docker `HEALTHCHECK`/`ready_cmd`，无需重量级导入。
* `Image()` 默认基础镜像仍为 `ubuntu:22.04`；`Image.official_base()` 是可选的；非官方基础镜像仅记录警告。
* 已核实控制台脚本名 `easy-sandbox-server` 与 `ebx` 不冲突。

## 8. 实现状态

均按设计实现：`easy-sandbox-server` 控制台脚本（`serve`、`healthcheck`、`check-config`、`version`）、`easy_sandbox.server.contract`、`easy_sandbox.api.base_image`
（`official_base_image`、`is_official_base_image`、`lint_dockerfile` B001-B005、`warn_on_dockerfile`、`scaffold_dockerfile`、`BaseImageContract`）、`Image.official_base()`、
`Image.build()` 与 `DockerBuilder.build()` 中的建议性 lint、`Sandbox.server` / `server_at()` / `start_server()`。测试：`client-sdk/tests/test_api/test_base_image.py`、
`tests/test_api/server_e2e/test_sandbox_server_helpers.py`、`server-sdk/tests/test_server/test_cli_main.py`。CLI 侧的确切变更：[cli-followups.md](cli-followups.md)。
