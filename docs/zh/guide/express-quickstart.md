# Express 快速开始

2026-10-15 在阿里云 Express（`alicloud-express`）上用 `agent-sandbox-client` 0.3.0 验证。模板是 generation 2，启动命令运行 `agent-sandbox-server`。

## 部署

```bash
abx template scaffold --template python --name hello-x
cd hello-x
abx template deploy . -y --generation 2 \
  --start-cmd 'agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py' \
  --ready-cmd 'agent-sandbox-server healthcheck --port 9000'
```

python 脚手架注册了 `hello(name="World")`，返回 `Hello, {name}!`。从部署输出里复制模板 id。

`--start-cmd` 和 `--ready-cmd` 需要 `--generation 2`。如果已有同名的 generation-1 模板，先删掉（`abx template delete <id> -y`）。如果部署报 `base must be a mapping`，把 `template.yaml` 改成：

```yaml
base:
  image: "fc-e2b-registry.cn-hangzhou.cr.aliyuncs.com/runtime/base:v0.0.49"
```

把地域和当前运行时基础镜像标签换成你自己的。

## 调用

```python
import asyncio

from agent_sandbox import ProviderSandbox as Sandbox

TEMPLATE = "<template-id>"


async def main() -> None:
    sb = await Sandbox.create(template=TEMPLATE, timeout=300)
    try:
        echoed = await sb.commands.run("echo hi")
        assert echoed.stdout == "hi\n" and echoed.exit_code == 0
        assert await sb.run("hello", name="Bob") == "Hello, Bob!"
        url = sb.network.get_url(9000)
        headers = sb.network.get_access_headers()
        # 用 headers 对 {url}/health 发 GET。/health 返回 200。
    finally:
        await sb.kill()


asyncio.run(main())
```

`sandbox.run` 不发送沙箱访问令牌。`get_access_headers()` 是给平台网关的 `X-Access-Token`。

Generation 1 仍然支持 `commands.run` 和 `files`（同一天在平台模板 `base`、envd 0.5.2 上验证）。镜像入口点是固定的，所以 generation-1 模板不能自己启动 `agent-sandbox-server`。命名命令需要上面的 generation-2 启动命令和就绪命令。

## 清理

`sb.kill()` 会删掉沙箱。用完后删除模板：

```bash
abx template delete <template-id> -y
```
