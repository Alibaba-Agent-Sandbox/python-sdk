# 测试与完成定义

Python SDK(`agent-sandbox-client`)与沙箱内服务(`agent-sandbox-server`)如何做端到端验证,以及判定一项变更"算完成"的规则。

> English version: [../../en/guide/testing-e2e.md](../../en/guide/testing-e2e.md)

## 验证层次

| 层 | 工具 | 真实组件? | 凭据 | 典型耗时 |
|---|---|---|---|---|
| 单元/组件测试 | `make test`（两个包的 pytest） | 逻辑 mock 与真实本地 HTTP/PTY 夹具 | 无 | 几秒至几分钟 |
| 真实云 E2E | `make e2e` | **是**:真实平台、envd、沙箱内服务 | `.env` 或环境变量 | 约 8 分钟 |
| 含慢速用例的 E2E | `make e2e-all` | **是** | 相同 | 更久 |

只有真实云这一层才能关闭完成定义中的"E2E"一项。

## 运行 E2E 套件

```bash
cp .env.example .env     # 填入真实值;.env 已被 git 忽略
make e2e                 # 快速路径
make e2e-all             # 另含慢速测试
make e2e-cleanup         # 清理遗留资源的 dry-run janitor;ARGS=--yes 才真正删除
```

没有凭据时,每个测试都会带明确原因被跳过,单元 CI 也不会收集该套件。套件创建的每个沙箱都带标签并在 finalizer 中删除;被强杀的运行由 `scripts/e2e-cleanup.py` 兜底。细节、标记与保证见 [`e2e/README.zh-CN.md`](../../../e2e/README.zh-CN.md)。套件发现的产品缺陷以 strict xfail 记录,并列于 [`e2e/KNOWN-ISSUES.zh-CN.md`](../../../e2e/KNOWN-ISSUES.zh-CN.md)。

## 完成定义

满足以下全部条件才算完成:

1. 单元测试、lint 与 `scripts/check-repo-health.sh` 通过。
2. 功能已对真实组件验证(`make e2e` 或针对性 E2E 用例),而不只是 mock。
3. 中英文文档完整,且有 CHANGELOG 条目。
4. 大型变更已按正确状态记录为 `.agents/notes/` 下的 ADR。
5. 证据(命令、结果、资源清理)保存在 `.agents/evidence/verify/<日期>-<主题>.md`,不含任何密钥。
6. 没有遗留沙箱。

完整规则以及 ADR 与证据模板见 [`.agents/notes/DEFINITION-OF-DONE.md`](../../../.agents/notes/DEFINITION-OF-DONE.md)。

## 云上示例练习

测试套件之外，按脚本在默认提供方上走一遍的说明见 [云上端到端练习](cloud-examples.md)。Agents API 的完整案例不在那一页，见 [Agents API](agents-api.md)。

## 本地 HTTP 与 PTY 夹具端口

客户端组件夹具启动监听前会选择不同的 HTTP 与 PTY 端口候选。刚释放的临时端口可能被再次分配，候选重选有次数上限，并保留显式指定的 PTY 端口。这种本地分配重选不重放请求，也不替代真实云验收。确定性复用回归启动真实服务、检查两个监听器，再由正常夹具清理将它们停止。


## 本地原始 HTTP 测试

原始请求使用实际监听地址。测试夹具在原有期限内等待 HTTP 服务初始化，并读取完整的
分帧响应。中间层可能在请求到达服务前拒绝故意构造的畸形 HTTP／WebSocket 流量；
这类失败必须保留，并由托管 CI 执行原有断言。不得用跳过、扩大超时或改变代理策略
代替协议覆盖。

## 公开发布回读

配套双包上传后，发布流程会将本地四个发行文件的文件名及 SHA-256 与 PyPI
逐一比较。元数据暂时不可见（HTTP 404）时最多尝试六次，间隔十秒；哈希不一致
会立即失败。通过官方 PyPI 索引进行的全新安装也采用同样的有限重试，因为索引
可能晚于包元数据同步。每次安装失败均保留在日志中。安装成功后只执行一次依赖
及公开导入检查，这些检查失败会直接阻止发布。

## SDK 夹具镜像

SDK 仓库保留独立于模板目录的 python-hello 和 agents-cli 离线夹具。两个
Dockerfile 均从官方 PyPI 安装公开 server 0.4.0a4，不需要本地 wheel。CI 构建
两个镜像，检查实际客体包与 HTTP 应用，并确认自有容器清理。Agents 运行时
列表不代表已安装 Agent 或完成真实模型调用。
