# Definition of Done

This is the binding product-owner rule for this repository. It is not an ADR (it has no Status); it
is the checklist every ADR, PR and feature is measured against. English first, 中文 below.

- Related: [`README.md`](README.md) (ADR format and lifecycle), [`../README.md`](../README.md),
  [`../../.github/CONTRIBUTING.md`](../../.github/CONTRIBUTING.md),
  [`../../.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md),
  [`../../e2e/README.md`](../../e2e/README.md), [`../../e2e/KNOWN-ISSUES.md`](../../e2e/KNOWN-ISSUES.md).

---

## English

### The rule

> **A feature, command or fix is done only when it has been verified end to end against real
> components, and the work is recorded under `.agents/` with complete documentation (English and
> Chinese) and a CHANGELOG entry.** Mocks prove logic; only real components prove the product.

A change is **not done** if any of the six items below is missing. "Almost done" and "works with
mocks" are not states a task may be reported in; report it as *in progress* or *blocked* (see
[Blocked E2E](#blocked-e2e)) instead.

### The six items

| # | Requirement | Where / how to prove it |
|---|---|---|
| 1 | **Unit tests** cover the change and pass | `make test` (client-sdk and server-sdk); `make ci` is the local CI equivalent |
| 2 | **E2E executed against real components** (real cloud, real binary, real filesystem), with the result recorded | `make e2e` (pytest suite in [`e2e/`](../../e2e/README.md), marker `e2e`; `make e2e-all` adds the slow and Docker/ACR cases). Add or extend a test when the change introduces new behaviour; flip or remove a `known_issue` xfail when you fix the bug it documents. Record the run in item 3 |
| 3 | **Verification evidence file**, no secrets | `.agents/evidence/verify/YYYY-MM-DD-<topic>.md` using the [template below](#evidence-file-template) |
| 4 | **ADR / note** in the correct state directory | `.agents/notes/{proposed,implemented}/<architecture\|feature\|process>/YYYY-MM-DD-<slug>.md` using the [ADR template](#adr-template); `Status:` must equal the directory; move it when the work lands |
| 5 | **Docs updated, English and Chinese** | `docs/en/...` and `docs/zh/...` (plus `README.md` / `README.zh-CN.md` and package READMEs if user-visible); both languages in the same PR |
| 6 | **CHANGELOG entry** | `CHANGELOG.md` under `[Unreleased]` (Keep a Changelog groups: Added / Changed / Fixed / Removed) |

And the gates that must stay green: `bash scripts/check-repo-health.sh` (documents, links, ADR names, machine-local paths), `make hygiene`, `make ci`.

### Rules for E2E

1. **Real components, not only mocks.** A passing mocked/unit test never closes item 2. Tests that
   patch `httpx`, the transport or the protocol layer belong to item 1; the pytest suite in `e2e/`
   against the real cloud is item 2.
2. **Credentials** live in gitignored `.env` files (`.env`, `client-sdk/.env`, `server-sdk/.env`; never committed) or in environment
   variables. **Never print, log, commit or write them anywhere**: not into reports, evidence
   files, snapshots, transcripts or test output. The suites mask them; if you add output capture,
   mask it too. Before committing run `git check-ignore .env client-sdk/.env server-sdk/.env` and `git status` and make sure no
   secret is staged.
3. **Clean up.** Every sandbox/template a test creates must be destroyed, also on failure; verify with
   `python scripts/e2e-cleanup.py --all-tagged` (dry run) afterwards and state "none leaked" in the evidence file.
4. **Deterministic and independent.** No test may depend on another test's leftovers; retries only for
   operations that are known to be eventually consistent, and say so in the scenario.
5. **Honest results.** Record failures and skips with their exact reason. A skipped scenario is not a
   pass.

### Blocked E2E

If the E2E cannot be run (missing credentials, platform outage, Docker/ACR unusable), the change is
**not done**. Write the evidence file anyway with `Result: BLOCKED`, the exact reason, what was
verified instead (unit tests) and what remains; keep the ADR in `proposed/`
(or `implemented/` with an `## Implementation` note stating the gap) and open a follow-up. Never
claim real-cloud verification that did not happen.

### Evidence file template

Copy to `.agents/evidence/verify/YYYY-MM-DD-<topic>.md` (kebab-case topic). Evidence is historical:
once merged, add a new dated file instead of editing it.

```markdown
# Verification: <topic>

- Date: YYYY-MM-DD
- Change: <PR / ADR slug / commit>
- Result: PASS | PARTIAL | BLOCKED | FAIL
- Package under test: <easy-sandbox / easy-sandbox-server version, how it was installed>
- Environment: <real cloud region, Node/Python versions, OS>. Credentials: supplied via env/.env (values not recorded)

## What was verified
<One paragraph: the behaviour that the change introduces or fixes>

## Commands run
<Exact commands (e.g. `make e2e`), with credentials omitted or masked>

## Results
| Scenario / test | Result | Notes (flakiness, retries, timing) |
|---|---|---|

## Cleanup
<How leaks were checked, e.g. the janitor dry run after the run: none left>

## Problems found
<Defects, platform quirks, links to follow-ups; "none" if none>

## Not verified
<What could not be run and why>
```

### ADR template

The format is defined by [`README.md`](README.md): file name `YYYY-MM-DD-<slug>.md`, title
`# Decision: <Title>` on the first line, `Status:` immediately after, and these sections in order.

```markdown
# Decision: <Title>

Status: proposed

## Problem
<Motivation, independent of the solution>

## Decision
<Technical approach, interfaces, file paths>

## API Design
<Signatures and input/output types, or "N/A — this decision does not involve API changes.">

## Alternatives considered
- **<Option A>** — <why rejected>

## Dependencies
<Modules/packages required>

## Test Strategy
<Unit tests and the E2E tests (real components) that cover the change>

## Acceptance criteria
<Measurable conditions, including the E2E scenarios that must pass>

## Evidence
- [`verify/YYYY-MM-DD-<topic>.md`](../../../evidence/verify/YYYY-MM-DD-<topic>.md)
```

### Checklist to paste into the PR

- [ ] Unit tests added/updated and passing
- [ ] E2E executed against real components (`make e2e`); result in `.agents/evidence/verify/<date>-<topic>.md` (no secrets, no leaked resources)
- [ ] ADR/note under `.agents/notes/{proposed,implemented}/<category>/<date>-<slug>.md`, `Status:` matches the directory
- [ ] Docs updated in English and Chinese
- [ ] CHANGELOG entry under `[Unreleased]`
- [ ] `bash scripts/check-repo-health.sh` passes

---

## 中文

### 规则

> **一个功能、命令或修复,只有在针对真实组件完成端到端验证,并且工作已记录在 `.agents/` 下、文档完整(中英文)、
> 附有 CHANGELOG 条目之后,才算完成。** mock 证明逻辑;只有真实组件才能证明产品。

下列六项缺任何一项,变更就**没有完成**。任务不得以"差不多完成"或"mock 下可用"的状态汇报,应报告为"进行中"或
"受阻"(见[E2E 受阻](#e2e-受阻))。

### 六项要求

| # | 要求 | 位置 / 证明方式 |
|---|---|---|
| 1 | **单元测试**覆盖变更且通过 | `make test`(client-sdk 与 server-sdk);`make ci` 为本地 CI 等价命令 |
| 2 | **针对真实组件执行 E2E**(真实云端、真实二进制、真实文件系统)并记录结果 | `make e2e`(`e2e/` 下的 pytest 套件,标记 `e2e`,见 [`e2e/`](../../e2e/README.md);`make e2e-all` 另含慢速与 Docker/ACR 用例)。引入新行为时新增或扩展测试;修复某个 `known_issue` xfail 所记录的缺陷时,同步翻转或删除该 xfail。运行结果记录到第 3 项 |
| 3 | **验证证据文件**,不含任何密钥 | `.agents/evidence/verify/YYYY-MM-DD-<topic>.md`,使用[下方模板](#证据文件模板) |
| 4 | **ADR / 笔记**位于正确状态目录 | `.agents/notes/{proposed,implemented}/<architecture\|feature\|process>/YYYY-MM-DD-<slug>.md`,使用 [ADR 模板](#adr-模板);`Status:` 必须与目录一致,工作落地时移动文件 |
| 5 | **中英文文档同步更新** | `docs/en/...` 与 `docs/zh/...`(用户可见变化还需 `README.md` / `README.zh-CN.md`);同一 PR 内完成两种语言 |
| 6 | **CHANGELOG 条目** | `CHANGELOG.md` 的 `[Unreleased]` 下(Keep a Changelog 分组:Added / Changed / Fixed / Removed) |

另需保持绿色的门禁:`bash scripts/check-repo-health.sh`(文档、链接、ADR 命名、本机路径)、`make hygiene`、`make ci`。

### E2E 规则

1. **真实组件,而非仅有 mock。** 单元/mock 测试通过永远不能关闭第 2 项。patch 了 `httpx`、传输层或协议层的测试属于第 1 项;针对真实云端的 `e2e/` pytest 套件才属于第 2 项。
2. **凭据**只存放在被 git 忽略的 `.env`(`.env`、`client-sdk/.env`、`server-sdk/.env`,绝不提交)或环境变量中。**绝不在任何地方打印、记录、提交或写入它们**:
   不写入报告、证据文件、快照、会话记录或测试输出。套件已做脱敏;若新增输出捕获,同样必须脱敏。提交前运行
   `git check-ignore .env client-sdk/.env server-sdk/.env` 与 `git status`,确认没有密钥被暂存。
3. **清理。** 测试创建的每个沙箱/模板即使在失败时也必须销毁;事后用 `python scripts/e2e-cleanup.py --all-tagged`(dry-run)核对,并在证据文件中写明"无泄漏"。
4. **确定且相互独立。** 测试不得依赖其他测试遗留的状态;仅对已知最终一致的操作重试,并在场景中说明。
5. **如实记录。** 失败与跳过必须附确切原因;跳过不等于通过。

### E2E 受阻

若无法运行 E2E(缺少凭据、平台故障、Docker/ACR 不可用),该变更**未完成**。仍须写证据文件,标注 `Result: BLOCKED`、确切原因、
已用其他方式验证的内容(如单元测试)及剩余工作;ADR 保持在 `proposed/`(或放入 `implemented/` 并在 `## Implementation`
中说明缺口),并开后续事项。绝不声称完成了实际没有发生的真实云端验证。

### 证据文件模板

复制为 `.agents/evidence/verify/YYYY-MM-DD-<topic>.md`(topic 使用 kebab-case)。证据是历史快照:合入后新增带日期的新文件,
不要再修改旧文件。章节与上文英文模板一致:`Verification: <topic>`、日期/变更/结果(PASS | PARTIAL | BLOCKED | FAIL)/被测包/环境
(凭据仅经环境变量或 .env 提供,值不记录)、验证内容、执行的命令(凭据省略或脱敏)、结果表、清理情况、发现的问题、未验证内容。

### ADR 模板

格式由 [`README.md`](README.md) 定义:文件名 `YYYY-MM-DD-<slug>.md`,首行 `# Decision: <Title>`,紧接 `Status:`,
随后依次为 Problem / Decision / API Design / Alternatives considered / Dependencies / Test Strategy / Acceptance criteria,
可选 `## Evidence` 链接到验证证据文件(见上文英文模板)。ADR 必须使用英文撰写(见 [`README.md`](README.md) 的 Language 一节)。

### 粘贴到 PR 的检查清单

- [ ] 已新增/更新单元测试且通过
- [ ] 已针对真实组件执行 E2E(`make e2e`),结果记录在 `.agents/evidence/verify/<date>-<topic>.md`(无密钥、无泄漏资源)
- [ ] ADR/笔记位于 `.agents/notes/{proposed,implemented}/<category>/<date>-<slug>.md`,`Status:` 与目录一致
- [ ] 已更新中英文文档
- [ ] `[Unreleased]` 下已添加 CHANGELOG 条目
- [ ] `bash scripts/check-repo-health.sh` 通过
