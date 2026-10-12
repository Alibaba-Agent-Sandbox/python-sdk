# 测试与完成定义

Python SDK(`easy-sandbox`)与沙箱内服务(`easy-sandbox-server`)如何做端到端验证,以及判定一项变更"算完成"的规则。

> English version: [../../en/guide/testing-e2e.md](../../en/guide/testing-e2e.md)

## 验证层次

| 层 | 工具 | 真实组件? | 凭据 | 典型耗时 |
|---|---|---|---|---|
| 单元测试 | `make test`(`client-sdk/tests`、`server-sdk/tests` 下的 pytest) | 否(mock) | 无 | 几秒 |
| 真实云 E2E | `make e2e` | **是**:真实平台、envd、沙箱内服务 | `.env` 或环境变量 | 约 8 分钟 |
| 含慢速与 Docker/ACR 流程的 E2E | `make e2e-all` | **是** | 另需 `AccessKey`、`AccessSecret`、`ACR_NAMESPACE` 与 Docker | 更久 |

只有真实云这一层才能关闭完成定义中的"E2E"一项。

## 运行 E2E 套件

```bash
cp .env.example .env     # 填入真实值;.env 已被 git 忽略
make e2e                 # 快速路径
make e2e-all             # 另含慢速测试与自定义模板 Docker 流程
make e2e-cleanup         # 清理遗留资源的 dry-run janitor;ARGS=--yes 才真正删除
```

没有凭据时,每个测试都会带明确原因被跳过,单元 CI 也不会收集该套件。套件创建的每个沙箱和模板都带标签并在 finalizer 中删除;被强杀的运行由 `scripts/e2e-cleanup.py` 兜底。细节、标记与保证见 [`e2e/README.zh-CN.md`](../../../e2e/README.zh-CN.md)。套件发现的产品缺陷以 strict xfail 记录,并列于 [`e2e/KNOWN-ISSUES.zh-CN.md`](../../../e2e/KNOWN-ISSUES.zh-CN.md)。

## 完成定义

满足以下全部条件才算完成:

1. 单元测试、lint 与 `scripts/check-repo-health.sh` 通过。
2. 功能已对真实组件验证(`make e2e` 或针对性 E2E 用例),而不只是 mock。
3. 中英文文档完整,且有 CHANGELOG 条目。
4. 大型变更已按正确状态记录为 `.agents/notes/` 下的 ADR。
5. 证据(命令、结果、资源清理)保存在 `.agents/evidence/verify/<日期>-<主题>.md`,不含任何密钥。
6. 没有遗留沙箱或模板。

完整规则以及 ADR 与证据模板见 [`.agents/notes/DEFINITION-OF-DONE.md`](../../../.agents/notes/DEFINITION-OF-DONE.md)。
