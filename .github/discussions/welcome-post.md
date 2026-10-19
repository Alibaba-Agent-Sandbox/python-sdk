# 👋 Welcome to Agent Sandbox Community!

Hey everyone! Welcome to the **Agent Sandbox** community — we're thrilled to have you here! 🎉

## What is Agent Sandbox?

Agent Sandbox is a Python SDK (and the `abx` CLI, maintained in the `agent-sandbox` repository) for creating, managing, and interacting with cloud sandboxes designed for AI agents. It uses E2B-style method names to ease porting, and adds Alibaba Cloud authentication and templates. Whether you're building autonomous agents, code interpreters, or secure execution environments, Agent Sandbox gives you the tools to do it with zero-config simplicity.

## 🗂️ How to Use This Community

We want to keep things organized so everyone can find what they need:

| What you need | Where to go |
|---------------|-------------|
| 💡 **Feature Requests** | [Discussions → Ideas](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/ideas) — suggest new features or improvements |
| 🐛 **Bug Reports** | [Issues](https://github.com/alibaba-agent-sandbox/python-sdk/issues/new/choose) — report bugs using our issue templates |
| 💬 **Q&A / Help** | [Discussions → Q&A](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/q-a) — ask questions and get help |
| 🎉 **Show and Tell** | [Discussions → Show and Tell](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/show-and-tell) — share what you've built! |

## 🚀 Quick Start

Install the matching client/server pair with the [source installation guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md); these packages are not yet published on PyPI. Configure your local credentials as described in [getting started](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/getting-started.md).

```python
from agent_sandbox import Sandbox

with Sandbox.create("base", timeout=60) as sb:
    result = sb.commands.run("printf hello")
    print(result.stdout)
```

For code execution use [the code-interpreter guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/client-sdk.md). The separate `abx` CLI is installed through its [binary installation guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md).

## 📚 Key Links

- 📖 **[README & Docs](https://github.com/alibaba-agent-sandbox/python-sdk#readme)**
- 🏗️ **[Design Document](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/docs/zh/DESIGN.md)**
- 📦 **[Community Templates](https://github.com/alibaba-agent-sandbox/awesome-templates)**
- 📝 **[Contributing Guide](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md)**
- 🔒 **[Security Policy](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/SECURITY.md)**

## 🤝 Code of Conduct

We're committed to fostering a welcoming and inclusive environment. Please take a moment to review our [Code of Conduct](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/.github/CODE_OF_CONDUCT.md). Be kind, be constructive, and help us build something great together.

---

We'd love to hear what you're building with Agent Sandbox — feel free to introduce yourself and share your use case in the replies! 👇

Happy sandboxing! 🏖️
