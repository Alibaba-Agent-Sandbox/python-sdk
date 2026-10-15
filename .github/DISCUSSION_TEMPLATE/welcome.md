---
title: "Welcome to Agent Sandbox Community!"
labels: []
---

👋 **Welcome to the Agent Sandbox community!**

We're excited to have you here. Agent Sandbox is a Python SDK (and the `abx` CLI, maintained in the `cli` repository) for creating, managing, and interacting with cloud sandboxes designed for AI agents — with E2B-style method names and Alibaba Cloud authentication and templates.

## 🗂️ Community Guide

Please use the right channel for your needs:

| Need | Where |
|------|-------|
| 💡 **Feature Request** | [Discussions → Ideas](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/ideas) |
| 🐛 **Bug Report** | [Issues](https://github.com/alibaba-agent-sandbox/python-sdk/issues/new/choose) |
| 💬 **Questions & Help** | [Discussions → Q&A](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/q-a) |
| 🎉 **Show and Tell** | [Discussions → Show and Tell](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/show-and-tell) |

## 🚀 Quick Start

```bash
pip install agent-sandbox-client
```

```python
from agent_sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="python-base") as sb:
        result = await sb.run_code("print('Hello from sandbox!')")
        print(result.text)
```

## 📚 Resources

- 📖 [Documentation](https://github.com/alibaba-agent-sandbox/python-sdk#readme)
- 🏗️ [Design Doc](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/docs/zh/DESIGN.md)
- 📦 [Community Templates](https://github.com/alibaba-agent-sandbox/awesome-templates)
- 📝 [Contributing Guide](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md)

## 🤝 Code of Conduct

Please be respectful and constructive. We follow the [Contributor Covenant Code of Conduct](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CODE_OF_CONDUCT.md).

---

Happy sandboxing! 🎉
