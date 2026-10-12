# 真实云端 E2E 套件(Python SDK)

针对**真实阿里云 FC 智能体沙箱平台**对 `easy-sandbox`(client-sdk)与 `easy-sandbox-server`(server-sdk)做端到端测试:
真实沙箱、真实 envd、真实沙箱内 server、真实模板构建。mock 测试位于 `client-sdk/tests` 与 `server-sdk/tests`;本套件的存在
是因为 mock 无法证明产品可用(见 [`../.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md) 中的完成定义)。

> English version: [README.md](README.md)。本套件固定的产品缺陷见 [KNOWN-ISSUES.zh-CN.md](KNOWN-ISSUES.zh-CN.md)。

## 运行

```bash
pip install -e ./server-sdk -e ./client-sdk pytest        # 或: make dev
cp .env.example .env                                       # 然后填入真实值(已被 git 忽略)

make e2e          # 仅沙箱用例(快速路径,约 8 分钟)
make e2e-all      # 另含慢速用例与 Docker/ACR 自定义模板流程
make e2e-cleanup  # janitor 干运行;加 ARGS=--yes 才会删除遗留资源

cd e2e && python -m pytest test_03_commands.py -k "timeout"   # 运行子集
cd e2e && python -m pytest -m "not e2e_slow" -ra               # 等同 `make e2e`,并输出汇总
```

必需:`E2B_API_KEY`(非默认地域另需 `E2B_API_URL`/`E2B_DOMAIN`)。Docker 流程还需要 `AccessKey`、`AccessSecret`、
`ACR_NAMESPACE` 与可用的 Docker 守护进程。`OPENAI_API_KEY` / `OPENAI_BASE_URL` 仅用于 AI 代码生成功能,本套件不涉及。
取值来自环境变量或被 git 忽略的 `.env` 文件(`e2e/.env`、`.env`、`client-sdk/.env`),环境变量优先。

缺少凭据时所有测试都会**跳过**,并给出 `E2E skipped: missing credentials [...]`。单元 CI 不会收集本套件
(`client-sdk` / `server-sdk` 在各自目录运行 `pytest tests/`)。

## 覆盖范围

| 文件 | 范围 |
|---|---|
| `test_01_platform.py` | 鉴权(有效/无效 key)、模板目录、沙箱列表、错误映射 |
| `test_02_lifecycle.py` | create / connect / info / list / kill、超时(`e2e_slow`:TTL 到期)、metadata 打标 |
| `test_03_commands.py` | `run` / `run_code` / `custom`、退出码、stdout/stderr、cwd、后台进程、进程列表/信号 |
| `test_04_files_envd.py` | 通过 envd 的文件操作:文本/二进制读写、list/stat、mkdir/move/remove、大小边界 |
| `test_05_network_and_code.py` | 端口 URL 与沙箱内 HTTP 服务、代码执行 |
| `test_06_server_sdk.py` | 真实沙箱(模板 `python-hello`)内的 `easy-sandbox-server`:`/commands`、`/files/*`、`/process/*`、`/capabilities`、`/system/info`、`/env`、`/ports`、自定义路由 |
| `test_07_declarative.py` | `@sandbox` 声明式远程执行 |
| `test_08_custom_template_docker.py` | `DockerBuilder` → 推送 ACR → 官方 `CreateTemplate` → 沙箱 → server-sdk 端点(`e2e_docker`,Docker/ACR 不可用时自动跳过) |

标记:`e2e`(全部)、`e2e_slow`(> 约 60 秒)、`e2e_docker`(需 Docker + ACR)、`known_issue`(记录已知缺陷的严格 xfail,见
[KNOWN-ISSUES.zh-CN.md](KNOWN-ISSUES.zh-CN.md))。

## 保证

- **打标与清理。** 所有沙箱和模板都通过 fixture 创建,并带 metadata `e2e=<run id>`(模板使用前缀 `e2e-`)且登记待删除。会话
  收尾时先删除所有已登记资源,再按标签扫描清理,即使测试失败或运行被中断也如此。`scripts/e2e-cleanup.py` 用于被强杀的
  运行(默认干运行;`--yes` 才删除;支持 `--run-id`、`--all-tagged`、`--older-than N`、`--templates`、`--acr`),
  绝不触碰无标签/前缀的资源。
- **绝不打印密钥。** 失败报告经过脱敏钩子,替换每个凭据值(及其派生形式);辅助函数不记录请求头。不要对环境变量值使用 `print`。
- **确定性。** 测试相互独立(各自的沙箱,或每次运行工作目录下各自的目录),超时宽松,仅对已知最终一致的操作(envd 就绪、
  沙箱列表、server 启动)用 `eventually` 轮询。
- **Docker 流程保护。** `docker_ctx` 首先向 ACR 推送 2 MB 随机层 canary(`E2E_CANARY_PUSH_TIMEOUT`,默认 120 秒);无法完成则
  带确切原因跳过该模块,而不是挂起数小时(KI-011)。无 buildx 的 Docker 通过 `DOCKER_BUILDKIT=0` 与隔离的 `DOCKER_CONFIG` 处理。

## 环境变量

| 变量 | 默认值 | 含义 |
|---|---|---|
| `E2E_SANDBOX_TTL` | 300 | 沙箱存活秒数 |
| `E2E_SERVER_TEMPLATE` | `python-hello` | 预装 `easy-sandbox-server` 的模板 |
| `E2E_RUN_ID` | 自动生成 | 标签值(`e2e=<id>`) |
| `E2E_CANARY_PUSH_TIMEOUT` / `E2E_CANARY_BYTES` | 120 / 2000000 | ACR canary 推送限制 |

## 新增测试

1. 使用 fixture(`base_sandbox`、`code_sandbox`、`server_sandbox`、`sandbox_factory`、`workdir`);不要直接调用 `Sandbox.create`,否则沙箱不会被追踪。
2. 断言**预期**行为。若因产品缺陷失败,标记 `@pytest.mark.known_issue` + `@pytest.mark.xfail(strict=True, reason="KI-0NN: ...")`,
   并在 [KNOWN-ISSUES.md](KNOWN-ISSUES.md)(中英文)中新增条目。
3. 在 `.agents/evidence/verify/<date>-<topic>.md` 记录运行结果(完成定义)。
