# 桌面操作和模拟接管验收

此可选流程直接使用 `e2b_desktop.Sandbox`，在真实 Linux 桌面内运行浏览器，通过另一个 noVNC 客户端接管，再交回 Agent，保存可离线查看的截图时间线。测试中的操作员由程序模拟，不代表真实用户登录验收，也不是托管接管服务。

使用同地域官方 Desktop 镜像 `runtime/desktop:v0.0.44` 创建独立命名模板，选择第二代沙箱、4 CPU、8192 MB，并独立确认 `Ready`。镜像和构建准备见[官方模板指南](https://help.aliyun.com/zh/functioncompute/desktop-template-example)。保留实际 Template ID；验收脚本不会修改或删除传入的模板。

在本仓库中安装隔离的可选依赖，配置好 `E2B_API_KEY`、`E2B_API_URL` 和 `E2B_DOMAIN` 后运行：

```bash
uv venv --python 3.11 .venv-desktop
uv pip install --python .venv-desktop/bin/python -r e2e/desktop-requirements.txt
.venv-desktop/bin/python e2e/desktop_acceptance.py \
  --template "$E2B_DESKTOP_TEMPLATE" --output-dir ./desktop-evidence-new
```

本地需要 Chromium 可执行文件；必要时通过 `--browser-executable` 指定。输出目录必须是新目录。此测试固定了已验证的镜像、分辨率和模拟页面；适配其他镜像前先看实际截图，再调整操作坐标。

## 三种独立凭证

| 层级 | 凭证和请求头 |
| --- | --- |
| SDK 控制接口、命令和文件 | `envdAccessToken`，SDK 自动发送 `X-Access-Token` |
| 禁止匿名访问的应用端口 | `Sandbox.traffic_access_token`，发送 `e2b-traffic-access-token` |
| VNC 会话 | `stream.start(require_auth=True)` 生成的口令 |

创建时显式设置 `secure=True`、`network={"allow_public_traffic": False}`。应用入口 Token 留在受控后端代理中，浏览器仅连接其回环地址。凭证区别见[网络访问指南](https://help.aliyun.com/en/agent-sandbox/network-access-control)。核对实际的拒绝和成功请求；公开 HTML 或 RFB 握手横幅本身不能证明鉴权已经成功。

脚本检查真实 PNG、鼠标键盘的实际效果、错误 VNC 口令被拒绝、实时 WebSocket 数据，并独立下载、核对 `agent-start → operator-step → agent-resumed` 的状态序列。`replay.html`、`timeline.json`、截图 SHA-256 和 `gui-state.json` 保留执行过程。回放是截图序列，不是完整视频。脚本只删除本次新建的沙箱，并通过独立的类型化不存在错误确认清理；测试模板由其所属流程另行删除。
