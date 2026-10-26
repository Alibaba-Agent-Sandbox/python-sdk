# 真实云端 E2E 套件(Python SDK)

针对**真实阿里云 FC 智能体沙箱平台**对 `agent-sandbox`(client-sdk)与 `agent-sandbox-server`(server-sdk)做端到端测试:
真实沙箱、真实 envd、真实沙箱内 server。模板的构建与部署由 `abx template build|deploy` 负责，由 CLI 自己的 E2E 套件覆盖。mock 测试位于 `client-sdk/tests` 与 `server-sdk/tests`;本套件的存在
是因为 mock 无法证明产品可用(见 [`../.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md) 中的完成定义)。

> English version: [README.md](README.md)。本套件固定的产品缺陷见 [KNOWN-ISSUES.zh-CN.md](KNOWN-ISSUES.zh-CN.md)。

## 标准 E2B 迁移验证

在仓库根目录执行 `python -m pytest e2e/test_standard_contract.py -ra`，验证标准
Sandbox/AsyncSandbox 和 code_interpreter 入口。它使用真实云端覆盖生命周期、文件、
后台进程 stdin、解释器上下文及回调、惰性分页和网络禁止/恢复。其他原生测试继续
覆盖 ProviderSandbox；不能把 mock 结果当作云端证据。

快照恢复额外需要 `E2E_SNAPSHOT_TEMPLATE`，指定已开通快照白名单账号下的 MicroVM
模板；未配置时明确跳过。测试会删除快照并登记恢复的沙箱以便清理。暂停/恢复也需要
受支持的运行时/账号条件，保留方法本身并不代表已经验证。服务限制见中英文迁移指南。

## Provider 分级

第三方 provider 不在本套件的云端运行里。它们和 CLI 使用同一套六级：从插件单测（T0）到本机 OpenSandbox（T4），再到阿里云平台（T5）。表格见 [cli/e2e/providers/PLAN.zh-CN.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/e2e/providers/PLAN.zh-CN.md)。T4 的辅助脚本在 [opensandbox/README.md](opensandbox/README.md)。

## 运行

```bash
pip install -e ./server-sdk -e ./client-sdk pytest        # 或: make dev
cp .env.example .env                                       # 然后填入真实值(已被 git 忽略)

make e2e          # 仅沙箱用例(快速路径,约 8 分钟)
make e2e-all      # 另含慢速用例
make e2e-cleanup  # janitor 干运行;加 ARGS=--yes 才会删除遗留资源

cd e2e && python -m pytest test_03_commands.py -k "timeout"   # 运行子集
cd e2e && python -m pytest -m "not e2e_slow" -ra               # 等同 `make e2e`,并输出汇总
```

必需:`ABX_SANDBOX_API_KEY`(非默认地域另需 `ABX_SANDBOX_BASE_URL`/`ABX_SANDBOX_DOMAIN`)。
取值来自环境变量或被 git 忽略的 `.env` 文件(`e2e/.env`、`.env`、`client-sdk/.env`),环境变量优先。

缺少凭据时所有测试都会**跳过**,并给出 `E2E skipped: missing credentials [...]`。单元 CI 不会收集本套件
(`client-sdk` / `server-sdk` 在各自目录运行 `pytest tests/`)。

## 覆盖范围

| 文件 | 范围 |
|---|---|
| `test_01_platform.py` | 鉴权(有效/无效 key)、沙箱列表、错误映射 |
| `test_02_lifecycle.py` | create / connect / info / list / kill、超时(`e2e_slow`:TTL 到期)、metadata 打标 |
| `test_03_commands.py` | `commands.run` / `run_code`、退出码、stdout/stderr、cwd、后台进程、进程列表/信号 |
| `test_04_files_envd.py` | 通过 envd 的文件操作:文本/二进制读写、list/stat、mkdir/move/remove、大小边界 |
| `test_05_network_and_code.py` | 端口 URL 与沙箱内 HTTP 服务、代码执行 |
| `test_06_server_sdk.py` | 真实沙箱(模板 `python-hello`)内的 `agent-sandbox-server`:`/commands`、`/files/*`、`/process/*`、`/capabilities`、`/system/info`、`/env`、`/ports`、自定义路由 |
| `test_07_declarative.py` | `@sandbox` 声明式远程执行 |
| `test_08_providers.py` | 真实后端调用：内置 `alicloud-express`（SDK 和 CLI），以及已安装的目录提供方 `opensandbox`、`cubesandbox`、`e2b`、`alicloud-container`。没有自己的后端时跳过，并且不会把极速版密钥发给它。 |
| `test_09_volume_mounts.py` | 显式启用的已有 Volume 验收：确认内核精确挂载点，独占创建、读取并删除一个测试文件，再释放带标签的沙箱。普通目录不能通过。 |
| `test_skill_storage_state.py` | 显式自有 RW/RO OSS 夹具：标准客户端释放并重建后的持久化、内核精确挂载点、只读约束及类型化清理。 |
| `test_09_mcp_lifecycle.py` | Python MCP 元数据/续期/列表、命令文件与外部实例归属 |

标记:`e2e`(全部)、`e2e_slow`(> 约 60 秒)、`known_issue`(记录已知缺陷的严格 xfail,见
[KNOWN-ISSUES.zh-CN.md](KNOWN-ISSUES.zh-CN.md))。

## 保证

- **打标与清理。** 所有沙箱都通过 fixture 创建,并带 metadata `e2e=<run id>` 且登记待删除。MCP 创建工具未开放 metadata，相关 E2E 直接登记返回的自有 ID，
  并在 `finally` 退出所属 manager。会话
  收尾时先删除所有已登记资源,再按标签扫描清理,即使测试失败或运行被中断也如此。`scripts/e2e-cleanup.py` 用于被强杀的
  运行(默认干运行;`--yes` 才删除;支持 `--run-id`、`--all-tagged`、`--older-than N`),
  绝不触碰无标签的沙箱。
- **绝不打印密钥。** 失败报告经过脱敏钩子,替换每个凭据值(及其派生形式);辅助函数不记录请求头。不要对环境变量值使用 `print`。
- **确定性。** 测试相互独立(各自的沙箱,或每次运行工作目录下各自的目录),超时宽松,仅对已知最终一致的操作(envd 就绪、
  沙箱列表、server 启动)用 `eventually` 轮询。

## 环境变量

服务fixture遵循 `Sandbox.server_at`：模板服务未配置令牌，不向它发送无关的envd
`X-Access-Token`。CLI provider场景使用 `ABX_BIN`（可包含参数）或PATH中的abx，
不依赖相邻源码目录。缺失预期报告项会使场景失败，包括未找到CLI的情况。

完整套件的凭据拒绝检查需要先在隔离测试HOME中安装对应catalog provider；安装须保留
同意和doctor验证。缺少插件不能证明该插件的凭据隔离边界。
宿主前置 `InvalidCredentialsError` 和provider内部 `InvalidAPIKeyError` 都是有效的凭据
拒绝。Cube实云验收须明确配置 `ABX_CUBESANDBOX_BASE_URL`，不能用其他本地服务的
端口监听推断CubeAPI已就绪。

| 变量 | 默认值 | 含义 |
|---|---|---|
| `E2E_SANDBOX_TTL` | 300 | 沙箱存活秒数 |
| `E2E_SERVER_TEMPLATE` | `python-hello` | 预装 `agent-sandbox-server` 的模板 |
| `E2E_RUN_ID` | 自动生成 | 标签值(`e2e=<id>`) |
| `ABX_E2E_VOLUME_MOUNT` | 未设置则跳过 | 设置为 `1` 才允许运行 Volume 验收。 |
| `ABX_E2E_VOLUME_NAME` | 未设置则跳过 | API Key 同 Team、同地域、已配置存储角色的可写 Volume 名称；不创建或删除 Volume。 |
| `ABX_E2E_VOLUME_MOUNT_PATH` | 未设置则跳过 | `/mnt/abx-e2e/` 下专用的规范沙箱路径；这是测试工具的收窄要求。 |
| `E2E_VOLUME_TEMPLATE` | 未设置则跳过 | 满足[官方挂载指南](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1)存储及运行时前提的模板。 |

## 自有 OSS 持久化与只读验收

`test_skill_storage_state.py` 使用标准同步客户端，验证两个显式自有的 OSS Volume
配置：两者指向同一专用存储路径，一个可读写，一个只读。请在当前 API Key 的
Team 和地域预先创建这些配置，并将 RAM 角色权限限制为该自有存储。此测试不会
创建或删除 Volume、角色或 Bucket。

设置 `E2E_VOLUME_ACCEPTANCE=owned-only`；`E2E_VOLUME_OWNER_RUN` 为本次自有运行名
（`abx-accept-` 后接 12 位小写字母或数字）；`E2E_VOLUME_RW_NAME` 和
`E2E_VOLUME_RO_NAME` 分别等于运行名加 `-rw` 和 `-ro`。必须显式设置满足挂载前提的
`E2E_VOLUME_TEMPLATE`。MicroVM 镜像须预装 ossfs2 2.0.10 或更高版本，详见
[官方挂载前提](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1)。

运行 `python -m pytest e2e/test_skill_storage_state.py -ra`。测试先验证内核精确挂载点，
再独占创建唯一测试文件、fsync，释放首个沙箱并断言类型化 not-found，随后新建沙箱
读取保留的数据。只读挂载须能读取该文件，且另一独占写入须返回只读或权限错误号。
仅清理已验证归属的测试文件和已登记沙箱；夹具所有者另行清理 Volume、角色及底层存储。
未显式启用时，在构造云端夹具前跳过；启用后前提缺失则失败，不自动挑选其他 Volume。

标准快照回归把可修改标记放在自有、非 sticky 的目录中。被测 envd 镜像在创建快照前，
就会拒绝 SDK 直接覆盖 sticky `/tmp` 下的文件；该独立行为保留在
[状态及存储验证记录](../.agents/evidence/verify/2026-10-26-skill-storage-state-acceptance.md)。

## 代码仓库、到期预览及第三方 MCP 运行器

在已安装本 checkout 配套客户端/服务端的环境执行
`python e2e/skill_tools_acceptance.py --output NEW_JSON_PATH`。沙箱凭据只配置于本地，
不向沙箱发送账号密钥。运行时须具备 Python、Node.js、git 以及 GitHub/npm 出网能力。
`ABX_SKILL_RUNTIME_TEMPLATE` 指定合适模板（默认 `code-interpreter-v1`），
`ABX_SKILL_RUN_PREFIX` 指定自有夹具 purpose 标签。证据输出文件必须尚不存在。

运行器最多用两次有界、只读的获取操作拉取指定公开提交，验证并启动 Node 应用，
随后检查应用 HMAC 预览：有效请求成功、未签名及篡改请求被拒绝、20 秒后到期。
该临时夹具使用 `secure=False` 和应用代理，不代表提供方网关原生签名链接通过。
随后依次安装固定的文件系统 MCP `2026.7.10`、`2026.8.31`，执行真实 initialize、
工具发现和 read_file，回读日志，删除工具并核实无自有 MCP 进程及沙箱残留。
这是手动实云运行器，不会自动启用单测或 Actions；失败和清理结果与成功检查分开记录。

## 新增测试

1. 使用 fixture(`base_sandbox`、`code_sandbox`、`server_sandbox`、`sandbox_factory`、`workdir`);不要直接调用 `Sandbox.create`,否则沙箱不会被追踪。
2. 断言**预期**行为。若因产品缺陷失败,标记 `@pytest.mark.known_issue` + `@pytest.mark.xfail(strict=True, reason="KI-0NN: ...")`,
   并在 [KNOWN-ISSUES.md](KNOWN-ISSUES.md)(中英文)中新增条目。
3. 在 `.agents/evidence/verify/<date>-<topic>.md` 记录运行结果(完成定义)。

### Python MCP 生命周期验证

`test_09_mcp_lifecycle.py` 验证真实 Python MCP 创建、白名单元数据、列表可见性、
续期、命令与文件，以及外部查询会话退出时不误删资源。仅列表按既有最终一致
40 秒窗口重试，不据此推断 IDE 或新镜像部署通过。

## 共享 Provider 条件能力验收（仅本地）

准备含六个注册命令的 CLI 构建，以及已开通暂停/快照的二代模板。凭据只保留本地：

```sh
python e2e/provider_conditional.py --abx "$ABX_BIN" \
  --template "$E2E_SNAPSHOT_TEMPLATE" --env-file .env --report provider-conditional-report.json
```

控制器启动隔离的真实引擎，比较两端发现结果，双向验证暂停恢复、快照创建/列表/恢复/删除、内存文件连续性、克隆隔离和独立清理。不会创建或删除传入的模板。二进制应放在不会被另一轮构建清理的独立位置。报告不包含凭据及资源标识；该手动控制器不会被 pytest 收集，也不从 Actions 调度。

## 可选的真实桌面验收

按照[桌面验收指南](../docs/zh/guide/desktop-acceptance.md)准备隔离环境和固定依赖，运行
`python e2e/desktop_acceptance.py --template "$E2B_DESKTOP_TEMPLATE" --output-dir NEWDIR`。
它独立于标准及 Provider 客户端套件；真实桌面模板、私有入口、流量令牌、VNC 密码与
接管/回放前提均由指南明确列出。
