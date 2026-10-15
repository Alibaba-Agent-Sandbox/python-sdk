# 👋 Welcome to Agent Sandbox Community!

Hey everyone! Welcome to the **Agent Sandbox** community — we're thrilled to have you here! 🎉

## What is Agent Sandbox?

Agent Sandbox is a Python SDK (and the `abx` CLI, maintained in the `cli` repository) for creating, managing, and interacting with cloud sandboxes designed for AI agents. It uses E2B-style method names to ease porting, and adds Alibaba Cloud authentication and templates. Whether you're building autonomous agents, code interpreters, or secure execution environments, Agent Sandbox gives you the tools to do it with zero-config simplicity.

## 🗂️ How to Use This Community

We want to keep things organized so everyone can find what they need:

| What you need | Where to go |
|---------------|-------------|
| 💡 **Feature Requests** | [Discussions → Ideas](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/ideas) — suggest new features or improvements |
| 🐛 **Bug Reports** | [Issues](https://github.com/alibaba-agent-sandbox/python-sdk/issues/new/choose) — report bugs using our issue templates |
| 💬 **Q&A / Help** | [Discussions → Q&A](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/q-a) — ask questions and get help |
| 🎉 **Show and Tell** | [Discussions → Show and Tell](https://github.com/alibaba-agent-sandbox/python-sdk/discussions/categories/show-and-tell) — share what you've built! |

## 🚀 Quick Start

```bash
pip install agent-sandbox-client
```

```python
from agent_sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="python-base") as sb:
        result = await sb.run_code("print('Hello from sandbox!')")
        print(result.text)  # Hello from sandbox!
```

Or use the CLI (a separate Node.js project in the `cli` repository):

```bash
npm install -g @agent-sandbox/cli
abx create --template python-base
abx exec <sandbox-id> "echo hello"
```

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
