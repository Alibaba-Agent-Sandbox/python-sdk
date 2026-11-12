# Python Hello 离线夹具

本目录为 Python SDK 的离线测试夹具。`commands.py` 在服务端注册命令，`call_api.py` 从客户端访问已运行的服务。真实模板的镜像、配置和发布说明由 [awesome-templates/python-hello](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/tree/main/python-hello) 维护。

## 使用真实模板

安装并配置[当前 CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox#installation) 后：

```bash
abx deploy python-hello --name hello
abx sandbox command run hello hello --arg name=Alice
abx sandbox command run hello run_script --arg 'code=print(1+1)'
abx sandbox upload hello ./local_file.txt /home/user/app/remote.txt
abx sandbox download hello /home/user/app/remote.txt ./local_file.txt
abx delete hello --yes
```

部署会生成并在本机保存缺省应用令牌。外部 Python 或 HTTP 调用者需要使用对应令牌及 Provider 返回的访问地址与认证头；见[模板使用指南](../../../docs/zh/guide/template-workflows.md)。安装 SDK 或本地注册函数不会部署该函数。

## 验证夹具

运行 `cd client-sdk && python -m pytest tests/test_templates/ -q`。该检查用于本地行为，不创建云资源。模板内容变更应提交到模板源仓库。
