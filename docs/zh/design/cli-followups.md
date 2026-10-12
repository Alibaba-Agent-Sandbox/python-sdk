# `ebx` CLI 跟进项：细粒度能力、基础镜像、服务端对齐

> 读者：Node/TypeScript 仓库（`/workspace/cli`）的 CLI 工作者。该仓库**没有**被这项工作修改；本文件就是确切的规格。
> 相关规格：[agents-api-cli-followups.md](agents-api-cli-followups.md)（Agents API）、
> [providers-and-credentials.md](providers-and-credentials.md)（凭据）。
> 相关设计：[fine-grained-capabilities.md](fine-grained-capabilities.md)、
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md)、
> [client-server-alignment.md](client-server-alignment.md)。
> 英文版为准：[../../en/design/cli-followups.md](../../en/design/cli-followups.md)。

下面的一切都是**增量的**：一个什么都没实现的 `ebx` 与新版 SDK 配合仍能正常工作（未配置的服务端、不变的模板）。

## 1. `ebx template init` 脚手架（`src/cli/scaffold.ts`）

当前的 Python/Node/minimal 脚手架以 `FROM python:3.11-slim` / `node:20-slim` 开头，安装 `easy-sandbox`（客户端发行包，现在依赖服务端发行包），
并运行 `CMD ["python3", "commands.py"]`。**所有**脚手架的新默认值：

1. `FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`。`<region>` 是解析出的地域（`src/cli/region.ts`，默认 `cn-hangzhou`）；`<tag>` 默认 `v0.0.49`，
   可用环境变量 `EBX_BASE_IMAGE_TAG` 覆盖（地域：`EBX_BASE_IMAGE_REGION`）。变体：`base`、`code-interpreter-v1`、`browser`、`claude-code`（参数 `--base-variant`）。
   各部分按 `^[a-z0-9-]+$`（地域）、`^[a-z0-9][a-z0-9._-]*$`（变体）、`^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$`（标签）校验，与
   `easy_sandbox.api.base_image.official_base_image` 规则相同。
2. 安装**服务端**发行包，并固定为 CLI 的同步版本：

   ```dockerfile
   ENV PIP_BREAK_SYSTEM_PACKAGES=1 PIP_NO_CACHE_DIR=1
   COPY *.whl /tmp/
   RUN command -v python3 >/dev/null || { echo 'python3 is required' >&2; exit 1; } \
    && if ls /tmp/easy_sandbox_server-*.whl >/dev/null 2>&1; then \
         pip install /tmp/easy_sandbox_server-*.whl; \
       else \
         pip install 'easy-sandbox-server==<VERSION>'; \
       fi \
    && rm -f /tmp/easy_sandbox_server-*.whl
   ```

   （对容器内运行时来说 `pip install easy-sandbox` 是错的；glob 要收窄，避免注入的 wheel 与其他 wheel 混淆。）
3. `WORKDIR /home/user/app`、`COPY commands.py /home/user/app/commands.py`、`EXPOSE 9000 9001`、`ENV EBX_SERVER_BASE_DIR=/home/user`。**不要**写 `ENTRYPOINT`（网关是 PID 1），也不要依赖 `CMD`。
4. 可选（`--policy <preset|file>`）：`COPY server-policy.json /etc/easy-sandbox/server-policy.json` 和
   `RUN easy-sandbox-server check-config --policy /etc/easy-sandbox/server-policy.json`（以 root 构建时**不要**加 `--strict`：lint L5 会使构建失败）。
5. Node 脚手架：Node 来自基础镜像；Python 服务端层保持一致。
6. `commands.py` 模板：用只含命令的模块取代 `start()` 样板（由 `easy-sandbox-server serve --commands /home/user/app/commands.py` 导入）；
   保持旧的 `start()` 写法（`python3 commands.py`）对现有模板可用。
7. `template.yaml` 脚手架：`base:` 改为官方引用；加入带注释的 `server:` 块（见第 3 节）以及 `start_command` / `ready_command`：

   ```yaml
   start_command: easy-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
   ready_command: easy-sandbox-server healthcheck --port 9000
   ```

CLI 不需要调用任何 Python：上面的字符串都是纯文本（Python 辅助函数 `scaffold_dockerfile()` 是参考实现；CLI 测试应把它在默认参数下的输出作为一次性的黄金文件进行比较）。

## 2. 部署（`src/cli/commands/template.ts`、`src/api/docker_builder.ts`、`src/api/fc_template.ts`）

* **wheel 注入**：注入**服务端** wheel（`easy_sandbox_server-<v>-py3-none-any.whl`）；`_downloadReleaseWheel` 必须向 PyPI 请求 `easy-sandbox-server`（不是 `easy-sandbox`），
  开发检出路径必须构建 `server-sdk/`。Dockerfile 中的文件名 glob：`easy_sandbox_server-*.whl`。
* **Dockerfile lint（建议性，永不致命）**，在构建前执行，移植自 `easy_sandbox.api.base_image.lint_dockerfile`：解析逻辑行；只看**最后一个阶段**；报告
  `B001` 基础镜像不是 `fc-e2b-registry.*.cr.aliyuncs.com/runtime/*`（且不是之前的阶段名）、`B002` 存在 `ENTRYPOINT`、`B003` 末尾 `USER root`/`0`、
  `B004` `EXPOSE` 了 5000、49983 或 49999、`B005` 没有 `FROM`。以 `warning:` 行打印；`--no-lint` 可关闭。
* **`envd_inject` 自动选择**（`use_official` 路径、`envd_inject` 选项）：最后一个阶段的基础镜像是官方镜像时保持 `envd_inject=false`（镜像已含 envd）；不是时保持今天的默认值，
  但打印 B001 警告并说明后果（"传入 `--envd-inject` 以便平台注入 envd"）。不要悄悄翻转默认值。
* **`start_command` / `ready_command`**：当 `template.yaml` 里有它们（或 CLI 脚手架生成了它们）时，作为 `start_command` / `ready_command` 传给官方创建模板调用（已接好为 `start_cmd` / `ready_cmd`，仅第 2 代）。
  Dockerfile 使用服务端脚手架而参数缺省时的默认值：`easy-sandbox-server serve --port 9000` 与 `easy-sandbox-server healthcheck --port 9000`（后者退出码 0/1，除 `127.0.0.1` 外不需要网络）。
* **策略编译**：`template.yaml` 含 `server:` 块时，把它以 JSON 写入 `<context>/server-policy.json`，并确保 Dockerfile 把它复制到 `/etc/easy-sandbox/server-policy.json`；
  校验失败时立即报错并给出校验器消息（第 3 节）。YAML 到 JSON 的转换在 CLI 中完成，因为容器内服务端仅依赖标准库。

## 3. `template.yaml` 的 `server:` 块（`src/utils/registry.ts`、`src/api/template.ts`）

声明式块与 JSON 策略是同一份文档（见 [fine-grained-capabilities.md](fine-grained-capabilities.md) 第 4 节）。从 `easy_sandbox.models.template` 移植 `validate_server_block`：
未知键为错误（`server.<path>: unknown key; allowed: [...]`）；顶层键 `version, preset, base_dir, groups, defaults, auth, endpoints, description`；预设
`default, transfer-only, read-only, hardened, locked`；规则键 `enabled, scopes, paths, limits, params, audit`；路径键 `allow, deny, read_only, symlinks`。
取值由服务端校验（`easy-sandbox-server check-config`），CLI 可以像第 1.4 节那样在构建中运行它；YAML 中绝不接受 `token` 字面量：令牌以 `token_env` 名称或 `token_sha256` 摘要提供。

## 4. 新增 CLI 命令（可选，轻量 HTTP 客户端）

都通过沙箱网关 URL（`9000-<id>.<domain>`）访问模板的 SandboxServer，携带 `X-Access-Token`（网关），服务端有自己的令牌时还带 `Authorization: Bearer`。

| 命令 | HTTP |
|------|------|
| `ebx sandbox server caps <id> [--endpoint NAME]` | `GET /capabilities`（v2：`endpoints`、`identity`、`revision`） |
| `ebx sandbox server check <id> <endpoint> [--path P --op read\|write\|delete]` | `POST /capabilities/check` |
| `ebx sandbox server start <id> [--commands F --preset P --policy FILE --token T]` | envd 后台命令 `easy-sandbox-server serve ...` + 轮询 `GET /health`（对应 `Sandbox.start_server`） |
| `ebx sandbox files watch <id> <path>` | `GET /files/watch`（SSE） |
| `ebx sandbox process output <id> <pid> [--since N --wait]` | `GET /process/{pid}/output` |
| `ebx sandbox process stdin <id> <pid> [-]` | `POST /process/{pid}/stdin` |

退出码遵循 [error-codes.md](../reference/error-codes.md) 中的 E9xxx 表（401 -> 3，其他服务端错误 -> 1）；CLI 从 JSON 响应体中打印 `code`、`endpoint`、`scope`，429 时打印 `retry_after`。

## 5. AI 模板指南（`src/agent/template_guide.ts`）与 codegen/adopt

指南目前教的是在任意基础镜像上使用 `commands.py` + `CMD ["python3", "commands.py"]`。更新提示词文本和 `REQUIRED_TEMPLATE_FILES` 的说明：

* 以沙箱所在地域的官方基础镜像开头 `FROM`（给出确切引用）；
* 绝不写 `ENTRYPOINT`；绝不依赖 `CMD`；平台运行 `easy-sandbox-server serve --port 9000 --commands /home/user/app/commands.py`；
* 按第 1.2 节安装 `easy-sandbox-server`；代码放在 `/home/user/app`；以 `user` 运行；
* 5000、49983、49999 是保留端口；9000 是 HTTP 服务端，9001 是 PTY WebSocket；
* 要限制模板暴露的内容，添加 `server:` 块（给出两个示例：带 `paths.allow: [/home/user/out]` 的 `transfer-only`，以及只读预设）；
* 生成之后，在校验步骤运行第 2 节的 lint 和 `check-config` 命令。

`adopt.ts`（接管现有 Dockerfile）：运行同样的 lint，如果基础镜像不是官方镜像，只**建议**改写，不要自动改写用户的 Dockerfile。

## 6. CLI 工作者应添加的测试

* python/node/minimal 脚手架与 `scaffold_dockerfile()` 输出的黄金文件对比。
* B001-B005 的 lint 表驱动测试，包括多阶段、`FROM --platform=...`、阶段名作为基础镜像、续行、注释。
* `server:` 块校验器与第 3 节所列词汇表的一致性测试。
* 部署：注入的 wheel 名称、默认情况下 `envd_inject` 不变、`start_cmd` / `ready_cmd` 仅对第 2 代传递。

## 7. 需要平台确认的未决点

1. 默认标签（当前官方页面为 `v0.0.49`）以及它变更的频率。
2. 网关是否遵守 Dockerfile 的 `CMD`，还是只认平台的 `start_command`（设计上避免使用 `CMD`）。
3. 网关是否把 `Authorization` 转发到端口（服务端同时接受 `Authorization: Bearer` 和 `X-Access-Token`，所以两种都行）。
4. `user` / `/home/user` 是否对每个官方变体都有保证（文档针对 `claude-code`）。
5. 在已经含有 envd 的镜像上开启 `envdInject` 是否无害。
