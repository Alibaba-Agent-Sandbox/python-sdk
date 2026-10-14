# Template Fixtures（离线测试夹具）

**Server SDK。** 每个模板里的 `commands.py` 随镜像启动，在沙箱里面听 HTTP。`python-hello/call_api.py` 是例外：它跑在沙箱外面，对已经在听的服务发请求，属于 Client SDK。

> ⚠️ **本目录不是模板发布真源（This directory is NOT the publishing source）。**
>
> 官方与社区模板的**唯一真源**是独立仓库
> **[`alibaba-agent-sandbox/awesome-templates`](https://github.com/alibaba-agent-sandbox/awesome-templates)**：
> 模板内容、机器可读索引（`awesome-templates.yaml`）、发布与 CI 全部在那里维护。
> 本目录保留离线夹具，供本仓库测试使用——不是可发布模板集合。`agents-cli` 与真源仓库中的同名模板保持同步。

## 本目录内容

```
examples/templates/
├── README.md        ← 本说明（fixture notice）
├── python-hello/    ← 最小命令服务器夹具
└── agents-cli/      ← Codex / Qwen Code 的 Agents API 案例（镜像不预装 CLI）
```

`python-hello` 是一个最小端到端样例，用于让 `client-sdk/tests/test_templates/` 在**无网络**
条件下驱动真实安装管线（`abx install` 的本地 / GitHub 两种来源、YAML 加载、
缓存布局、容器内命令服务器 E2E）。它与真源仓库中的同名模板保持同步，
但**不从本仓库发布**。

## 发现与安装真实模板（远程索引）

模板通过真源仓库中的索引 `awesome-templates.yaml` 发现与安装：

（以下 `abx` 命令由独立 `cli` 仓库中的 `abx` CLI 提供。）

```bash
abx template search python             # 浏览远程目录（名称 / 标签 / 描述）
abx template install node-web          # 裸名 → 通过索引解析
abx template install alibaba-agent-sandbox/awesome-templates//qwen-code@v1.0.0   # 直接引用 + 版本锁定
```

索引默认地址（可用 `ABX_TEMPLATE_INDEX_URL` / `--index-url` 覆盖）：

```
https://raw.githubusercontent.com/alibaba-agent-sandbox/awesome-templates/main/awesome-templates.yaml
```

行为约定：

| 场景 | 行为 |
|------|------|
| 缓存新鲜（< 1 小时） | 直接使用 `~/.abx/index/` 缓存，不发起网络请求 |
| 网络失败 / GitHub 限流（403/429） | 回退到已缓存副本并给出 warning；无缓存时报 `NetworkError` 并附补救建议 |
| `--refresh` | 强制重新拉取（带 `If-None-Match` 条件请求） |
| `schema_version` 高于本客户端 | 拒绝解析并提示升级 `agent-sandbox` |
| 索引条目声明 `ref` | `abx template install <name>` 安装该固定版本 |
| 直接引用 `owner/repo//subdir@ref` | 完全绕过索引（网络失败时的兜底路径） |

## 校验

- 真源仓库侧（内容 / 索引对账 / `commands.py` E2E）：在
  [`awesome-templates` CI](https://github.com/alibaba-agent-sandbox/awesome-templates/actions) 中运行。
- 本仓库侧：`cd client-sdk && python -m pytest tests/test_templates/ -q`（离线 fixture 套件，无网络、无 Docker）。

## 新增或修改模板

请到[真源仓库](https://github.com/alibaba-agent-sandbox/awesome-templates)提交变更，参见其
[CONTRIBUTING.md](https://github.com/alibaba-agent-sandbox/awesome-templates/blob/main/CONTRIBUTING.md)：
一个模板 = 一个目录 + 一条索引记录，CI 强制两者不漂移。
