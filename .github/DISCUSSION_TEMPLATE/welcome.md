---
title: "Welcome to Agent Sandbox Community!"
labels: []
---

👋 **Welcome to the Agent Sandbox community!**

We're excited to have you here. Agent Sandbox is a Python SDK (and the `abx` CLI, maintained in the `agent-sandbox` repository) for creating, managing, and interacting with cloud sandboxes designed for AI agents — with E2B-style method names and Alibaba Cloud authentication and templates.

## 🗂️ Community Guide

Please use the right channel for your needs:

| Need | Where |
|------|-------|
| 💡 **Feature Request** | [Discussions → Ideas](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/ideas) |
| 🐛 **Bug Report** | [Issues](https://github.com/alibaba-agent-sandbox/python-sdk/issues/new/choose) |
| 💬 **Questions & Help** | [Discussions → Q&A](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/q-a) |
| 🎉 **Show and Tell** | [Discussions → Show and Tell](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/show-and-tell) |

## 🚀 Quick Start

Install the matching client/server pair with the [source installation guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md); these packages are not yet published on PyPI. Configure your local credentials as described in [getting started](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/getting-started.md).

```python
from agent_sandbox import Sandbox

with Sandbox.create("base", timeout=60) as sb:
    result = sb.commands.run("printf hello")
    print(result.stdout)
```

For code execution use [the code-interpreter guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/client-sdk.md). The separate `abx` CLI is installed through its [binary installation guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md).

## 📚 Resources

- 📖 [Documentation](https://github.com/alibaba-agent-sandbox/python-sdk#readme)
- 🏗️ [Design Doc](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/docs/zh/DESIGN.md)
- 📦 [Community Templates](https://github.com/alibaba-agent-sandbox/awesome-templates)
- 📝 [Contributing Guide](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md)

## 🤝 Code of Conduct

Please be respectful and constructive. We follow the [Contributor Covenant Code of Conduct](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CODE_OF_CONDUCT.md).

---

Happy sandboxing! 🎉
